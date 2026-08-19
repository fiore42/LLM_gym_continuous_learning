import importlib.util
import inspect
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from llm_gym.corpus.evidence import index_signature


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "eval_audit_digest_claims.py"
SPEC = importlib.util.spec_from_file_location("digest_claim_audit", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_terminal_line_editing_loads_readline_when_available():
    readline_available = importlib.util.find_spec("readline") is not None
    assert MODULE.LINE_EDITING_ENABLED is readline_available
    if readline_available:
        assert "readline" in sys.modules


def test_compact_cards_do_not_use_a_pager_by_default():
    parameter = inspect.signature(MODULE.run_blind_labels).parameters["use_pager"]
    assert parameter.default is False


def test_input_key_indexes_disambiguate_reused_keys(capsys):
    MODULE._print_blind_input_index()
    blind = capsys.readouterr().out
    assert "Scope: y = in scope | n = out of scope | u = unclear (n/u skip support and significance)" in blind
    assert "Evidence-set support: f = fully supported" in blind
    assert "c = show context" in blind
    assert "u = unclear" in blind
    assert "u = unsupported" in blind
    assert "x = unable to determine" in blind
    assert "Digest label justified by the evidence set: s = significant | i = incremental" in blind

    MODULE._print_reveal_input_index(labels_match=False)
    reveal = capsys.readouterr().out
    assert "Reason support: f = fully supported" in reveal
    assert "Different model label: y = reasonable alternative" in reveal

    MODULE._print_reveal_input_index(labels_match=True)
    reveal_match = capsys.readouterr().out
    assert "exact blind match — AGREE is recorded automatically" in reveal_match


def _fixture(tmp_path: Path, *, per_label: int = 2):
    index = tmp_path / "evidence.sqlite3"
    connection = sqlite3.connect(index)
    connection.executescript(
        """
        CREATE TABLE evidence_items (
          evidence_id TEXT PRIMARY KEY, platform TEXT, source_key TEXT,
          canonical_url TEXT, published_at TEXT, title TEXT, author TEXT, kind TEXT
        );
        CREATE TABLE evidence_chunks (
          evidence_id TEXT, chunk_index INTEGER, text TEXT
        );
        """
    )
    assessments = []
    number = 0
    for predicted in MODULE.MODEL_LABELS:
        for _ in range(per_label):
            number += 1
            item_id = f"item-{number}"
            item = {
                "evidence_id": item_id,
                "platform": "youtube",
                "source_key": "source",
                "canonical_url": f"https://example.test/{number}",
                "published_at": "2026-08-01T00:00:00+00:00",
                "title": f"Item {number}",
                "author": "Author",
                "kind": "video",
            }
            connection.execute(
                "INSERT INTO evidence_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(item[key] for key in (
                    "evidence_id", "platform", "source_key", "canonical_url",
                    "published_at", "title", "author", "kind")),
            )
            quote = f"Measured result for {item_id} is 42 percent."
            second_quote = f"The change for {item_id} was deployed."
            connection.execute("INSERT INTO evidence_chunks VALUES (?, ?, ?)",
                               (item_id, 0, f"Opening context for {item_id}. {quote} "
                                f"{second_quote} Closing context."))
            assessments.append({
                "item_id": item_id,
                "claimed_change": f"A measured and deployed change occurred for {item_id}.",
                "reason": f"The passage reports a measured result for {item_id}.",
                "significance": predicted,
                "supporting_evidence": [
                    {"claim_component": "The result was measured.", "quote": quote},
                    {"claim_component": "The change was deployed.", "quote": second_quote},
                ],
                "canonical_url": item["canonical_url"],
                "published_at": item["published_at"],
                "title": item["title"],
            })
    connection.commit()
    connection.close()
    signature = index_signature(index)
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "model": "test-model",
        "prompt_version": "significance-v2",
        "prompt_sha256": "a" * 64,
        "window": {"index_signature": signature},
        "assessments": assessments,
    }))
    rubric = tmp_path / "rubric.json"
    rubric.write_text(json.dumps({
        "rubric_id": "digest_claim_audit",
        "rubric_version": 1,
        "blind_question": "What does this passage establish?",
        "passage_labels": {label: label for label in MODULE.HUMAN_CLASSIFICATIONS},
    }))
    return index, report, rubric


