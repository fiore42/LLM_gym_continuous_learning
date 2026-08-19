import json
import unittest

from llm_gym.agent.model_client import ModelProviderError
from llm_gym.agent.retrieval_retry import _merge_evidence, run_retrieval_retry


class RetryClient:
    def __init__(self):
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        ids = [line.split("\n", 1)[0] for line in kwargs["user"].split("EVIDENCE_ID: ")[1:]]
        if self.calls == 1:
            payload = {
                "answer": "The evidence is insufficient.",
                "classification": "INSUFFICIENT_EVIDENCE",
                "citation_ids": [ids[0]],
                "suggested_queries": ["targeted retrieval"],
            }
        else:
            payload = {
                "answer": "The expanded evidence supports the answer.",
                "classification": "SUPPORTED",
                "citation_ids": ids,
                "suggested_queries": [],
            }
        payload["evidence_assessment"] = [
            {"evidence_id": item, "relevant": True, "reason": "Test evidence."}
            for item in ids
        ]
        return json.dumps(payload)


class RetrievalRetryTests(unittest.TestCase):
    def test_refined_query_adds_unique_evidence_and_allows_second_draft(self):
        client = RetryClient()
        calls = []

        def retrieve(query):
            calls.append(query)
            return [{"evidence_id": "e2", "snippet": "New evidence."}]

        result = run_retrieval_retry(
            question="Question", evidence=({"evidence_id": "e1", "snippet": "Initial."},),
            model="test-model", client=client, retrieve=retrieve, prompt_version="synthesis-v6",
        )
        self.assertEqual(result.stop_reason, "QUALITY_GATE_PASSED")
        self.assertEqual(len(result.attempts), 2)
        self.assertEqual([item["evidence_id"] for item in result.evidence], ["e1", "e2"])
        self.assertEqual(calls, ["targeted retrieval"])

    def test_duplicate_retrieval_stops_without_third_call(self):
        client = RetryClient()
        result = run_retrieval_retry(
            question="Question", evidence=({"evidence_id": "e1", "snippet": "Initial."},),
            model="test-model", client=client,
            retrieve=lambda query: [{"evidence_id": "e1", "snippet": "Duplicate."}],
            prompt_version="synthesis-v6",
        )
        self.assertEqual(result.stop_reason, "RETRIEVAL_NO_NEW_EVIDENCE")
        self.assertEqual(len(result.attempts), 1)


class ThinEvidenceClient:
    """Reports SUPPORTED while judging almost none of the evidence usable.

    This is the live failure mode: on identical input the label flipped
    between SUPPORTED and INSUFFICIENT_EVIDENCE, while the per-item relevance
    assessment stayed consistent. Expansion must key on the stable signal.
    """

    def __init__(self, relevant_in_round_one=1):
        self.calls = 0
        self.relevant_in_round_one = relevant_in_round_one

    def complete(self, **kwargs):
        self.calls += 1
        ids = [line.split("\n", 1)[0] for line in kwargs["user"].split("EVIDENCE_ID: ")[1:]]
        first = self.calls == 1
        relevant = self.relevant_in_round_one if first else len(ids)
        return json.dumps({
            "answer": "The retrieved evidence gives only a fragmentary picture.",
            "classification": "SUPPORTED",
            "citation_ids": ids[:1],
            "suggested_queries": ["a refined query"] if first else [],
            "evidence_assessment": [
                {"evidence_id": item, "relevant": index < relevant, "reason": "judged"}
                for index, item in enumerate(ids)
            ],
        })


