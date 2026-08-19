import unittest

from scripts.agent_measure_retrieval_trigger import (_row_line, classify_trigger,
                                                    measurement_output_dir,
                                                    provider_refused, summarise)


def _trace(classification, expanded):
    return {"rounds": [{"classification": classification}], "evidence_expanded": expanded}


class ClassifyTriggerTests(unittest.TestCase):
    def test_label_and_relevance_are_attributed_separately(self):
        """The point of the measurement is telling the two signals apart."""
        self.assertEqual(classify_trigger(_trace("INSUFFICIENT_EVIDENCE", True)), "label")
        # Expanded despite a sufficient label: only the relevance count can
        # have caused this, which is the case never yet seen live.
        self.assertEqual(classify_trigger(_trace("SUPPORTED", True)), "relevance_only")

    def test_non_expanding_runs_record_why_they_stopped(self):
        self.assertEqual(classify_trigger(_trace("SUPPORTED", False)),
                         "stopped_label_sufficient")
        self.assertEqual(classify_trigger(_trace("INSUFFICIENT_EVIDENCE", False)),
                         "stopped_no_queries")

    def test_a_run_without_rounds_is_not_miscounted(self):
        self.assertEqual(classify_trigger({"rounds": [], "evidence_expanded": False}),
                         "no_round_one")


class SummariseTests(unittest.TestCase):
    def _row(self, trigger, classification, cost=0.02, calls=2, expanded=True,
             stop="QUALITY_GATE_PASSED", provider_calls=None, latency=10.0,
             output_tokens=1000):
        return {"trigger": trigger, "round_one_classification": classification,
                "evidence_expanded": expanded, "stop_reason": stop,
                "model_calls": calls,
                "provider_calls": calls if provider_calls is None else provider_calls,
                "model_latency_seconds": latency, "output_tokens": output_tokens,
                "cost_usd": cost}

    def test_summary_counts_triggers_labels_errors_and_spend(self):
        rows = [
            self._row("label", "INSUFFICIENT_EVIDENCE"),
            self._row("relevance_only", "SUPPORTED"),
            self._row("stopped_label_sufficient", "SUPPORTED", calls=1, expanded=False),
            # A failed round: one validated attempt short of the calls billed.
            self._row("label", "INSUFFICIENT_EVIDENCE", calls=1, expanded=False,
                      stop="PROVIDER_OR_VALIDATION_ERROR", provider_calls=3),
        ]
        summary = summarise(rows)
        self.assertEqual(summary["runs"], 4)
        self.assertEqual(summary["relevance_only_fired"], 1)
        self.assertEqual(summary["expanded"], 2)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["round_one_labels"]["SUPPORTED"], 2)
        self.assertEqual(summary["total_completed_rounds"], 6)
        # The billed count exceeds completed rounds whenever a round failed.
        self.assertEqual(summary["total_provider_calls"], 8)
        self.assertAlmostEqual(summary["total_cost_usd"], 0.08)

    def test_throughput_is_recomputed_from_totals_not_averaged_per_run(self):
        """A slow, wordy run must not be weighted the same as a fast, short one.

        Averaging the two per-run rates would give 30 tokens/sec; the honest
        figure is total tokens over total time.
        """
        rows = [
            self._row("label", "INSUFFICIENT_EVIDENCE", latency=90.0, output_tokens=900),
            self._row("label", "INSUFFICIENT_EVIDENCE", latency=10.0, output_tokens=500),
        ]
        summary = summarise(rows)
        self.assertEqual(summary["total_model_latency_seconds"], 100.0)
        self.assertEqual(summary["output_tokens_per_second"], 14.0)

    def test_runs_without_timing_report_no_throughput(self):
        rows = [self._row("label", "INSUFFICIENT_EVIDENCE", latency=0.0, output_tokens=0)]
        self.assertIsNone(summarise(rows)["output_tokens_per_second"])


class FailedRunReportingTests(unittest.TestCase):
    """A run that dies in round one still has to be printable and countable."""

    def _row(self, **overrides):
        row = {"case_id": "what_are_evals", "repetition": 5, "trigger": "no_round_one",
               "round_one_classification": None, "round_one_relevant": None,
               "round_one_assessed": None, "provider_calls": 1,
               "model_latency_seconds": 0.0, "cost_usd": 0.0}
        row.update(overrides)
        return row

    def test_a_run_with_no_first_round_prints_instead_of_crashing(self):
        """A None classification used to raise TypeError mid-loop, aborting
        every measurement still queued and losing the summary entirely."""
        line = _row_line(self._row())
        self.assertIn("round1=NONE", line)
        self.assertIn("rep 5", line)

    def test_a_normal_row_still_formats_its_classification(self):
        line = _row_line(self._row(round_one_classification="SUPPORTED",
                                   round_one_relevant=3, round_one_assessed=8))
        self.assertIn("round1=SUPPORTED", line)
        self.assertIn("relevant=3/8", line)


class ProviderRefusalTests(unittest.TestCase):
    """A spend cap fails every remaining repetition the same way."""

    def test_a_usage_limit_stops_the_whole_measurement(self):
        trace = {"error": "ModelProviderError: model request failed: HTTP 400: You have "
                          "reached your specified API usage limits. You will regain "
                          "access on 2026-09-01 at 00:00 UTC."}
        self.assertTrue(provider_refused(trace))

    def test_an_ordinary_validation_failure_does_not_stop_the_run(self):
        """Those are stochastic — the next repetition may well succeed."""
        trace = {"error": "ValueError: evidence_assessment must contain each supplied "
                          "evidence ID exactly once"}
        self.assertFalse(provider_refused(trace))

    def test_a_clean_run_is_not_mistaken_for_a_refusal(self):
        self.assertFalse(provider_refused({"error": None}))


class ProviderArmIsolationTests(unittest.TestCase):
    def test_each_arm_measures_into_its_own_directory(self):
        """Shared directories let one arm overwrite the other's traces, and the
        surviving summary then mixes both runs while looking complete."""
        self.assertNotEqual(measurement_output_dir("AGENT"),
                            measurement_output_dir("OPEN_WEIGHT"))
        self.assertIn("open_weight", measurement_output_dir("OPEN_WEIGHT"))


if __name__ == "__main__":
    unittest.main()
