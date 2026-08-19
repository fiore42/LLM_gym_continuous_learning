import json
import re
import unittest
from dataclasses import replace
from unittest.mock import patch

from llm_gym.agent.model_client import ModelProviderError
from llm_gym.agent.retrieval_retry import run_retrieval_retry
from scripts.agent_run_retrieval_retry import default_output_path, load_case, run_case


def _evidence(evidence_id, snippet):
    return {"evidence_id": evidence_id, "canonical_url": f"https://example.test/{evidence_id}",
            "snippet": snippet, "locator": None}


class ScriptedClient:
    """Builds a valid response for whatever evidence the prompt actually carries.

    Round two receives an expanded evidence set, so the assessment must be
    generated from the prompt rather than hardcoded.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.seen_evidence_counts = []
        self.last_usage = {}

    def complete(self, **kwargs):
        classification, queries = self.script[self.calls]
        self.calls += 1
        ids = re.findall(r"EVIDENCE_ID: (\S+)", kwargs["user"])
        self.seen_evidence_counts.append(len(ids))
        return json.dumps({
            "answer": "The retrieved evidence is summarised here.",
            "classification": classification,
            "citation_ids": ids,
            "evidence_assessment": [
                {"evidence_id": item, "relevant": True, "reason": "considered"}
                for item in ids
            ],
            "suggested_queries": queries,
        })


class RetrievalRetryScriptTests(unittest.TestCase):
    def test_thin_first_round_triggers_evidence_expansion(self):
        extra = [_evidence("e2", "A second source found by the refined query.")]
        client = ScriptedClient([
            ("INSUFFICIENT_EVIDENCE", ["evaluation practice"]),
            ("SUPPORTED", []),
        ])
        trace = run_case(
            question="What does the corpus say about evals?",
            model="test-model", client=client,
            retrieve=lambda query: ([_evidence("e1", "One thin source.")]
                                    if query.startswith("What") else extra),
            case_id="demo", frozen_expected_outcome="SUPPORTED",
        )
        self.assertEqual(client.calls, 2)
        self.assertEqual(client.seen_evidence_counts, [1, 2])
        self.assertTrue(trace["evidence_expanded"])
        self.assertEqual(trace["evidence_count_initial"], 1)
        self.assertEqual(trace["evidence_count_final"], 2)
        self.assertEqual(trace["refined_queries"], ["evaluation practice"])
        self.assertEqual(
            [row["classification"] for row in trace["rounds"]],
            ["INSUFFICIENT_EVIDENCE", "SUPPORTED"],
        )

    def test_sufficient_first_round_does_not_expand(self):
        client = ScriptedClient([("SUPPORTED", [])])
        trace = run_case(
            question="A well covered question?", model="test-model", client=client,
            retrieve=lambda query: [_evidence("e1", "A sufficient source.")],
        )
        self.assertEqual(client.calls, 1)
        self.assertFalse(trace["evidence_expanded"])
        self.assertEqual(trace["stop_reason"], "QUALITY_GATE_PASSED")

    def test_trace_records_triage_context_not_a_pass_fail_verdict(self):
        """A live run must not be scored against a frozen expected_outcome."""
        client = ScriptedClient([("INSUFFICIENT_EVIDENCE", [])])
        trace = run_case(
            question="Anything?", model="test-model", client=client,
            retrieve=lambda query: [_evidence("e1", "text")],
            case_id="independent_evaluation",
            frozen_expected_outcome="CONFLICTING_EVIDENCE",
        )
        self.assertEqual(trace["mode"], "live_retrieval")
        self.assertEqual(trace["frozen_expected_outcome"], "CONFLICTING_EVIDENCE")
        self.assertIn("Diff the evidence sets", trace["comparison_note"])
        # No pass/fail field exists: the trace is evidence for triage, not a score.
        self.assertNotIn("passed", trace)
        self.assertNotIn("match", trace)

    def test_unknown_case_lists_the_valid_ones(self):
        with self.assertRaisesRegex(ValueError, "unknown answer case"):
            load_case("config/agent_eval_suite.json", "no_such_case")

    def test_suite_cases_named_by_the_roadmap_are_loadable(self):
        for case_id in ("what_are_evals", "independent_evaluation"):
            with self.subTest(case=case_id):
                case = load_case("config/agent_eval_suite.json", case_id)
                self.assertTrue(case["question"].strip())


class TimingClient(ScriptedClient):
    """A scripted client that reports usage the way a real provider does."""

    def __init__(self, script, usages):
        super().__init__(script)
        self.usages = list(usages)

    def complete(self, **kwargs):
        body = super().complete(**kwargs)
        self.last_usage = self.usages[self.calls - 1]
        return body


class LatencyTraceTests(unittest.TestCase):
    """Per-call timing must reach the trace, since that is what gets compared."""

    def test_each_round_carries_its_own_usage_and_the_run_carries_the_total(self):
        extra = [_evidence("e2", "A second source found by the refined query.")]
        client = TimingClient(
            [("INSUFFICIENT_EVIDENCE", ["evaluation practice"]), ("SUPPORTED", [])],
            [{"output_tokens": 300, "latency_seconds": 12.0, "output_tokens_per_second": 25.0},
             {"output_tokens": 900, "latency_seconds": 28.0, "output_tokens_per_second": 32.14}],
        )
        trace = run_case(
            question="What does the corpus say about evals?",
            model="test-model", client=client,
            retrieve=lambda query: ([_evidence("e1", "One thin source.")]
                                    if query.startswith("What") else extra),
        )
        self.assertEqual([row["usage"]["latency_seconds"] for row in trace["rounds"]],
                         [12.0, 28.0])
        self.assertEqual(trace["model_latency_seconds"], 40.0)
        self.assertEqual(trace["output_tokens"], 1200)
        # 1200 tokens over 40 seconds — recomputed from the totals, not the
        # mean of the two per-round rates (28.6), which would ignore that the
        # second round wrote three times as much.
        self.assertEqual(trace["output_tokens_per_second"], 30.0)

    def test_a_rejected_call_counts_toward_latency_and_tokens(self):
        """A billed call must not vanish because validation rejected it.

        Measured live: runs whose round two failed validation reported 20
        seconds while clean runs reported 63 — the failed run looked *faster*
        because only validated rounds were counted, even though its cost,
        tracked separately, included the rejected call. Cost and latency have
        to agree about which calls happened.
        """
        class RejectRoundTwo(TimingClient):
            def complete(self, **kwargs):
                if self.calls >= 1:
                    self.calls += 1
                    self.last_usage = {"latency_seconds": 45.0, "output_tokens": 3000}
                    raise ValueError("evidence_assessment must contain each supplied "
                                     "evidence ID exactly once")
                return super().complete(**kwargs)

        client = RejectRoundTwo(
            [("INSUFFICIENT_EVIDENCE", ["evaluation practice"])],
            [{"latency_seconds": 20.0, "output_tokens": 1500}],
        )
        trace = run_case(
            question="What does the corpus say about evals?",
            model="test-model", client=client,
            retrieve=lambda query: ([_evidence("e1", "One thin source.")]
                                    if query.startswith("What") else
                                    [_evidence("e2", "A second source.")]),
        )
        self.assertEqual(trace["stop_reason"], "PROVIDER_OR_VALIDATION_ERROR")
        # One validated round at 20s plus two rejected attempts at 45s each.
        self.assertEqual(trace["model_latency_seconds"], 110.0)
        self.assertEqual(trace["rejected_call_latency_seconds"], 90.0)
        self.assertEqual(trace["rejected_calls_with_usage"], 2)
        self.assertEqual(trace["output_tokens"], 7500)

    def test_a_failure_before_usage_is_recorded_does_not_reuse_the_last_call(self):
        """Truncation raises before usage is set, leaving a stale value behind.

        Without clearing it first, the previous call's tokens and latency get
        counted twice and a phantom call appears in the trace.
        """
        class TruncateRoundTwo(TimingClient):
            def complete(self, **kwargs):
                if self.calls >= 1:
                    self.calls += 1
                    raise ModelProviderError("truncated at max_output_tokens=4000",
                                             retryable=False)
                return super().complete(**kwargs)

        client = TruncateRoundTwo(
            [("INSUFFICIENT_EVIDENCE", ["evaluation practice"])],
            [{"latency_seconds": 20.0, "output_tokens": 1500}],
        )
        trace = run_case(
            question="What does the corpus say about evals?",
            model="test-model", client=client,
            retrieve=lambda query: ([_evidence("e1", "One thin source.")]
                                    if query.startswith("What") else
                                    [_evidence("e2", "A second source.")]),
        )
        self.assertEqual(trace["model_latency_seconds"], 20.0)
        self.assertEqual(trace["output_tokens"], 1500)
        self.assertEqual(trace["rejected_calls_with_usage"], 0)

    def test_a_result_carrying_no_usage_tuple_still_produces_every_round(self):
        """``usage`` defaults to empty, so it can be shorter than ``attempts``.

        Zipping the two without padding would silently drop rounds from the
        trace — losing the run's content to make room for its diagnostics.
        """
        client = ScriptedClient([("SUPPORTED", [])])
        real = run_retrieval_retry

        def without_usage(**kwargs):
            result = real(**kwargs)
            return replace(result, usage=())

        with patch("scripts.agent_run_retrieval_retry.run_retrieval_retry", without_usage):
            trace = run_case(
                question="A well covered question?", model="test-model", client=client,
                retrieve=lambda query: [_evidence("e1", "A sufficient source.")],
            )
        self.assertEqual(len(trace["rounds"]), 1)
        self.assertEqual(trace["rounds"][0]["usage"], {})

    def test_a_client_reporting_no_usage_still_produces_every_round(self):
        """Timing is diagnostic; missing it must not cost the trace its rounds."""
        client = ScriptedClient([("SUPPORTED", [])])
        trace = run_case(
            question="A well covered question?", model="test-model", client=client,
            retrieve=lambda query: [_evidence("e1", "A sufficient source.")],
        )
        self.assertEqual(len(trace["rounds"]), 1)
        self.assertEqual(trace["rounds"][0]["usage"], {})
        self.assertEqual(trace["model_latency_seconds"], 0.0)
        self.assertIsNone(trace["output_tokens_per_second"])


class ProviderArmTests(unittest.TestCase):
    """Two provider arms must be distinguishable in both trace and filename."""

    def test_trace_records_which_provider_environment_served_the_run(self):
        client = ScriptedClient([("SUPPORTED", [])])
        trace = run_case(
            question="A well covered question?", model="glm-5.2", client=client,
            retrieve=lambda query: [_evidence("e1", "A sufficient source.")],
            provider_prefix="OPEN_WEIGHT",
        )
        self.assertEqual(trace["provider_prefix"], "OPEN_WEIGHT")
        self.assertEqual(trace["model"], "glm-5.2")

    def test_default_trace_path_defaults_to_the_agent_environment(self):
        client = ScriptedClient([("SUPPORTED", [])])
        trace = run_case(
            question="A well covered question?", model="m", client=client,
            retrieve=lambda query: [_evidence("e1", "A sufficient source.")],
        )
        self.assertEqual(trace["provider_prefix"], "AGENT")

    def test_two_arms_do_not_write_to_the_same_file(self):
        agent = default_output_path("what_are_evals", "AGENT")
        open_weight = default_output_path("what_are_evals", "OPEN_WEIGHT")
        self.assertNotEqual(agent, open_weight)
        self.assertIn("open_weight", open_weight)


class FailingClient:
    """Returns a truncated / unparseable response, as a real provider can."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0
        self.last_usage = {}

    def complete(self, **kwargs):
        self.calls += 1
        return self.payload


