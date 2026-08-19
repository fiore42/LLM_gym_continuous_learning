import json
import unittest

from llm_gym.agent.significance import (SIGNIFICANCE_LABELS, SIGNIFICANCE_PROMPT_VERSION,
                                        SignificanceRequest, assess_item, quote_is_grounded,
                                        render_prompt)

ITEM = {
    "evidence_id": "abc123",
    "canonical_url": "https://example.test/video",
    "published_at_utc": "2026-08-03T00:00:00+00:00",
    "title": "Routing cheaply",
    "text": "We replaced the single model with a router.\nIt cut p95 latency "
            "from 800ms to 120ms in production, measured over two weeks.",
}


def _response(**overrides) -> str:
    payload = {
        "supporting_evidence": [
            {"claim_component": "A router replaced the single model.",
             "quote": "We replaced the single model with a router."},
            {"claim_component": "The router reduced p95 latency.",
             "quote": "It cut p95 latency from 800ms to 120ms in production"},
        ],
        "claimed_change": "A router replaced the single model and reduced p95 latency.",
        "problem_addressed": "High p95 latency in production.",
        "significance": "SIGNIFICANT",
        "reason": "The item reports a measured latency reduction over a stated period.",
    }
    payload.update(overrides)
    return json.dumps(payload)


class Client:
    def __init__(self, body: str):
        self.body = body
        self.calls = 0
        self.seen: dict = {}

    def complete(self, **kwargs):
        self.calls += 1
        self.seen = kwargs
        return self.body


class GroundedQuoteTests(unittest.TestCase):
    """A judgement is auditable only if its quote can be located in the source."""

    def test_a_quote_spanning_a_line_break_is_grounded(self):
        """Reflowing a newline into a space is not a misquote."""
        self.assertTrue(quote_is_grounded(
            "with a router. It cut p95 latency", ITEM["text"]))

    def test_paraphrase_and_ellipsis_are_not_grounded(self):
        for quote in ("It reduced p95 latency from 800ms to 120ms",
                      "It cut p95 latency ... in production",
                      "It cut p95 latency from 80ms to 120ms",
                      ""):
            with self.subTest(quote=quote):
                self.assertFalse(quote_is_grounded(quote, ITEM["text"]))


