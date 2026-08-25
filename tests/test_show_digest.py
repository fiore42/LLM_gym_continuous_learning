import unittest

from scripts.show_digest import format_assessment, format_header, format_selection


class DigestHeaderTests(unittest.TestCase):
    def test_time_and_legacy_call_counts_are_labelled_honestly(self):
        report = {
            "window": {
                "since": "2026-07-01T00:00:00+00:00",
                "until": "2026-07-31T00:00:00+00:00",
                "days": 30.0,
                "platforms": ["youtube"],
                "sources": {"channel": 3},
                "index_signature": "index-v1:1:2",
                "considered": 3,
            },
            "loop": {"run_id": "run-1", "loop_type": "DIGEST"},
            "prompt_version": "significance-v1",
            "model": "model",
            "outcome": "COMPLETED",
            "stop_reason": "UNITS_EXHAUSTED",
            "complete": True,
            "items_assessed": 3,
            "items_total": 3,
            "items_rejected": 0,
            "label_counts": {"SIGNIFICANT": 3},
            "cost_usd": 0.03,
            "provider_calls": 3,
            "provider_calls_exact": False,
            "invocation_elapsed_seconds": 10,
            "run_wall_elapsed_seconds": 3600,
            "usage_totals": {"model_latency_seconds": 8},
        }
        rendered = "\n".join(format_header(report))
        self.assertIn(">=3 (legacy lower bound) provider calls", rendered)
        self.assertIn("10s this invocation", rendered)
        self.assertIn("3600s run wall including pauses", rendered)
        self.assertIn("8s in the provider", rendered)
        self.assertIn("usage>=   0 in / 0 out", rendered)

    def test_old_reports_without_explicit_provider_fields_are_lower_bounds(self):
        report = {
            "window": {"since": "2026-07-01", "until": "2026-07-02",
                       "days": 1, "platforms": ["youtube"], "sources": {}},
            "loop": {"run_id": "old", "loop_type": "DIGEST"},
            "model": "model", "prompt_version": "v1", "outcome": "COMPLETED",
            "stop_reason": "UNITS_EXHAUSTED", "complete": True,
            "items_total": 5, "items_assessed": 5, "items_rejected": 0,
            "cost_usd": 0.01, "model_calls": 5, "elapsed_seconds": 2,
            "usage_totals": {}, "label_counts": {},
        }
        rendered = "\n".join(format_header(report))
        self.assertIn(">=5 (legacy lower bound) provider calls", rendered)
        self.assertIn("usage>=", rendered)


class DigestAssessmentTests(unittest.TestCase):
    def test_multiple_mapped_quotes_are_rendered_and_v1_remains_readable(self):
        base = {"significance": "SIGNIFICANT", "published_at": "2026-08-01",
                "title": "Example", "claimed_change": "A and B changed.",
                "problem_addressed": "", "reason": "Two passages establish it.",
                "canonical_url": "https://example.test"}
        current = {**base, "supporting_evidence": [
            {"claim_component": "A changed.", "quote": "Exact quote A."},
            {"claim_component": "B changed.", "quote": "Exact quote B."},
        ]}
        rendered = "\n".join(format_assessment(current, quotes=True))
        self.assertIn("evidence 1: A changed.", rendered)
        self.assertIn('quote 2   : "Exact quote B."', rendered)

        historical = "\n".join(format_assessment(
            {**base, "supporting_quote": "Old exact quote."}, quotes=True))
        self.assertIn('quote 1   : "Old exact quote."', historical)


if __name__ == "__main__":
    unittest.main()


class SelectionSummaryTests(unittest.TestCase):
    RANKED = [
        {"significance": "SIGNIFICANT"},
        {"significance": "SIGNIFICANT"},
        {"significance": "INCREMENTAL"},
        {"significance": "PROMOTIONAL"},
    ]

    def test_filtered_view_names_the_hidden_count_and_the_flag(self):
        summary = format_selection(self.RANKED, {"SIGNIFICANT"})
        self.assertIn("2 of 4 assessments", summary)
        self.assertIn("2 hidden by this filter", summary)
        self.assertIn("--label ALL", summary)

    def test_unfiltered_view_claims_no_hidden_work(self):
        summary = format_selection(self.RANKED, {"ALL"})
        self.assertIn("4 of 4 assessments", summary)
        self.assertNotIn("hidden", summary)

    def test_a_filter_matching_everything_reports_no_hidden_work(self):
        summary = format_selection(
            self.RANKED, {"SIGNIFICANT", "INCREMENTAL", "PROMOTIONAL"})
        self.assertNotIn("hidden", summary)


class BrokenPipeTests(unittest.TestCase):
    """A reader quitting the pager must not look like a report failure."""

    REPORT = {
        "window": {"since": "2026-07-01T00:00:00+00:00", "until": "2026-07-31T00:00:00+00:00",
                   "days": 30.0, "platforms": ["youtube"], "sources": {"c": 1},
                   "index_signature": "i:1:2", "considered": 1},
        "loop": {"run_id": "r", "loop_type": "DIGEST"},
        "prompt_version": "significance-v2", "model": "m",
        "outcome": "ESCALATED_FOR_REVIEW", "stop_reason": "UNITS_EXHAUSTED",
        "complete": False, "items_assessed": 1, "items_total": 2, "items_rejected": 1,
        "label_counts": {"SIGNIFICANT": 1}, "cost_usd": 0.01,
        "provider_calls": 1, "provider_calls_exact": True,
        "invocation_elapsed_seconds": 1, "run_wall_elapsed_seconds": 1,
        "usage_totals": {"model_latency_seconds": 1},
        # Large enough that the output exceeds the 64 KB pipe buffer. With a
        # handful of rows everything fits, the writer never blocks, and no
        # BrokenPipeError is raised — the test then passes with the guard
        # removed, which is how this fixture was wrong the first time.
        "ranked": [{"significance": "SIGNIFICANT", "published_at": "2026-07-02",
                    "title": f"title {index}", "canonical_url": "u",
                    "claimed_change": "c" * 200, "supporting_quote": "q"}
                   for index in range(2000)],
        "rejected": [],
    }

    def test_a_reader_closing_the_pipe_prints_no_traceback(self):
        """Runs the real CLI through a pipe a reader abandons after one line.

        In-process fd juggling does not reproduce this: print() buffers, so no
        BrokenPipeError is raised and the test passes with the guard removed.
        Only a real subprocess writing into a real closed pipe exercises it.
        """
        import json, os, subprocess, sys, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(self.REPORT, handle)
            path = handle.name
        try:
            script = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                  "scripts", "show_digest.py")
            completed = subprocess.run(
                f'{sys.executable} {script} {path} --label ALL | head -1',
                shell=True, capture_output=True, text=True)
        finally:
            os.unlink(path)
        self.assertNotIn("BrokenPipeError", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertEqual(completed.stderr.strip(), "")