class ThinEvidenceTriggerTests(unittest.TestCase):
    def _evidence(self, count):
        return tuple({"evidence_id": f"e{n}", "snippet": f"snippet {n}"}
                     for n in range(1, count + 1))

    def test_supported_but_thin_evidence_still_expands(self):
        client = ThinEvidenceClient(relevant_in_round_one=1)
        result = run_retrieval_retry(
            question="Question", evidence=self._evidence(8), model="m", client=client,
            retrieve=lambda query: [{"evidence_id": "new1", "snippet": "found"}],
        )
        # Round one said SUPPORTED; the loop expanded anyway because only one
        # of eight items was judged usable.
        self.assertEqual(client.calls, 2)
        self.assertEqual(len(result.evidence), 9)
        self.assertEqual(result.queries, ("a refined query",))

    def test_supported_with_enough_relevant_evidence_stops(self):
        client = ThinEvidenceClient(relevant_in_round_one=5)
        result = run_retrieval_retry(
            question="Question", evidence=self._evidence(8), model="m", client=client,
            retrieve=lambda query: [{"evidence_id": "new1", "snippet": "found"}],
        )
        self.assertEqual(client.calls, 1)
        self.assertEqual(result.stop_reason, "QUALITY_GATE_PASSED")

    def test_threshold_scales_to_a_small_retrieved_set(self):
        """Two relevant items out of two is not thin evidence."""
        client = ThinEvidenceClient(relevant_in_round_one=2)
        result = run_retrieval_retry(
            question="Question", evidence=self._evidence(2), model="m", client=client,
            retrieve=lambda query: [{"evidence_id": "new1", "snippet": "found"}],
        )
        self.assertEqual(client.calls, 1)
        self.assertEqual(result.stop_reason, "QUALITY_GATE_PASSED")


class FlakyValidationClient:
    """Fails validation on the first N calls, then returns a valid response.

    Live symptom: emitting exactly one evidence_assessment entry per supplied
    item becomes unreliable as the evidence set grows, so an identical request
    can fail once and succeed on retry.
    """

    def __init__(self, failures_before_success, classification="SUPPORTED"):
        self.failures_before_success = failures_before_success
        self.classification = classification
        self.calls = 0
        self.prompts = []

    def complete(self, **kwargs):
        self.calls += 1
        self.prompts.append(kwargs["user"])
        if self.calls <= self.failures_before_success:
            ids = [line.split("\n", 1)[0] for line in kwargs["user"].split("EVIDENCE_ID: ")[1:]]
            # One assessment short: the exact live failure mode.
            return json.dumps({
                "answer": "An answer.",
                "classification": self.classification,
                "citation_ids": ids[:1],
                "suggested_queries": [],
                "evidence_assessment": [
                    {"evidence_id": item, "relevant": True, "reason": "judged"}
                    for item in ids[:-1]
                ],
            })
        ids = [line.split("\n", 1)[0] for line in kwargs["user"].split("EVIDENCE_ID: ")[1:]]
        return json.dumps({
            "answer": "A corrected answer.",
            "classification": self.classification,
            "citation_ids": ids[:1],
            "suggested_queries": [],
            "evidence_assessment": [
                {"evidence_id": item, "relevant": True, "reason": "judged"}
                for item in ids
            ],
        })


class NonRetryableClient:
    def __init__(self):
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        raise ModelProviderError("model response truncated at max_output_tokens=4000",
                                 retryable=False)


class ValidationRetryTests(unittest.TestCase):
    def _evidence(self, count):
        return tuple({"evidence_id": f"e{n}", "snippet": f"snippet {n}"}
                     for n in range(1, count + 1))

    def test_a_stochastic_validation_failure_is_retried_and_recovers(self):
        client = FlakyValidationClient(failures_before_success=1)
        result = run_retrieval_retry(
            question="Question", evidence=self._evidence(4), model="m", client=client,
            retrieve=lambda query: [],
        )
        self.assertEqual(client.calls, 2)
        self.assertEqual(result.stop_reason, "QUALITY_GATE_PASSED")
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.attempts[0].answer, "A corrected answer.")
        # The retry must tell the model what was wrong, not repeat blindly.
        self.assertIn("was rejected", client.prompts[1])
        self.assertIn("evidence_assessment", client.prompts[1])

    def test_repeated_validation_failure_still_degrades_gracefully(self):
        client = FlakyValidationClient(failures_before_success=99)
        result = run_retrieval_retry(
            question="Question", evidence=self._evidence(4), model="m", client=client,
            retrieve=lambda query: [],
        )
        self.assertEqual(client.calls, 2)  # one attempt plus one retry
        self.assertEqual(result.stop_reason, "PROVIDER_OR_VALIDATION_ERROR")
        self.assertIn("evidence_assessment", result.error)

    def test_a_non_retryable_provider_error_is_not_retried(self):
        """Truncation will truncate again; retrying identically wastes spend."""
        client = NonRetryableClient()
        result = run_retrieval_retry(
            question="Question", evidence=self._evidence(4), model="m", client=client,
            retrieve=lambda query: [],
        )
        self.assertEqual(client.calls, 1)
        self.assertEqual(result.stop_reason, "PROVIDER_OR_VALIDATION_ERROR")
        self.assertIn("truncated", result.error)