class AssessItemTests(unittest.TestCase):
    def test_one_item_produces_one_call_and_a_validated_result(self):
        client = Client(_response())
        result = assess_item(SignificanceRequest(ITEM, "test-model"), client)
        self.assertEqual(client.calls, 1)
        self.assertEqual(result.item_id, "abc123")
        self.assertEqual(result.significance, "SIGNIFICANT")
        self.assertTrue(result.validation["quote_grounded"])
        self.assertEqual(result.validation["evidence_count"], 2)
        self.assertEqual(len(result.supporting_evidence), 2)
        self.assertEqual(result.prompt_version, SIGNIFICANCE_PROMPT_VERSION)
        # Provenance travels with the judgement, per Rule 0.
        self.assertTrue(result.prompt["prompt_sha256"])
        self.assertIn("abc123", result.prompt["rendered_user_prompt"])

    def test_only_the_supplied_item_reaches_the_model(self):
        """A per-item call must not leak the rest of the window."""
        client = Client(_response())
        assess_item(SignificanceRequest(ITEM, "test-model"), client)
        user = client.seen["user"]
        self.assertIn(ITEM["text"], user)
        self.assertNotIn("EVIDENCE_ID", user)

    def test_an_ungrounded_quote_is_rejected(self):
        """The failure this validation exists for: a confident invention."""
        client = Client(_response(supporting_evidence=[{
            "claim_component": "Latency fell.",
            "quote": "It cut p95 latency from 900ms to 50ms",
        }]))
        with self.assertRaisesRegex(ValueError, "does not appear in the item text"):
            assess_item(SignificanceRequest(ITEM, "test-model"), client)

    def test_evidence_is_limited_to_three_distinct_mapped_quotes(self):
        one = {"claim_component": "A router was introduced.",
               "quote": "We replaced the single model with a router."}
        with self.subTest("duplicate"):
            with self.assertRaisesRegex(ValueError, "must be distinct"):
                assess_item(SignificanceRequest(ITEM, "test-model"),
                            Client(_response(supporting_evidence=[one, one])))
        with self.subTest("too-many"):
            with self.assertRaisesRegex(ValueError, "between 1 and 3"):
                assess_item(SignificanceRequest(ITEM, "test-model"),
                            Client(_response(supporting_evidence=[one] * 4)))

    def test_explicit_v1_prompt_keeps_the_historical_single_quote_shape(self):
        payload = {
            "claimed_change": "A router replaced a single model.",
            "problem_addressed": "High latency.",
            "significance": "SIGNIFICANT",
            "reason": "The item reports a router.",
            "supporting_quote": "We replaced the single model with a router.",
        }
        result = assess_item(
            SignificanceRequest(ITEM, "test-model", prompt_version="significance-v1"),
            Client(json.dumps(payload)))
        serialized = result.to_dict()
        self.assertEqual(serialized["supporting_quote"], payload["supporting_quote"])
        self.assertNotIn("supporting_evidence", serialized)

    def test_an_unknown_label_is_rejected_and_names_the_allowed_set(self):
        client = Client(_response(significance="VERY_IMPORTANT"))
        with self.assertRaisesRegex(ValueError, "significance must be one of"):
            assess_item(SignificanceRequest(ITEM, "test-model"), client)

    def test_duplicate_is_not_a_label_the_model_may_assign(self):
        """Duplication is a deterministic property of a group, decided by code."""
        self.assertNotIn("DUPLICATE", SIGNIFICANCE_LABELS)
        client = Client(_response(significance="DUPLICATE"))
        with self.assertRaises(ValueError):
            assess_item(SignificanceRequest(ITEM, "test-model"), client)

    def test_a_label_is_accepted_case_insensitively_but_normalised(self):
        client = Client(_response(significance="  incremental  "))
        result = assess_item(SignificanceRequest(ITEM, "test-model"), client)
        self.assertEqual(result.significance, "INCREMENTAL")

    def test_a_missing_field_names_the_field(self):
        payload = json.loads(_response())
        del payload["problem_addressed"]
        client = Client(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "keys must be exactly"):
            assess_item(SignificanceRequest(ITEM, "test-model"), client)

    def test_an_extra_field_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "keys must be exactly"):
            assess_item(SignificanceRequest(ITEM, "test-model"),
                        Client(_response(unrequested="value")))

    def test_an_empty_reason_is_rejected(self):
        client = Client(_response(reason="   "))
        with self.assertRaisesRegex(ValueError, "reason must not be empty"):
            assess_item(SignificanceRequest(ITEM, "test-model"), client)

    def test_a_fenced_response_is_still_parsed(self):
        """Live contact showed providers wrap JSON in Markdown fences."""
        client = Client(f"```json\n{_response()}\n```")
        result = assess_item(SignificanceRequest(ITEM, "test-model"), client)
        self.assertEqual(result.significance, "SIGNIFICANT")

    def test_an_item_without_text_is_refused_before_any_call(self):
        client = Client(_response())
        with self.assertRaisesRegex(ValueError, "requires text"):
            assess_item(SignificanceRequest({**ITEM, "text": ""}, "test-model"), client)
        self.assertEqual(client.calls, 0)

    def test_an_item_without_an_id_is_refused_before_any_call(self):
        client = Client(_response())
        with self.assertRaisesRegex(ValueError, "requires evidence_id"):
            assess_item(SignificanceRequest({**ITEM, "evidence_id": ""}, "test-model"), client)
        self.assertEqual(client.calls, 0)

    def test_revision_feedback_is_appended_for_a_retry(self):
        request = SignificanceRequest(ITEM, "test-model",
                                      revision_feedback="quote was not verbatim")
        _, user, _ = render_prompt(request)
        self.assertIn("quote was not verbatim", user)
        self.assertIn("previous response was rejected", user)


if __name__ == "__main__":
    unittest.main()