def _packet(tmp_path: Path):
    index, report, rubric = _fixture(tmp_path)
    packet = MODULE.build_audit_packet(
        report_path=report, index_path=index, rubric_path=rubric,
        sample_size=8, context_chars=20)
    return packet, report


def _complete_labels(packet, reviewer="alfonso", overrides=None):
    overrides = overrides or {}
    labels = MODULE.new_label_file(packet, reviewer)
    for card in packet["cards"]:
        MODULE.add_claim_decision(
            labels, card,
            scope_verdict="IN_SCOPE",
            evidence_support_verdict="FULLY_SUPPORTED",
            human_label=overrides.get(card["audit_id"], "SIGNIFICANT"),
            rationale="The displayed passage supports this decision.")
    return labels


def _complete_review(packet, labels, report):
    responses = [{"audit_id": card["audit_id"],
                  "reason_support_verdict": "FULLY_SUPPORTED",
                  "model_label_verdict": "AGREE",
                  "audit_note": ""} for card in packet["cards"]]
    return MODULE.build_model_review(packet, labels, report, responses)


def test_prepare_creates_compact_blind_cards_stratified_by_hidden_label(tmp_path):
    packet, _ = _packet(tmp_path)
    assert len(packet["cards"]) == 8
    assert packet["selection"]["allocation_by_hidden_model_label"] == {
        label: 2 for label in MODULE.MODEL_LABELS
    }
    for card in packet["cards"]:
        assert "source_text" not in card
        assert card["platform"] == "youtube"
        assert card["source_key"] == "source"
        assert card["claim_to_evaluate"].startswith("A measured and deployed change occurred")
        assert "reason" not in card
        assert "significance" not in card
        assert len(card["supporting_evidence"]) == 2
        assert card["supporting_evidence"][0]["quote"].startswith("Measured result")
        assert len(card["supporting_evidence"][0]["context_before"]) <= 21
        assert len(card["supporting_evidence"][0]["context_after"]) <= 21


def test_prepare_refuses_a_different_corpus_identity(tmp_path):
    index, report, rubric = _fixture(tmp_path)
    payload = json.loads(report.read_text())
    payload["window"]["index_signature"] = "different"
    report.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="corpus identity mismatch"):
        MODULE.build_audit_packet(report_path=report, index_path=index,
                                  rubric_path=rubric, sample_size=8)


def test_prepare_refuses_historical_single_quote_reports(tmp_path):
    index, report, rubric = _fixture(tmp_path)
    payload = json.loads(report.read_text())
    for assessment in payload["assessments"]:
        assessment["supporting_quote"] = assessment.pop("supporting_evidence")[0]["quote"]
    payload["prompt_version"] = "significance-v1"
    report.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="requires a significance-v2 report"):
        MODULE.build_audit_packet(report_path=report, index_path=index,
                                  rubric_path=rubric, sample_size=8)


def test_context_requires_the_model_quote_to_exist():
    with pytest.raises(ValueError, match="does not occur"):
        MODULE.passage_context("This source says something else.", "Missing quote", context_chars=10)


def test_optional_context_is_hidden_until_requested_and_cannot_answer_for_reviewer(capsys):
    card = {"supporting_evidence": [{
        "context_before": "Before detail.", "quote": "This changed.",
        "context_after": "After detail.",
    }]}
    answers = iter(["c", "p"])
    verdict = MODULE._prompt_evidence_support(card, lambda _: next(answers))
    output = capsys.readouterr().out
    assert verdict == "PARTIALLY_SUPPORTED"
    assert "OPTIONAL INTERPRETATION CONTEXT" in output
    assert "cannot supply missing claim facts" in output
    assert "BEFORE: Before detail." in output


