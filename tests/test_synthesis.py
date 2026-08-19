import json
import unittest

from llm_gym.shared.settings import agent_parameters
from llm_gym.agent.synthesis import MAX_OUTPUT_TOKENS, PROMPT_VERSION, SynthesisRequest, synthesize


EVIDENCE = ({"evidence_id": "e1", "canonical_url": "https://example.test/1",
             "locator": "00:01", "snippet": "Agents store useful context."},)


class FakeModel:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        payload = dict(self.payload)
        if "evidence_assessment" not in payload:
            ids = [line.split("\n", 1)[0] for line in kwargs["user"].split("EVIDENCE_ID: ")[1:]]
            payload["evidence_assessment"] = [
                {"evidence_id": evidence_id, "relevant": True, "reason": "Relevant test evidence."}
                for evidence_id in ids
            ]
        return json.dumps(payload)


class SynthesisTests(unittest.TestCase):
    def test_json_inside_markdown_fence_is_accepted(self):
        client = FakeModel({
            "answer": "Agents store context.", "classification": "SUPPORTED", "citation_ids": ["e1"]
        })
        original = client.complete
        client.complete = lambda **kwargs: "Here is the result:\n```json\n" + original(**kwargs) + "\n```"
        result = synthesize(SynthesisRequest("Question", EVIDENCE, "test-model"), client)
        self.assertEqual(result.answer, "Agents store context.")

    def test_malformed_json_includes_bounded_preview(self):
        client = FakeModel({"answer": "not used"})
        client.complete = lambda **kwargs: "not JSON " + ("x" * 1000)
        with self.assertRaisesRegex(ValueError, "preview") as raised:
            synthesize(SynthesisRequest("Question", EVIDENCE, "test-model"), client)
        self.assertLess(len(str(raised.exception)), 500)

    def test_injected_model_produces_citation_validated_result(self):
        client = FakeModel({"answer": "Agents store context.", "classification": "SUPPORTED", "citation_ids": ["e1"]})
        result = synthesize(SynthesisRequest("How do agents use memory?", EVIDENCE, "test-model"), client)
        self.assertEqual(result.citation_ids, ("e1",))
        self.assertTrue(result.validation["passed"])
        self.assertEqual(client.calls[0]["model"], "test-model")
        # Assert against the registry default rather than a literal version, so
        # this test does not need editing on every prompt bump.
        self.assertEqual(result.prompt["prompt_version"], PROMPT_VERSION)
        self.assertIn("How do agents use memory?", result.prompt["rendered_user_prompt"])
        self.assertIn("EVIDENCE_ID: e1", result.prompt["rendered_user_prompt"])

    def test_unknown_citation_is_rejected(self):
        client = FakeModel({"answer": "Unsupported.", "classification": "SUPPORTED", "citation_ids": ["unknown"]})
        with self.assertRaisesRegex(ValueError, "unknown citation"):
            synthesize(SynthesisRequest("Question", EVIDENCE, "test-model"), client)

    def test_missing_evidence_assessment_is_rejected(self):
        client = FakeModel({"answer": "Supported.", "classification": "SUPPORTED", "citation_ids": ["e1"]})
        client.payload = {**client.payload, "evidence_assessment": None}
        with self.assertRaisesRegex(ValueError, "evidence_assessment"):
            synthesize(SynthesisRequest("Question", EVIDENCE, "test-model"), client)

    def test_missing_evidence_is_rejected_before_model_call(self):
        client = FakeModel({"answer": "No", "classification": "SUPPORTED", "citation_ids": ["e1"]})
        with self.assertRaisesRegex(ValueError, "requires retrieved evidence"):
            synthesize(SynthesisRequest("Question", (), "test-model"), client)
        self.assertFalse(client.calls)

    def test_unscoped_corpus_claim_is_rejected(self):
        client = FakeModel({
            "answer": "The corpus proves that agents need memory.",
            "classification": "SUPPORTED",
            "citation_ids": ["e1"],
        })
        with self.assertRaisesRegex(ValueError, "corpus-wide"):
            synthesize(SynthesisRequest("Question", EVIDENCE, "test-model"), client)

    def test_retrieval_scoped_claim_is_accepted(self):
        client = FakeModel({
            "answer": "The retrieved evidence supports a role for agent memory.",
            "classification": "SUPPORTED",
            "citation_ids": ["e1"],
        })
        result = synthesize(SynthesisRequest("Question", EVIDENCE, "test-model"), client)
        self.assertTrue(result.validation["retrieval_scope_checked"])

    def test_negated_corpus_claim_is_accepted(self):
        client = FakeModel({
            "answer": "This does not mean the corpus proves either position.",
            "classification": "SUPPORTED",
            "citation_ids": ["e1"],
        })
        result = synthesize(SynthesisRequest("Question", EVIDENCE, "test-model"), client)
        self.assertTrue(result.validation["retrieval_scope_checked"])

    def test_industry_consensus_overclaim_is_rejected(self):
        client = FakeModel({
            "answer": "Industry consensus is that agents need memory.",
            "classification": "SUPPORTED",
            "citation_ids": ["e1"],
        })
        with self.assertRaisesRegex(ValueError, "corpus-wide"):
            synthesize(SynthesisRequest("Question", EVIDENCE, "test-model"), client)


class OutputTokenCeilingTests(unittest.TestCase):
    """One configured ceiling, not a default per call site.

    Three defaults previously disagreed — 2000 in synthesis, 4000 in the
    retrieval loop, and a script flag that was parsed and discarded. A request
    that inherited the lowest truncated a response already paid for, and
    surfaced as a JSON parse error rather than a token limit.
    """

    def test_the_default_comes_from_configuration(self):
        self.assertEqual(MAX_OUTPUT_TOKENS,
                         int(agent_parameters()["max_output_tokens"]))
        request = SynthesisRequest("Question?", EVIDENCE, "test-model")
        self.assertEqual(request.max_output_tokens, MAX_OUTPUT_TOKENS)

    def test_the_retrieval_loop_shares_that_ceiling(self):
        """A second literal here is what caused the truncation bug."""
        from llm_gym.agent import retrieval_retry
        import inspect
        default = inspect.signature(
            retrieval_retry.run_retrieval_retry).parameters["max_output_tokens"].default
        self.assertEqual(default, MAX_OUTPUT_TOKENS)