class EvidenceCapClient:
    """Always insufficient, always proposing one query, so expansion is driven
    purely by how many items the merge step allows in."""

    def __init__(self):
        self.calls = 0
        self.supplied_counts = []

    def complete(self, **kwargs):
        self.calls += 1
        ids = [line.split("\n", 1)[0] for line in kwargs["user"].split("EVIDENCE_ID: ")[1:]]
        self.supplied_counts.append(len(ids))
        return json.dumps({
            "answer": "An answer.",
            "classification": "INSUFFICIENT_EVIDENCE",
            "citation_ids": ids[:1],
            "suggested_queries": ["refine"],
            "evidence_assessment": [
                {"evidence_id": item, "relevant": False, "reason": "judged"}
                for item in ids
            ],
        })


class EvidenceCapTests(unittest.TestCase):
    def test_expansion_stops_at_the_cap(self):
        """Unbounded expansion walked the loop past its own output ceiling.

        Measured live: 26+ item sets truncated in five of seven runs, while
        sets of 25 or fewer always completed.
        """
        client = EvidenceCapClient()
        result = run_retrieval_retry(
            question="Question", evidence=({"evidence_id": "e0", "snippet": "start"},),
            model="m", client=client,
            retrieve=lambda query: [{"evidence_id": f"n{i}", "snippet": "found"}
                                    for i in range(50)],
            max_evidence_items=20,
        )
        self.assertLessEqual(len(result.evidence), 20)
        # Round two must never be handed more than the cap allows.
        self.assertTrue(all(count <= 20 for count in client.supplied_counts),
                        client.supplied_counts)

    def test_evidence_already_seen_is_never_dropped(self):
        """Truncating additions is safe; removing shown evidence is not."""
        over_cap = tuple({"evidence_id": f"e{n}", "snippet": "x"} for n in range(25))
        merged = _merge_evidence(over_cap, [{"evidence_id": "new", "snippet": "y"}],
                                 20)
        self.assertEqual(len(merged), 25)
        self.assertNotIn("new", [item["evidence_id"] for item in merged])

    def test_no_cap_preserves_previous_behaviour(self):
        merged = _merge_evidence(({"evidence_id": "e1", "snippet": "x"},),
                                 [{"evidence_id": f"n{i}", "snippet": "y"} for i in range(30)],
                                 None)
        self.assertEqual(len(merged), 31)


class ProviderCallAccountingTests(unittest.TestCase):
    def _evidence(self, count):
        return tuple({"evidence_id": f"e{n}", "snippet": f"snippet {n}"}
                     for n in range(1, count + 1))

    def test_rejected_calls_are_counted_even_though_they_leave_no_attempt(self):
        """A billed call that fails validation must not vanish from the count.

        Measured live: ten runs reported fifteen completed rounds while the
        provider had actually been called about twenty-one times, because
        failed rounds never reach ``attempts``.
        """
        client = FlakyValidationClient(failures_before_success=1)
        result = run_retrieval_retry(
            question="Question", evidence=self._evidence(4), model="m", client=client,
            retrieve=lambda query: [],
        )
        self.assertEqual(len(result.attempts), 1)      # one validated round
        self.assertEqual(result.provider_calls, 2)      # two billed requests
        self.assertEqual(result.provider_calls, client.calls)

    def test_counts_agree_when_nothing_fails(self):
        client = FlakyValidationClient(failures_before_success=0)
        result = run_retrieval_retry(
            question="Question", evidence=self._evidence(4), model="m", client=client,
            retrieve=lambda query: [],
        )
        self.assertEqual(result.provider_calls, len(result.attempts))

    def test_a_non_retryable_failure_still_counts_its_call(self):
        client = NonRetryableClient()
        result = run_retrieval_retry(
            question="Question", evidence=self._evidence(4), model="m", client=client,
            retrieve=lambda query: [],
        )
        self.assertEqual(result.attempts, ())
        self.assertEqual(result.provider_calls, 1)
