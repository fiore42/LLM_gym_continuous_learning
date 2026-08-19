#!/usr/bin/env python3
"""Audit compact digest passages and the model claims made from them.

No model call and no network access. The first phase shows the explicit
model-generated claim and its mapped set of one to three exact evidence quotes
while hiding the model's proposed label and reason. Optional context may
clarify a quote but cannot supply missing claim facts. The second phase reveals those judgements for
review. This audits existing decisions; it does not measure missed claims or
corpus-level recall.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.corpus.evidence import index_signature
from llm_gym.corpus.window import attach_item_text
from llm_gym.shared.atomic import atomic_write_text


DEFAULT_REPORT = Path(
    "data/digests/2026-07-31-to-2026-08-07-youtube-glm-5.2-open-weight-"
    "significance-v2-report.json"
)
DEFAULT_INDEX = Path("data/evidence.sqlite3")
DEFAULT_RUBRIC = Path("config/digest_claim_audit_v1.json")
DEFAULT_PACKET = Path("data/human-review/digest-claim-audit-v1/audit-packet.json")
DEFAULT_OUTPUT_DIR = Path("data/human-labels/digest-claim-audit-v1")
AUDIT_SCHEMA_VERSION = 1
LABEL_SCHEMA_VERSION = 1
MODEL_REVIEW_SCHEMA_VERSION = 1
MODEL_LABELS = ("SIGNIFICANT", "INCREMENTAL", "UNSUPPORTED", "PROMOTIONAL")
HUMAN_CLASSIFICATIONS = MODEL_LABELS + ("OUT_OF_SCOPE", "UNABLE_TO_DETERMINE")
SCOPE_VERDICTS = ("IN_SCOPE", "OUT_OF_SCOPE", "UNCLEAR")
SUPPORT_VERDICTS = ("FULLY_SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "UNCLEAR")
SUPPORT_DECISIONS = SUPPORT_VERDICTS + ("NOT_APPLICABLE",)
MODEL_LABEL_VERDICTS = ("AGREE", "DISAGREE", "UNCLEAR", "NOT_APPLICABLE")
SAMPLE_SEED = "digest-claim-audit-v1"


def _enable_terminal_line_editing() -> bool:
    """Activate readline editing for input(), including normal Backspace."""
    try:
        __import__("readline")
    except ImportError:
        return False
    return True


LINE_EDITING_ENABLED = _enable_terminal_line_editing()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "reviewer"


def _stable_order(item_id: str) -> str:
    return _sha256_text(f"{SAMPLE_SEED}:{item_id}")


def _normalise_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _sample_allocations(counts: dict[str, int], sample_size: int) -> dict[str, int]:
    """Allocate a balanced sample across every present model label."""
    population = sum(counts.values())
    if not 0 < sample_size <= population:
        raise ValueError("sample_size must be between 1 and the number of assessments")
    present = [label for label in MODEL_LABELS if counts.get(label, 0)]
    if sample_size < len(present):
        raise ValueError("sample_size is too small to include every model label")
    result = {label: min(counts[label], sample_size // len(present)) for label in present}
    while sum(result.values()) < sample_size:
        candidates = [label for label in present if result[label] < counts[label]]
        if not candidates:
            raise ValueError("sample allocation exceeds available assessments")
        label = min(candidates, key=lambda name: (result[name], MODEL_LABELS.index(name)))
        result[label] += 1
    return result


def passage_context(text: str, quote: str, *, context_chars: int) -> dict[str, str]:
    """Locate a quote and return bounded normalized context around it."""
    source = _normalise_whitespace(text)
    passage = _normalise_whitespace(quote)
    position = source.casefold().find(passage.casefold())
    if position < 0:
        raise ValueError("supporting_quote does not occur in the source text")
    start = max(0, position - context_chars)
    end = min(len(source), position + len(passage) + context_chars)
    before = source[start:position].strip()
    after = source[position + len(passage):end].strip()
    if start:
        before = f"…{before}"
    if end < len(source):
        after = f"{after}…"
    return {"context_before": before, "passage": source[position:position + len(passage)],
            "context_after": after}


def _source_metadata(index_path: str | Path, item_ids: set[str]) -> list[dict[str, Any]]:
    """Load stable source provenance for selected evidence items."""
    if not item_ids:
        return []
    placeholders = ",".join("?" for _ in item_ids)
    connection = sqlite3.connect(index_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT evidence_id, platform, source_key, canonical_url, published_at, "
            f"title, author, kind FROM evidence_items WHERE evidence_id IN ({placeholders})",
            sorted(item_ids),
        ).fetchall()
    finally:
        connection.close()
    if len(rows) != len(item_ids):
        found = {str(row["evidence_id"]) for row in rows}
        raise ValueError(f"source metadata missing for evidence IDs: {sorted(item_ids - found)}")
    return [dict(row) for row in rows]


def build_audit_packet(*, report_path: str | Path, index_path: str | Path,
                       rubric_path: str | Path, sample_size: int = 20,
                       context_chars: int = 600) -> dict[str, Any]:
    """Build compact blind cards from a deterministic stratified sample."""
    report = _read_json(report_path)
    rubric = _read_json(rubric_path)
    if any(not isinstance(row.get("supporting_evidence"), list)
           for row in report.get("assessments") or []):
        raise ValueError(
            "claim audit requires a significance-v2 report with supporting_evidence; "
            "a v1 single-quote report cannot support this review")
    report_signature = (report.get("window") or {}).get("index_signature")
    current_signature = index_signature(index_path)
    if report_signature != current_signature:
        raise ValueError(
            f"corpus identity mismatch: report={report_signature}, current_index={current_signature}")

    assessments = report.get("assessments") or []
    by_id = {str(row.get("item_id")): row for row in assessments}
    if len(by_id) != len(assessments):
        raise ValueError("digest report contains duplicate assessment item IDs")
    counts = Counter(str(row.get("significance")) for row in assessments)
    if set(counts) - set(MODEL_LABELS):
        raise ValueError(f"digest report contains unknown model labels: {dict(counts)}")
    allocations = _sample_allocations(dict(counts), sample_size)
    selected_ids: set[str] = set()
    for label, allocation in allocations.items():
        candidates = sorted(
            (item_id for item_id, row in by_id.items() if row["significance"] == label),
            key=_stable_order,
        )
        selected_ids.update(candidates[:allocation])

    source_rows = _source_metadata(index_path, selected_ids)
    attached = attach_item_text(index_path, source_rows)
    cards = []
    for source in attached:
        item_id = str(source["evidence_id"])
        assessment = by_id[item_id]
        text = str(source.get("text") or "")
        if not text.strip():
            raise ValueError(f"source item has no reviewable text: {item_id}")
        evidence = []
        for entry in assessment["supporting_evidence"]:
            context = passage_context(text, str(entry.get("quote") or ""),
                                      context_chars=context_chars)
            evidence.append({
                "claim_component": str(entry.get("claim_component") or ""),
                "quote": context["passage"],
                "context_before": context["context_before"],
                "context_after": context["context_after"],
                "quote_sha256": _sha256_text(context["passage"]),
            })
        evidence_sha256 = _sha256_text(json.dumps(
            [{"claim_component": row["claim_component"], "quote": row["quote"]}
             for row in evidence], sort_keys=True, ensure_ascii=False))
        cards.append({
            "audit_id": item_id,
            "source_item_id": item_id,
            "source_title": source.get("title"),
            "platform": source.get("platform"),
            "source_key": source.get("source_key"),
            "source_author": source.get("author"),
            "canonical_url": source.get("canonical_url"),
            "published_at": source.get("published_at"),
            "claim_to_evaluate": assessment["claimed_change"],
            "claim_sha256": _sha256_text(assessment["claimed_change"]),
            "supporting_evidence": evidence,
            "evidence_sha256": evidence_sha256,
            "source_text_sha256": _sha256_text(text),
        })
    cards.sort(key=lambda row: _stable_order(row["audit_id"]))
    rubric_sha256 = _sha256_text(json.dumps(rubric, sort_keys=True, ensure_ascii=False))
    return {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "created_at": _now(),
        "audit_design": "model_selected_evidence_set_blind_support_and_label_review",
        "rubric": rubric,
        "rubric_sha256": rubric_sha256,
        "corpus": {"index_signature": current_signature},
        "model_result_reference": {
            "report_path": str(report_path),
            "model": report.get("model"),
            "prompt_version": report.get("prompt_version"),
            "prompt_sha256": report.get("prompt_sha256"),
            "reason_and_label_hidden_during_blind_phase": True,
        },
        "selection": {
            "method": "deterministic balanced sample by hidden model label",
            "seed": SAMPLE_SEED,
            "assessment_population": len(assessments),
            "sample_size": len(cards),
            "allocation_by_hidden_model_label": allocations,
        },
        "limitations": [
            "Claims and one to three mapped evidence quotes were selected by the model being audited.",
            "The audit measures selected-decision quality, not missed claims or recall.",
            "An evidence-set verdict is not a single label for the complete source transcript.",
            "Optional context clarifies a quote but cannot supply missing claim facts.",
            "Blind claim classification alignment is diagnostic because candidates were selected by the model being audited.",
        ],
        "cards": cards,
    }


def write_audit_packet(packet: dict[str, Any], output_path: str | Path) -> None:
    output = Path(output_path)
    card_dir = output.parent / "cards"
    card_dir.mkdir(parents=True, exist_ok=True)
    for stale_card in card_dir.glob("*.txt"):
        stale_card.unlink()
    for index, card in enumerate(packet["cards"], start=1):
        path = card_dir / f"{index:02d}-{card['audit_id'][:12]}.txt"
        platform = str(card.get("platform") or "").lower()
        source_key = str(card.get("source_key") or "")
        if platform == "youtube":
            producer = f"YOUTUBE CHANNEL: {source_key}"
        elif platform == "x":
            producer = f"X ACCOUNT: {'@' if source_key and not source_key.startswith('@') else ''}{source_key}"
        else:
            producer = f"SOURCE ACCOUNT: {source_key}"
        evidence_text = ""
        for evidence_index, evidence in enumerate(card["supporting_evidence"], start=1):
            evidence_text += (
                f"\n=== AI-SELECTED EVIDENCE {evidence_index}/"
                f"{len(card['supporting_evidence'])} ===\n"
                f"CLAIM COMPONENT: {evidence['claim_component']}\n"
                "HIGHLIGHTED PASSAGE:\n"
                f"{evidence['quote']}\n"
                "=== END EVIDENCE ===\n"
            )
        text = (
            f"SOURCE TITLE: {card.get('source_title') or ''}\n"
            f"{producer}\n"
            f"PLATFORM: {platform or 'unknown'}\n"
            f"SOURCE: {card.get('canonical_url') or ''}\n"
            f"PUBLISHED: {card.get('published_at') or ''}\n"
            f"AUDIT_ID: {card['audit_id']}\n\n"
            "=== CLAIM TO EVALUATE ===\n"
            f"{card['claim_to_evaluate']}\n"
            "=== END CLAIM ===\n\n"
            f"{evidence_text.lstrip()}"
        )
        path.write_text(text, encoding="utf-8")
        card["local_card_path"] = str(path)
    _write_json(output, packet)


def new_label_file(packet: dict[str, Any], reviewer_id: str) -> dict[str, Any]:
    return {
        "label_schema_version": LABEL_SCHEMA_VERSION,
        "reviewer_id": reviewer_id,
        "created_at": _now(),
        "updated_at": _now(),
        "rubric_sha256": packet["rubric_sha256"],
        "index_signature": packet["corpus"]["index_signature"],
        "blind_to_model_reason_and_label": True,
        "labels": [],
    }


def add_claim_decision(labels: dict[str, Any], card: dict[str, Any], *,
                       scope_verdict: str, evidence_support_verdict: str, human_label: str,
                       rationale: str) -> dict[str, Any]:
    scope_verdict = scope_verdict.strip().upper()
    evidence_support_verdict = evidence_support_verdict.strip().upper()
    human_label = human_label.strip().upper()
    rationale = rationale.strip()
    if scope_verdict not in SCOPE_VERDICTS:
        raise ValueError(f"scope_verdict must be one of {SCOPE_VERDICTS}")
    if evidence_support_verdict not in SUPPORT_DECISIONS:
        raise ValueError(f"evidence_support_verdict must be one of {SUPPORT_DECISIONS}")
    if human_label not in HUMAN_CLASSIFICATIONS:
        raise ValueError(f"human_label must be one of {HUMAN_CLASSIFICATIONS}")
    expected_skips = {
        "OUT_OF_SCOPE": ("NOT_APPLICABLE", "OUT_OF_SCOPE"),
        "UNCLEAR": ("NOT_APPLICABLE", "UNABLE_TO_DETERMINE"),
    }
    if scope_verdict in expected_skips and (
            evidence_support_verdict, human_label) != expected_skips[scope_verdict]:
        raise ValueError(f"{scope_verdict} requires {expected_skips[scope_verdict]}")
    if scope_verdict == "IN_SCOPE" and (
            evidence_support_verdict == "NOT_APPLICABLE" or human_label == "OUT_OF_SCOPE"):
        raise ValueError("IN_SCOPE requires a support verdict and significance classification")
    if not rationale:
        raise ValueError("rationale is required")
    existing = {row["audit_id"] for row in labels.get("labels") or []}
    if card["audit_id"] in existing:
        raise ValueError(f"audit card is already labeled: {card['audit_id']}")
    labels.setdefault("labels", []).append({
        "audit_id": card["audit_id"],
        "claim_sha256": card["claim_sha256"],
        "evidence_sha256": card["evidence_sha256"],
        "platform": card.get("platform"),
        "source_key": card.get("source_key"),
        "source_title": card.get("source_title"),
        "canonical_url": card.get("canonical_url"),
        "scope_verdict": scope_verdict,
        "evidence_support_verdict": evidence_support_verdict,
        "human_classification": human_label,
        "rationale": rationale,
        "labeled_at": _now(),
    })
    labels["updated_at"] = _now()
    return labels


def validate_label_file(packet: dict[str, Any], labels: dict[str, Any], *,
                        require_complete: bool) -> dict[str, Any]:
    if labels.get("label_schema_version") != LABEL_SCHEMA_VERSION:
        raise ValueError(f"label file must use schema version {LABEL_SCHEMA_VERSION}")
    if labels.get("rubric_sha256") != packet.get("rubric_sha256"):
        raise ValueError("label file uses a different rubric")
    if labels.get("index_signature") != packet["corpus"]["index_signature"]:
        raise ValueError("label file uses a different corpus index_signature")
    cards = {row["audit_id"]: row for row in packet["cards"]}
    seen: set[str] = set()
    for row in labels.get("labels") or []:
        audit_id = str(row.get("audit_id"))
        if audit_id in seen:
            raise ValueError(f"duplicate claim decision: {audit_id}")
        seen.add(audit_id)
        if audit_id not in cards:
            raise ValueError(f"unknown audit card: {audit_id}")
        if row.get("evidence_sha256") != cards[audit_id]["evidence_sha256"]:
            raise ValueError(f"evidence set changed for audit card: {audit_id}")
        if row.get("claim_sha256") != cards[audit_id]["claim_sha256"]:
            raise ValueError(f"claim changed for audit card: {audit_id}")
        for field in ("platform", "source_key", "source_title", "canonical_url"):
            if row.get(field) != cards[audit_id].get(field):
                raise ValueError(f"source provenance changed for audit card: {audit_id}")
        scope_verdict = row.get("scope_verdict")
        if scope_verdict not in SCOPE_VERDICTS:
            raise ValueError(f"invalid scope verdict for audit card: {audit_id}")
        if row.get("evidence_support_verdict") not in SUPPORT_DECISIONS:
            raise ValueError(f"invalid evidence support verdict for audit card: {audit_id}")
        if row.get("human_classification") not in HUMAN_CLASSIFICATIONS:
            raise ValueError(f"invalid human classification for audit card: {audit_id}")
        if not str(row.get("rationale") or "").strip():
            raise ValueError(f"missing rationale for audit card: {audit_id}")
        if scope_verdict == "OUT_OF_SCOPE" and (
                row["evidence_support_verdict"], row["human_classification"]) != (
                    "NOT_APPLICABLE", "OUT_OF_SCOPE"):
            raise ValueError(f"invalid out-of-scope decision for audit card: {audit_id}")
        if scope_verdict == "UNCLEAR" and (
                row["evidence_support_verdict"], row["human_classification"]) != (
                    "NOT_APPLICABLE", "UNABLE_TO_DETERMINE"):
            raise ValueError(f"invalid unclear-scope decision for audit card: {audit_id}")
        if scope_verdict == "IN_SCOPE" and (
                row["evidence_support_verdict"] == "NOT_APPLICABLE"
                or row["human_classification"] == "OUT_OF_SCOPE"):
            raise ValueError(f"invalid in-scope decision for audit card: {audit_id}")
    missing = sorted(set(cards) - seen)
    if require_complete and missing:
        raise ValueError(f"label file is incomplete: {len(missing)} cards remain")
    counts = Counter(row["human_classification"] for row in labels.get("labels") or [])
    scope_counts = Counter(row["scope_verdict"] for row in labels.get("labels") or [])
    return {"valid": True, "reviewer_id": labels.get("reviewer_id"),
            "labeled": len(seen), "total": len(cards), "remaining": len(missing),
            "label_counts": dict(sorted(counts.items())),
            "scope_counts": dict(sorted(scope_counts.items()))}


def _prompt_choice(prompt: str, choices: dict[str, str], input_fn: Callable[[str], str]) -> str:
    while True:
        answer = input_fn(prompt).strip().lower()
        if answer in choices:
            return choices[answer]
        print(f"Choose one of: {', '.join(choices)}")


def _show_card(card: dict[str, Any], *, use_pager: bool) -> None:
    path = Path(card["local_card_path"])
    if use_pager and sys.stdin.isatty() and sys.stdout.isatty():
        pager = shlex.split(os.environ.get("PAGER", "less"))
        try:
            subprocess.run([*pager, str(path)], check=False)
            return
        except FileNotFoundError:
            pass
    print(path.read_text(encoding="utf-8"))


def _print_rubric(rubric: dict[str, Any]) -> None:
    print("\nCLAIM-AUDIT RUBRIC")
    print(rubric["scope_question"])
    for verdict in SCOPE_VERDICTS:
        print(f"- {verdict}: {rubric['scope_verdicts'][verdict]}")
    print("\nAI-SELECTED EVIDENCE SUPPORT (IN-SCOPE ITEMS ONLY)")
    print(rubric["support_question"])
    for verdict in SUPPORT_VERDICTS:
        print(f"- {verdict}: {rubric['support_verdicts'][verdict]}")
    print("\nSIGNIFICANCE OF WHAT IS ACTUALLY SUPPORTED")
    print(rubric["blind_question"])
    for label in MODEL_LABELS + ("UNABLE_TO_DETERMINE",):
        print(f"- {label}: {rubric['passage_labels'][label]}")
    print("The verdict applies to the stated claim—not the video title or whole source.")


def _print_blind_input_index() -> None:
    print("\nINPUT KEY INDEX")
    print("Scope: y = in scope | n = out of scope | u = unclear (n/u skip support and significance)")
    print("Evidence-set support: f = fully supported | p = partially supported | n = not supported | u = unclear | c = show context")
    print("Digest label justified by the evidence set: s = significant | i = incremental | u = unsupported | p = promotional | x = unable to determine")


def _print_reveal_objective() -> None:
    print("MODEL-DECISION REVEAL PHASE")
    print("Your blind scope, support, and significance decisions are locked.")
    print("For each in-scope card, do two separate checks:")
    print("1. REASON GROUNDING — does the selected evidence support every material "
          "assertion in the model's explanation?")
    print("2. LABEL COMPARISON — the script shows whether your blind label and the "
          "model label match. Exact matches are recorded automatically; only "
          "differences need your judgement.")
    print("A grounded label can have a partly unsupported explanation, so these "
          "results are kept separate.\n")


def _print_reveal_input_index(*, labels_match: bool = False) -> None:
    print("\nINPUT KEY INDEX")
    print("Reason support: f = fully supported | p = partially supported | n = not supported | u = unclear")
    if labels_match:
        print("Model label: exact blind match — AGREE is recorded automatically")
    else:
        print("Different model label: y = reasonable alternative | n = not reasonable | u = unclear")


def _prompt_evidence_support(card: dict[str, Any], input_fn: Callable[[str], str]) -> str:
    choices = {"f": "FULLY_SUPPORTED", "p": "PARTIALLY_SUPPORTED",
               "n": "NOT_SUPPORTED", "u": "UNCLEAR"}
    while True:
        answer = input_fn(
            "Do the AI-selected passages jointly support the complete stated claim? "
            "[f/p/n/u/c=context]: ").strip().lower()
        if answer in choices:
            return choices[answer]
        if answer == "c":
            print("\nOPTIONAL INTERPRETATION CONTEXT")
            print("Use this only to clarify a selected passage; it cannot supply missing claim facts.")
            for index, evidence in enumerate(card["supporting_evidence"], start=1):
                print(f"\nEVIDENCE {index}")
                print(f"BEFORE: {evidence['context_before']}")
                print(f"QUOTE: {evidence['quote']}")
                print(f"AFTER: {evidence['context_after']}")
            continue
        print("Choose one of: f, p, n, u, c")


def run_blind_labels(packet: dict[str, Any], labels_path: str | Path, *, reviewer_id: str,
                     use_pager: bool = False, max_cards: int = 0,
                     input_fn: Callable[[str], str] = input) -> dict[str, Any]:
    labels_path = Path(labels_path)
    labels = _read_json(labels_path) if labels_path.exists() else new_label_file(packet, reviewer_id)
    if labels.get("reviewer_id") != reviewer_id:
        raise ValueError("reviewer_id does not match the existing label file")
    validate_label_file(packet, labels, require_complete=False)
    completed = {row["audit_id"] for row in labels["labels"]}
    pending = [card for card in packet["cards"] if card["audit_id"] not in completed]
    if max_cards > 0:
        pending = pending[:max_cards]
    print("BLIND CLAIM AUDIT: the claim is visible; the model reason and proposed label are hidden.")
    _print_rubric(packet["rubric"])
    print("Labels: S=SIGNIFICANT, I=INCREMENTAL, U=UNSUPPORTED, P=PROMOTIONAL, X=UNABLE_TO_DETERMINE")
    for position, card in enumerate(pending, start=len(completed) + 1):
        print(f"\n=== Audit card {position}/{len(packet['cards'])} ===")
        _show_card(card, use_pager=use_pager)
        _print_blind_input_index()
        scope_verdict = _prompt_choice(
            "Is this claim about building, evaluating, deploying, operating, securing, governing, or using AI/agent systems? [y/n/u]: ",
            {"y": "IN_SCOPE", "n": "OUT_OF_SCOPE", "u": "UNCLEAR"}, input_fn)
        if scope_verdict == "OUT_OF_SCOPE":
            evidence_support, human_label = "NOT_APPLICABLE", "OUT_OF_SCOPE"
            print("Recorded as OUT_OF_SCOPE; evidence support and significance are skipped.")
        elif scope_verdict == "UNCLEAR":
            evidence_support, human_label = "NOT_APPLICABLE", "UNABLE_TO_DETERMINE"
            print("Scope is unclear; evidence support and significance are skipped.")
        else:
            evidence_support = _prompt_evidence_support(card, input_fn)
            human_label = _prompt_choice(
                "Which digest label does this evidence set justify for the stated claim [s/i/u/p/x]: ",
                {"s": "SIGNIFICANT", "i": "INCREMENTAL", "u": "UNSUPPORTED",
                 "p": "PROMOTIONAL", "x": "UNABLE_TO_DETERMINE"}, input_fn)
        rationale = ""
        while not rationale:
            rationale = input_fn("One-sentence rationale for this evidence set: ").strip()
        add_claim_decision(labels, card, scope_verdict=scope_verdict,
                           evidence_support_verdict=evidence_support,
                           human_label=human_label, rationale=rationale)
        _write_json(labels_path, labels)
        print(f"Saved {position}/{len(packet['cards'])} to {labels_path}")
    return validate_label_file(packet, labels, require_complete=False)


def build_model_review(packet: dict[str, Any], labels: dict[str, Any], report: dict[str, Any],
                       responses: Iterable[dict[str, Any]]) -> dict[str, Any]:
    validate_label_file(packet, labels, require_complete=True)
    reference = packet["model_result_reference"]
    observed = {
        "model": report.get("model"),
        "prompt_version": report.get("prompt_version"),
        "prompt_sha256": report.get("prompt_sha256"),
    }
    expected = {key: reference.get(key) for key in observed}
    if observed != expected:
        raise ValueError(f"model report provenance mismatch: expected={expected}, observed={observed}")
    human = {row["audit_id"]: row for row in labels["labels"]}
    assessments = {str(row["item_id"]): row for row in report.get("assessments") or []}
    cards = {row["audit_id"]: row for row in packet["cards"]}
    rows = []
    seen: set[str] = set()
    for response in responses:
        audit_id = str(response.get("audit_id"))
        if audit_id in seen:
            raise ValueError(f"duplicate model review: {audit_id}")
        seen.add(audit_id)
        if audit_id not in human or audit_id not in assessments or audit_id not in cards:
            raise ValueError(f"unknown model-review audit card: {audit_id}")
        reason_support = str(response.get("reason_support_verdict") or "").upper()
        label_verdict = str(response.get("model_label_verdict") or "").upper()
        if reason_support not in SUPPORT_DECISIONS:
            raise ValueError(f"reason_support_verdict must be one of {SUPPORT_DECISIONS}")
        if label_verdict not in MODEL_LABEL_VERDICTS:
            raise ValueError(f"model_label_verdict must be one of {MODEL_LABEL_VERDICTS}")
        in_scope = human[audit_id]["scope_verdict"] == "IN_SCOPE"
        if in_scope and (reason_support == "NOT_APPLICABLE"
                         or label_verdict == "NOT_APPLICABLE"):
            raise ValueError("in-scope model review cannot be NOT_APPLICABLE")
        if not in_scope and (reason_support, label_verdict) != (
                "NOT_APPLICABLE", "NOT_APPLICABLE"):
            raise ValueError("out-of-scope or unclear model review must be NOT_APPLICABLE")
        assessment = assessments[audit_id]
        rows.append({
            "audit_id": audit_id,
            "source_title": cards[audit_id].get("source_title"),
            "platform": cards[audit_id].get("platform"),
            "source_key": cards[audit_id].get("source_key"),
            "canonical_url": cards[audit_id].get("canonical_url"),
            "claim_to_evaluate": cards[audit_id]["claim_to_evaluate"],
            "scope_verdict": human[audit_id]["scope_verdict"],
            "evidence_support_verdict": human[audit_id]["evidence_support_verdict"],
            "human_classification": human[audit_id]["human_classification"],
            "human_rationale": human[audit_id]["rationale"],
            "model_claimed_change": assessment["claimed_change"],
            "model_reason": assessment["reason"],
            "model_label": assessment["significance"],
            "blind_label_match": human[audit_id]["human_classification"] == assessment["significance"],
            "reason_support_verdict": reason_support,
            "model_label_verdict": label_verdict,
            "audit_note": str(response.get("audit_note") or "").strip(),
        })
    return {
        "model_review_schema_version": MODEL_REVIEW_SCHEMA_VERSION,
        "created_at": _now(),
        "reviewer_id": labels["reviewer_id"],
        "model": report.get("model"),
        "prompt_version": report.get("prompt_version"),
        "responses": rows,
    }


def run_model_review(packet: dict[str, Any], labels: dict[str, Any], report: dict[str, Any],
                     output_path: str | Path,
                     input_fn: Callable[[str], str] = input) -> dict[str, Any]:
    validate_label_file(packet, labels, require_complete=True)
    output_path = Path(output_path)
    existing = _read_json(output_path) if output_path.exists() else {"responses": []}
    responses = list(existing.get("responses") or [])
    completed = {row["audit_id"] for row in responses}
    human = {row["audit_id"]: row for row in labels["labels"]}
    assessments = {str(row["item_id"]): row for row in report.get("assessments") or []}
    _print_reveal_objective()
    for position, card in enumerate(packet["cards"], start=1):
        audit_id = card["audit_id"]
        if audit_id in completed:
            continue
        assessment = assessments[audit_id]
        print(f"\n=== Reveal and verify {position}/{len(packet['cards'])} ===")
        _show_card(card, use_pager=False)
        print("=== YOUR LOCKED BLIND DECISION ===")
        print(f"Locked human classification: {human[audit_id]['human_classification']}")
        print(f"Locked scope verdict: {human[audit_id]['scope_verdict']}")
        print(f"Locked evidence-support verdict: {human[audit_id]['evidence_support_verdict']}")
        print(f"Human rationale: {human[audit_id]['rationale']}")
        print("\n=== REVEALED MODEL DECISION ===")
        print(f"Model reason: {assessment['reason']}")
        print(f"Model label: {assessment['significance']}")
        if human[audit_id]["scope_verdict"] != "IN_SCOPE":
            reason_support = label_verdict = "NOT_APPLICABLE"
            note = f"Skipped model-decision review: {human[audit_id]['scope_verdict']}."
            print(note)
        else:
            labels_match = (
                human[audit_id]["human_classification"] == assessment["significance"]
            )
            comparison = "EXACT MATCH" if labels_match else "DIFFERENT"
            print(f"\n=== BLIND LABEL COMPARISON: {comparison} ===")
            print(f"Human: {human[audit_id]['human_classification']}")
            print(f"Model: {assessment['significance']}")
            if labels_match:
                print("The labels are identical. AGREE will be recorded automatically.")
            else:
                print("The labels differ. You will decide whether the model label is still "
                      "a reasonable alternative.")
            _print_reveal_input_index(labels_match=labels_match)
            print("\nQUESTION 1 — MODEL-REASON GROUNDING")
            print("Your earlier support verdict applied to the stated claim. This question "
                  "applies only to the model's explanation above.")
            print("Choose PARTIALLY_SUPPORTED when the core explanation is grounded but it "
                  "adds an unsupported assertion, such as calling something established "
                  "practice without evidence for that claim.")
            reason_support = _prompt_choice(
                "Does the selected evidence support every material assertion in the model "
                "reason? [f/p/n/u]: ",
                {"f": "FULLY_SUPPORTED", "p": "PARTIALLY_SUPPORTED",
                 "n": "NOT_SUPPORTED", "u": "UNCLEAR"}, input_fn)
            if labels_match:
                label_verdict = "AGREE"
            else:
                print("\nQUESTION 2 — DIFFERENT-LABEL REASONABLENESS")
                print("This does not change your locked blind label. Decide only whether the "
                      "model's different label is also defensible for the supported content.")
                label_verdict = _prompt_choice(
                    "Is the model's different label a reasonable alternative? [y/n/u]: ",
                    {"y": "AGREE", "n": "DISAGREE", "u": "UNCLEAR"}, input_fn)
            note = input_fn("Optional audit note (Enter to skip): ").strip()
        responses.append({"audit_id": audit_id, "reason_support_verdict": reason_support,
                          "model_label_verdict": label_verdict, "audit_note": note})
        result = build_model_review(packet, labels, report, responses)
        _write_json(output_path, result)
        print(f"Saved {position}/{len(packet['cards'])} to {output_path}")
    return build_model_review(packet, labels, report, responses)


def validate_model_review(packet: dict[str, Any], review: dict[str, Any]) -> None:
    expected = {row["audit_id"] for row in packet["cards"]}
    actual = {row["audit_id"] for row in review.get("responses") or []}
    if len(actual) != len(review.get("responses") or []):
        raise ValueError("model review contains duplicate audit IDs")
    if actual != expected:
        raise ValueError(f"model review is incomplete: {len(expected - actual)} cards remain")


def audit_report(packet: dict[str, Any], labels: dict[str, Any], model_review: dict[str, Any]) -> dict[str, Any]:
    validate_label_file(packet, labels, require_complete=True)
    validate_model_review(packet, model_review)
    rows = model_review["responses"]
    blind_rows = labels["labels"]
    in_scope_rows = [row for row in rows if row["scope_verdict"] == "IN_SCOPE"]
    scorable = [row for row in in_scope_rows if row["human_classification"] in MODEL_LABELS]
    matches = sum(row["blind_label_match"] for row in scorable)
    scope_counts = Counter(row["scope_verdict"] for row in blind_rows)
    evidence_support_counts = Counter(row["evidence_support_verdict"] for row in blind_rows
                                      if row["scope_verdict"] == "IN_SCOPE")
    reason_support_counts = Counter(row["reason_support_verdict"] for row in in_scope_rows)
    verdict_counts = Counter(row["model_label_verdict"] for row in in_scope_rows)
    accepted = sum(row["evidence_support_verdict"] == "FULLY_SUPPORTED"
                   and row["reason_support_verdict"] == "FULLY_SUPPORTED"
                   and row["model_label_verdict"] == "AGREE" for row in in_scope_rows)
    return {
        "audit_report_schema_version": 1,
        "created_at": _now(),
        "status": "PROVISIONAL_MODEL_DECISION_AUDIT",
        "model": model_review.get("model"),
        "prompt_version": model_review.get("prompt_version"),
        "index_signature": packet["corpus"]["index_signature"],
        "sample": packet["selection"],
        "scope_counts": dict(sorted(scope_counts.items())),
        "out_of_scope_selection_rate": (
            scope_counts["OUT_OF_SCOPE"] / len(rows) if rows else None),
        "blind_claim_classification_alignment": {
            "cards": len(rows),
            "in_scope": len(in_scope_rows),
            "scored": len(scorable),
            "unable_to_determine": len(in_scope_rows) - len(scorable),
            "exact_matches": matches,
            "exact_match_rate": matches / len(scorable) if scorable else None,
        },
        "evidence_support_counts": dict(sorted(evidence_support_counts.items())),
        "reason_support_counts": dict(sorted(reason_support_counts.items())),
        "model_label_verdict_counts": dict(sorted(verdict_counts.items())),
        "accepted_decisions": accepted,
        "accepted_decision_rate": accepted / len(in_scope_rows) if in_scope_rows else None,
        "limitations": packet["limitations"] + [
            "No precision, recall, or corpus-level ranking metric is reported from this audit."
        ],
        "items": rows,
    }


def _labels_path(reviewer_id: str) -> Path:
    return DEFAULT_OUTPUT_DIR / f"{_slug(reviewer_id)}-blind-claim-decisions.json"


def _review_path(reviewer_id: str) -> Path:
    return DEFAULT_OUTPUT_DIR / f"{_slug(reviewer_id)}-model-review.json"


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Build 20 compact claim-and-evidence cards")
    prepare.add_argument("--report", default=str(DEFAULT_REPORT))
    prepare.add_argument("--index", default=str(DEFAULT_INDEX))
    prepare.add_argument("--rubric", default=str(DEFAULT_RUBRIC))
    prepare.add_argument("--output", default=str(DEFAULT_PACKET))
    prepare.add_argument("--sample-size", type=int, default=20)
    prepare.add_argument("--context-chars", type=int, default=600)

    label = subparsers.add_parser(
        "label", help="Audit selected-evidence support while model reason and label stay hidden")
    label.add_argument("--packet", default=str(DEFAULT_PACKET))
    label.add_argument("--reviewer", required=True)
    label.add_argument("--labels", default="")
    label.add_argument("--pager", action="store_true",
                       help="Open each compact card in a pager; off by default")
    label.add_argument("--max-cards", type=int, default=0,
                       help="Stop after this many new cards; 0 means finish")

    validate = subparsers.add_parser("validate", help="Validate blind claim-audit decisions")
    validate.add_argument("--packet", default=str(DEFAULT_PACKET))
    validate.add_argument("--labels", required=True)
    validate.add_argument("--allow-incomplete", action="store_true")

    review = subparsers.add_parser(
        "review-model", help="Reveal and audit the model reason and label after blind decisions")
    review.add_argument("--packet", default=str(DEFAULT_PACKET))
    review.add_argument("--report", default=str(DEFAULT_REPORT))
    review.add_argument("--labels", required=True)
    review.add_argument("--output", default="")

    report = subparsers.add_parser("report", help="Summarize the completed model-decision audit")
    report.add_argument("--packet", default=str(DEFAULT_PACKET))
    report.add_argument("--labels", required=True)
    report.add_argument("--model-review", required=True)
    report.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    if args.command == "prepare":
        packet = build_audit_packet(report_path=args.report, index_path=args.index,
                                    rubric_path=args.rubric, sample_size=args.sample_size,
                                    context_chars=args.context_chars)
        write_audit_packet(packet, args.output)
        _print_json({"status": "READY", "packet": args.output,
                     "cards": len(packet["cards"]),
                     "population": packet["selection"]["assessment_population"],
                     "claim_visible_model_reason_and_label_hidden": True,
                     "next": ("Run: .venv/bin/python scripts/eval_audit_digest_claims.py "
                              "label --reviewer alfonso")})
        return 0
    packet = _read_json(args.packet)
    if args.command == "label":
        labels_path = Path(args.labels) if args.labels else _labels_path(args.reviewer)
        status = run_blind_labels(packet, labels_path, reviewer_id=args.reviewer,
                                  use_pager=args.pager, max_cards=args.max_cards)
        next_step = ("Rerun the same command to continue." if status["remaining"] else
                     ("Run review-model with --labels " + str(labels_path)))
        _print_json({**status, "labels_path": str(labels_path), "next": next_step})
        return 0
    if args.command == "validate":
        _print_json(validate_label_file(packet, _read_json(args.labels),
                                        require_complete=not args.allow_incomplete))
        return 0
    if args.command == "review-model":
        labels = _read_json(args.labels)
        reviewer_id = str(labels.get("reviewer_id") or "reviewer")
        output = Path(args.output) if args.output else _review_path(reviewer_id)
        result = run_model_review(packet, labels, _read_json(args.report), output)
        _print_json({"status": "MODEL_DECISIONS_REVIEWED", "output": str(output),
                     "cards": len(result["responses"]),
                     "next": "Run the report command; do not interpret it as recall."})
        return 0
    if args.command == "report":
        result = audit_report(packet, _read_json(args.labels), _read_json(args.model_review))
        result["provenance"] = {"labels": args.labels, "model_review": args.model_review,
                                "source_report": packet["model_result_reference"]["report_path"]}
        _write_json(args.output, result)
        _print_json({"status": result["status"], "output": args.output,
                     "cards": result["blind_claim_classification_alignment"]["cards"],
                     "accepted_decisions": result["accepted_decisions"],
                     "limitations": result["limitations"]})
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