class RetrievalRetryResilienceTests(unittest.TestCase):
    def test_truncated_response_does_not_lose_the_run(self):
        """A malformed round must degrade into an inspectable trace.

        Losing the whole run on one bad response also discards the rounds
        already paid for.
        """
        client = FailingClient('{ "answer": "cut off mid-sen')
        trace = run_case(
            question="Anything?", model="test-model", client=client,
            retrieve=lambda query: [_evidence("e1", "text")],
            case_id="demo",
        )
        self.assertEqual(trace["stop_reason"], "PROVIDER_OR_VALIDATION_ERROR")
        self.assertIn("valid JSON", trace["error"])
        self.assertEqual(trace["rounds"], [])
        self.assertEqual(trace["evidence_count_initial"], 1)

    def test_partial_rounds_survive_a_later_failure(self):
        class ThenFail(ScriptedClient):
            def complete(self, **kwargs):
                if self.calls == 0:
                    return super().complete(**kwargs)
                self.calls += 1
                return "not json at all"

        client = ThenFail([("INSUFFICIENT_EVIDENCE", ["refined query"])])
        trace = run_case(
            question="Thin question?", model="test-model", client=client,
            retrieve=lambda query: ([_evidence("e1", "one")]
                                    if query.startswith("Thin") else [_evidence("e2", "two")]),
        )
        self.assertEqual(trace["stop_reason"], "PROVIDER_OR_VALIDATION_ERROR")
        # Round one is preserved even though round two failed.
        self.assertEqual(len(trace["rounds"]), 1)
        self.assertEqual(trace["rounds"][0]["classification"], "INSUFFICIENT_EVIDENCE")
        self.assertTrue(trace["evidence_expanded"])


if __name__ == "__main__":
    unittest.main()