def test_blind_passage_label_requires_a_rationale(tmp_path):
    packet, _ = _packet(tmp_path)
    labels = MODULE.new_label_file(packet, "alfonso")
    with pytest.raises(ValueError, match="rationale is required"):
        MODULE.add_claim_decision(labels, packet["cards"][0],
                                  scope_verdict="IN_SCOPE",
                                  evidence_support_verdict="FULLY_SUPPORTED",
                                  human_label="SIGNIFICANT", rationale="")
    MODULE.add_claim_decision(labels, packet["cards"][0],
                              scope_verdict="IN_SCOPE",
                              evidence_support_verdict="UNCLEAR",
                              human_label="UNABLE_TO_DETERMINE",
                              rationale="The displayed context is insufficient.")
    assert labels["labels"][0]["human_classification"] == "UNABLE_TO_DETERMINE"
    assert labels["labels"][0]["source_key"] == "source"
    assert labels["labels"][0]["platform"] == "youtube"


def test_out_of_scope_decision_skips_support_and_significance(tmp_path):
    packet, _ = _packet(tmp_path)
    labels = MODULE.new_label_file(packet, "alfonso")
    MODULE.add_claim_decision(
        labels, packet["cards"][0], scope_verdict="OUT_OF_SCOPE",
        evidence_support_verdict="NOT_APPLICABLE", human_label="OUT_OF_SCOPE",
        rationale="This is a general security claim without an AI connection.")
    assert labels["labels"][0]["scope_verdict"] == "OUT_OF_SCOPE"
    with pytest.raises(ValueError, match="OUT_OF_SCOPE requires"):
        MODULE.add_claim_decision(
            labels, packet["cards"][1], scope_verdict="OUT_OF_SCOPE",
            evidence_support_verdict="UNCLEAR", human_label="UNABLE_TO_DETERMINE",
            rationale="Invalid combination.")


def test_model_review_rejects_an_invalid_reason_support_verdict(tmp_path):
    packet, report_path = _packet(tmp_path)
    labels = _complete_labels(packet)
    with pytest.raises(ValueError, match="support_verdict"):
        MODULE.build_model_review(
            packet, labels, json.loads(report_path.read_text()),
            [{"audit_id": packet["cards"][0]["audit_id"],
              "reason_support_verdict": "MAYBE", "model_label_verdict": "AGREE"}])


def test_reveal_phase_explains_exact_match_and_does_not_ask_redundant_label_question(
        tmp_path, capsys):
    packet, report_path = _packet(tmp_path)
    MODULE.write_audit_packet(packet, tmp_path / "packet.json")
    report = json.loads(report_path.read_text())
    model_labels = {row["item_id"]: row["significance"] for row in report["assessments"]}
    labels = _complete_labels(packet, overrides=model_labels)
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        if prompt.startswith("Does the selected evidence"):
            return "f"
        if prompt.startswith("Optional audit note"):
            return ""
        raise AssertionError(f"unexpected prompt for an exact label match: {prompt}")

    output = tmp_path / "model-review.json"
    result = MODULE.run_model_review(packet, labels, report, output, input_fn=answer)
    displayed = capsys.readouterr().out
    assert "MODEL-DECISION REVEAL PHASE" in displayed
    assert "BLIND LABEL COMPARISON: EXACT MATCH" in displayed
    assert "AGREE will be recorded automatically" in displayed
    assert "reasonable alternative?" not in "".join(prompts)
    assert {row["model_label_verdict"] for row in result["responses"]} == {"AGREE"}


def test_reveal_phase_underlines_difference_and_asks_if_model_label_is_reasonable(
        tmp_path, capsys):
    packet, report_path = _packet(tmp_path)
    MODULE.write_audit_packet(packet, tmp_path / "packet.json")
    report = json.loads(report_path.read_text())
    model_labels = {row["item_id"]: row["significance"] for row in report["assessments"]}
    first_id = packet["cards"][0]["audit_id"]
    model_labels[first_id] = next(
        label for label in MODULE.MODEL_LABELS if label != model_labels[first_id])
    labels = _complete_labels(packet, overrides=model_labels)
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        if prompt.startswith("Does the selected evidence"):
            return "f"
        if prompt.startswith("Is the model's different label"):
            return "n"
        if prompt.startswith("Optional audit note"):
            return ""
        raise AssertionError(f"unexpected prompt: {prompt}")

    result = MODULE.run_model_review(
        packet, labels, report, tmp_path / "model-review.json", input_fn=answer)
    displayed = capsys.readouterr().out
    first = next(row for row in result["responses"] if row["audit_id"] == first_id)
    assert "BLIND LABEL COMPARISON: DIFFERENT" in displayed
    assert "DIFFERENT-LABEL REASONABLENESS" in displayed
    assert first["model_label_verdict"] == "DISAGREE"
    assert any("reasonable alternative" in prompt for prompt in prompts)


