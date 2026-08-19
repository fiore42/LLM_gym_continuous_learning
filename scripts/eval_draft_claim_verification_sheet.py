#!/usr/bin/env python3
"""Draft claim-to-evidence verification sheets for human confirmation."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.shared.config import load_dotenv
from llm_gym.agent.model_client import model_client_from_environment
from llm_gym.agent.prompt_registry import VERIFICATION_PROMPT_ROOT, load_prompt


VERDICTS = {"proven", "not_proven", "unclear"}
def verification_prompt(version: str | None = None):
    """Load the versioned drafter prompt from its own registry family."""
    return load_prompt(version=version, root=VERIFICATION_PROMPT_ROOT)


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def _parse_model_json(raw: str) -> dict[str, Any]:
    candidates = [raw.strip()]
    candidates.extend(match.strip() for match in _JSON_FENCE.findall(raw))
    first_object = raw.find("{")
    last_object = raw.rfind("}")
    if first_object >= 0 and last_object > first_object:
        candidates.append(raw[first_object:last_object + 1].strip())
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    preview = " ".join(raw.strip().split())[:400]
    raise ValueError(f"model response must contain a JSON object; preview: {preview!r}")


def _trace_parts(payload: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    attempts = payload.get("attempts") or []
    synthesis = None
    if isinstance(attempts, list):
        for attempt in reversed(attempts):
            if isinstance(attempt, dict) and isinstance(attempt.get("synthesis"), dict):
                synthesis = attempt["synthesis"]
                break
    synthesis = synthesis or payload.get("synthesis")
    if not isinstance(synthesis, dict) or not isinstance(synthesis.get("answer"), str):
        raise ValueError("trace must contain synthesis.answer")
    evidence = payload.get("evidence") or payload.get("retrieved_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("trace must contain evidence or retrieved_evidence")
    if any(not isinstance(item, dict) or not item.get("evidence_id") for item in evidence):
        raise ValueError("every evidence item requires evidence_id")
    return str(payload.get("question") or ""), synthesis["answer"], evidence


def validate_proposals(proposals: Any, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(proposals, list):
        raise ValueError("model response requires a claims array")
    snippets = {str(item["evidence_id"]): str(item.get("snippet") or "") for item in evidence}
    validated = []
    for raw in proposals:
        if not isinstance(raw, dict):
            raise ValueError("each claim proposal must be an object")
        claim = str(raw.get("claim") or "").strip()
        verdict = str(raw.get("verdict") or "").strip().lower()
        evidence_id = str(raw.get("evidence_id") or "")
        quote = str(raw.get("quote") or "").strip()
        if not claim or verdict not in VERDICTS or not evidence_id or not quote:
            raise ValueError("claim proposals require claim, valid verdict, evidence_id, and quote")
        if evidence_id not in snippets:
            quote_valid = False
            flag = "unknown_evidence_id"
        else:
            quote_valid = _normalized(quote) in _normalized(snippets[evidence_id])
            flag = None if quote_valid else "quote_not_found_in_evidence_snippet"
        validated.append({
            "claim": claim,
            "verdict": verdict if quote_valid else "unclear",
            "evidence_id": evidence_id,
            "quote": quote,
            "quote_valid": quote_valid,
            "flag": flag,
        })
    return validated


def draft_claims(trace: dict[str, Any], client: Any, *, model: str,
                 max_output_tokens: int = 1200,
                 prompt_version: str | None = None) -> dict[str, Any]:
    question, answer, evidence = _trace_parts(trace)
    evidence_text = "\n\n".join(
        f"EVIDENCE_ID: {item['evidence_id']}\nTEXT: {item.get('snippet', '')}"
        for item in evidence
    )
    prompt = verification_prompt(prompt_version)
    user_prompt = prompt.user_template.format(
        question=question, answer=answer, evidence_text=evidence_text
    )
    raw = client.complete(system=prompt.system_template, user=user_prompt, model=model,
                          max_output_tokens=max_output_tokens)
    payload = _parse_model_json(raw)
    proposals = validate_proposals(payload.get("claims"), evidence)
    return {
        "verification_version": 1,
        "question": question,
        "answer": answer,
        "model": model,
        "prompt": {
            "prompt_id": prompt.prompt_id,
            "prompt_version": prompt.prompt_version,
            "sha256": prompt.sha256,
            "system_prompt": prompt.system_template,
            "rendered_user_prompt": user_prompt,
        },
        "evidence": evidence,
        "retrieval_evidence": trace.get("retrieval_evidence") or trace.get("live_retrieved_evidence") or [],
        "claims": proposals,
        "usage": getattr(client, "last_usage", {}),
        "advisory_only": True,
    }


def render_markdown(draft: dict[str, Any]) -> str:
    evidence_by_id = {
        str(item.get("evidence_id")): item
        for item in draft.get("evidence") or []
        if isinstance(item, dict) and item.get("evidence_id")
    }

    def blockquote(value: Any) -> list[str]:
        return [f"> {line}" if line else ">" for line in str(value).splitlines()]

    lines = [
        "# Assisted verification",
        "",
        "[Project rules](../../PROJECT_RULES.md)",
        "",
        "Advisory draft only. Confirm each row; the drafter is not authoritative.",
        "",
    ]
    for index, item in enumerate(draft["claims"], start=1):
        evidence_id = item["evidence_id"]
        evidence = evidence_by_id.get(evidence_id, {})
        flag = f" ({item['flag']})" if item.get("flag") else ""
        lines.extend([
            f"## Claim {index}",
            "",
            f"**Claim:** {item['claim']}",
            f"**Draft verdict:** {item['verdict'].upper()}{flag}",
            "",
            f"**Evidence ID:** `{evidence_id}`",
            f"**Source:** [{evidence.get('title') or 'Untitled source'}]({evidence.get('canonical_url') or '#'})",
            f"**Locator:** {evidence.get('locator') or 'not provided'}",
            "",
            "**Full supplied evidence snippet:**",
            *blockquote(evidence.get("snippet") or "[snippet unavailable]"),
            "",
            "**Drafter's supporting quote:**",
            *blockquote(item["quote"]),
            "",
            "**Human response:** agree? `[y/n/edit]`",
            "",
        ])

    lines.extend(["## All supplied evidence", "", "The complete frozen evidence set shown to the drafter:", ""])
    for index, evidence in enumerate(draft.get("evidence") or [], start=1):
        evidence_id = evidence.get("evidence_id", "unknown")
        lines.extend([
            f"### Evidence {index}: `{evidence_id}`",
            f"**Source:** [{evidence.get('title') or 'Untitled source'}]({evidence.get('canonical_url') or '#'})",
            f"**Locator:** {evidence.get('locator') or 'not provided'}",
            "",
            *blockquote(evidence.get("snippet") or "[snippet unavailable]"),
            "",
        ])

    retrieval_evidence = draft.get("retrieval_evidence") or []
    if retrieval_evidence:
        lines.extend([
            "## Additional live-retrieval evidence",
            "",
            "These items were retrieved for the live question but were **not supplied to the frozen-evidence suite model**. They are included so a human can assess whether the frozen case missed better evidence. They must not be used to validate the stored answer without rerunning synthesis.",
            "",
        ])
        for index, evidence in enumerate(retrieval_evidence, start=1):
            evidence_id = evidence.get("evidence_id", "unknown")
            lines.extend([
                f"### Live evidence {index}: `{evidence_id}`",
                f"**Source:** [{evidence.get('title') or 'Untitled source'}]({evidence.get('canonical_url') or '#'})",
                f"**Locator:** {evidence.get('locator') or 'not provided'}",
                "",
                *blockquote(evidence.get("snippet") or "[snippet unavailable]"),
                "",
            ])
    return "\n".join(lines) + "\n"


def apply_labels(draft: dict[str, Any], responses: list[dict[str, Any]]) -> dict[str, Any]:
    by_claim = {str(item.get("claim")): item for item in responses if isinstance(item, dict)}
    labels = []
    for proposal in draft.get("claims") or []:
        response = by_claim.get(proposal["claim"], {})
        human = str(response.get("human_verdict") or response.get("verdict") or "").strip().lower()
        if human not in VERDICTS:
            raise ValueError(f"missing valid human_verdict for claim: {proposal['claim']}")
        labels.append({
            "criterion": "claims_supported",
            "claim": proposal["claim"],
            "drafted_verdict": proposal["verdict"],
            "human_verdict": human,
            "agreed": human == proposal["verdict"],
        })
    return {"labels_version": 1, "advisory_only": True, "labels": labels}


def agreement_report(label_paths: list[Path]) -> dict[str, Any]:
    tally: dict[str, dict[str, int]] = {}
    total = 0
    for path in label_paths:
        payload = _read_json(path)
        for label in payload.get("labels") or []:
            criterion = str(label.get("criterion") or "claims_supported")
            bucket = tally.setdefault(criterion, {"agreed": 0, "disagreed": 0, "total": 0})
            agreed = bool(label.get("agreed"))
            bucket["agreed" if agreed else "disagreed"] += 1
            bucket["total"] += 1
            total += 1
    for bucket in tally.values():
        bucket["agreement_rate"] = bucket["agreed"] / bucket["total"] if bucket["total"] else 0.0
    return {"agreement_version": 1, "authoritative_labels": "human_verdict", "files": len(label_paths),
            "total_labels": total, "by_criterion": tally}


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", help="Trace JSON containing synthesis and evidence")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--markdown", help="Readable review-sheet Markdown path")
    parser.add_argument("--model", default=os.environ.get("JUDGE_MODEL", ""))
    parser.add_argument("--max-output-tokens", type=int, default=1200)
    parser.add_argument("--apply-labels", help="Responses JSON to apply to --draft")
    parser.add_argument("--draft", help="Draft verification JSON used with --apply-labels")
    parser.add_argument("--agreement-report", nargs="?", const="data/verification-labels",
                        help="Aggregate label files from this directory")
    args = parser.parse_args()

    try:
        if args.agreement_report is not None:
            paths = sorted(Path(args.agreement_report).glob("*.json"))
            result = agreement_report(paths)
            _write_json(args.output, result)
            print(json.dumps(result, indent=2))
            return 0
        if args.apply_labels:
            if not args.draft:
                parser.error("--draft is required with --apply-labels")
            result = apply_labels(_read_json(args.draft), _read_json(args.apply_labels))
            _write_json(args.output, result)
            print(json.dumps(result, indent=2))
            return 0
        if not args.trace:
            parser.error("--trace is required when drafting verification")
        if not args.model:
            parser.error("--model or JUDGE_MODEL is required")
        trace = _read_json(args.trace)
        client = model_client_from_environment(prefix="JUDGE")
        result = draft_claims(trace, client, model=args.model,
                              max_output_tokens=args.max_output_tokens)
        _write_json(args.output, result)
        markdown_path = args.markdown or str(Path(args.output).with_suffix(".md"))
        Path(markdown_path).write_text(render_markdown(result), encoding="utf-8")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
