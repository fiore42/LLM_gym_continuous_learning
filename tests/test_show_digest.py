import unittest

from scripts.show_digest import format_assessment, format_header


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