def test_report_is_explicitly_an_audit_and_never_reports_precision_or_recall(tmp_path):
    packet, report_path = _packet(tmp_path)
    labels = _complete_labels(packet)
    review = _complete_review(packet, labels, json.loads(report_path.read_text()))
    review["responses"][0]["reason_support_verdict"] = "PARTIALLY_SUPPORTED"
    result = MODULE.audit_report(packet, labels, review)
    assert result["status"] == "PROVISIONAL_MODEL_DECISION_AUDIT"
    assert result["accepted_decisions"] == 7
    assert result["accepted_decision_rate"] == 0.875
    assert result["scope_counts"] == {"IN_SCOPE": 8}
    assert result["out_of_scope_selection_rate"] == 0.0
    assert result["evidence_support_counts"] == {"FULLY_SUPPORTED": 8}
    assert result["reason_support_counts"] == {
        "FULLY_SUPPORTED": 7,
        "PARTIALLY_SUPPORTED": 1,
    }
    serialized = json.dumps(result).lower()
    assert '"precision"' not in serialized
    assert '"recall"' not in serialized
    assert any("not missed claims" in limitation for limitation in result["limitations"])


def test_report_counts_out_of_scope_as_selection_failure_not_significance(tmp_path):
    packet, report_path = _packet(tmp_path)
    labels = MODULE.new_label_file(packet, "alfonso")
    out_of_scope = packet["cards"][0]["audit_id"]
    for card in packet["cards"]:
        if card["audit_id"] == out_of_scope:
            MODULE.add_claim_decision(
                labels, card, scope_verdict="OUT_OF_SCOPE",
                evidence_support_verdict="NOT_APPLICABLE", human_label="OUT_OF_SCOPE",
                rationale="This is outside the AI and agent scope.")
        else:
            MODULE.add_claim_decision(
                labels, card, scope_verdict="IN_SCOPE",
                evidence_support_verdict="FULLY_SUPPORTED", human_label="SIGNIFICANT",
                rationale="The displayed passage supports this decision.")
    responses = [{
        "audit_id": card["audit_id"],
        "reason_support_verdict": (
            "NOT_APPLICABLE" if card["audit_id"] == out_of_scope else "FULLY_SUPPORTED"),
        "model_label_verdict": (
            "NOT_APPLICABLE" if card["audit_id"] == out_of_scope else "AGREE"),
        "audit_note": "",
    } for card in packet["cards"]]
    review = MODULE.build_model_review(
        packet, labels, json.loads(report_path.read_text()), responses)
    result = MODULE.audit_report(packet, labels, review)
    assert result["scope_counts"] == {"IN_SCOPE": 7, "OUT_OF_SCOPE": 1}
    assert result["out_of_scope_selection_rate"] == 0.125
    assert result["evidence_support_counts"] == {"FULLY_SUPPORTED": 7}
    assert result["blind_claim_classification_alignment"]["in_scope"] == 7


def test_prepare_entry_point_writes_readable_cards(tmp_path, capsys):
    index, report, rubric = _fixture(tmp_path)
    output = tmp_path / "audit" / "packet.json"
    exit_code = MODULE.main([
        "prepare", "--report", str(report), "--index", str(index),
        "--rubric", str(rubric), "--output", str(output),
        "--sample-size", "8", "--context-chars", "20",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cards"] == 8
    assert output.exists()
    assert len(list((output.parent / "cards").glob("*.txt"))) == 8
    first_card = sorted((output.parent / "cards").glob("*.txt"))[0].read_text()
    assert "YOUTUBE CHANNEL: source" in first_card
    assert "PLATFORM: youtube" in first_card
    assert "AI-SELECTED EVIDENCE 1/2" in first_card
    assert "AI-SELECTED EVIDENCE 2/2" in first_card
    assert "CONTEXT BEFORE" not in first_card
    assert "CONTEXT AFTER" not in first_card
