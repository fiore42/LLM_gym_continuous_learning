import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "eval_draft_claim_verification_sheet.py"
SPEC = importlib.util.spec_from_file_location("draft_verification", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_fabricated_quote_is_downgraded():
    result = MODULE.validate_proposals([
        {"claim": "Agents use memory", "verdict": "proven", "evidence_id": "e1",
         "quote": "This sentence is fabricated."}
    ], [{"evidence_id": "e1", "snippet": "Agents use memory."}])
    assert result[0]["verdict"] == "unclear"
    assert result[0]["quote_valid"] is False


def test_model_json_fence_and_preamble_are_accepted():
    payload = MODULE._parse_model_json('Here is the review:\n```json\n{"claims": []}\n```')
    assert payload == {"claims": []}


def test_unknown_evidence_id_is_downgraded():
    result = MODULE.validate_proposals([
        {"claim": "A claim", "verdict": "proven", "evidence_id": "multiple",
         "quote": "A quote."}
    ], [{"evidence_id": "e1", "snippet": "A quote."}])
    assert result[0]["verdict"] == "unclear"
    assert result[0]["flag"] == "unknown_evidence_id"


def test_agreement_report_tally(tmp_path):
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"labels": [
        {"criterion": "claims_supported", "agreed": True},
        {"criterion": "claims_supported", "agreed": False},
        {"criterion": "answer_complete", "agreed": True},
    ]}))
    result = MODULE.agreement_report([path])
    assert result["total_labels"] == 3
    assert result["by_criterion"]["claims_supported"]["agreed"] == 1
    assert result["by_criterion"]["claims_supported"]["agreement_rate"] == 0.5


def test_labels_round_trip():
    draft = {"claims": [{"claim": "Agents use memory", "verdict": "proven"}]}
    result = MODULE.apply_labels(draft, [{"claim": "Agents use memory", "human_verdict": "proven"}])
    assert result["labels"][0] == {
        "criterion": "claims_supported",
        "claim": "Agents use memory",
        "drafted_verdict": "proven",
        "human_verdict": "proven",
        "agreed": True,
    }


def test_markdown_includes_full_supplied_evidence():
    markdown = MODULE.render_markdown({
        "claims": [{
            "claim": "A claim",
            "verdict": "proven",
            "evidence_id": "abc",
            "quote": "exact words",
        }],
        "evidence": [{
            "evidence_id": "abc",
            "title": "Example source",
            "canonical_url": "https://example.test/source",
            "locator": "00:01:02",
            "snippet": "The full supplied sentence with exact words.",
        }],
        "retrieval_evidence": [{
            "evidence_id": "live-1",
            "title": "Live candidate",
            "canonical_url": "https://example.test/live",
            "snippet": "A live candidate not shown to the frozen suite model.",
        }],
    })
    assert "The full supplied sentence with exact words." in markdown
    assert "Example source" in markdown
    assert "00:01:02" in markdown
    assert "A live candidate not shown to the frozen suite model." in markdown
    assert "Additional live-retrieval evidence" in markdown


class RecordingClient:
    def __init__(self, payload):
        self.payload = payload
        self.last_kwargs = None
        self.last_usage = {}

    def complete(self, **kwargs):
        self.last_kwargs = kwargs
        return self.payload


TRACE = {
    "question": "How do agents use memory?",
    "attempts": [{"synthesis": {"answer": "Agents keep prior context.",
                                "citation_ids": ["e1"]}}],
    "retrieved_evidence": [{"evidence_id": "e1", "snippet": "Agents keep prior context."}],
}


def test_drafter_prompt_comes_from_the_registry_and_is_recorded():
    """The drafter must carry the same provenance as synthesis.

    A prompt defined as a module constant leaves no record of which version
    produced a verification sheet, so drafter versions cannot be compared the
    way synthesis versions are.
    """
    client = RecordingClient(json.dumps({"claims": [
        {"claim": "Agents keep prior context.", "verdict": "proven",
         "evidence_id": "e1", "quote": "Agents keep prior context."}
    ]}))
    sheet = MODULE.draft_claims(TRACE, client, model="test-model")
    prompt = sheet["prompt"]
    assert prompt["prompt_id"] == "verification"
    assert prompt["prompt_version"].startswith("verification-v")
    assert len(prompt["sha256"]) == 64
    # The prompt actually sent must be the registry one, not a stale copy.
    assert client.last_kwargs["system"] == prompt["system_prompt"]
    assert "How do agents use memory?" in client.last_kwargs["user"]


def test_prompt_families_do_not_share_a_directory():
    """load_prompt() returns the highest version_number in its root.

    If two families shared a directory, the second to reach a higher number
    would silently become the other family's default.
    """
    from llm_gym.agent.prompt_registry import (PROMPT_ROOT, VERIFICATION_PROMPT_ROOT,
                                               load_prompt)
    assert PROMPT_ROOT != VERIFICATION_PROMPT_ROOT
    assert load_prompt(root=PROMPT_ROOT).prompt_id == "agent_task_synthesis"
    assert load_prompt(root=VERIFICATION_PROMPT_ROOT).prompt_id == "verification"
    for root in (PROMPT_ROOT, VERIFICATION_PROMPT_ROOT):
        ids = {json.loads(p.read_text())["prompt_id"] for p in root.glob("*.json")}
        assert len(ids) == 1, f"{root} mixes prompt families: {ids}"
