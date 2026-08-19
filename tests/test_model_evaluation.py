import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_gym.agent.model_evaluation import BenchmarkCase, load_benchmark_cases, run_model_comparison


EVIDENCE = ({"evidence_id": "e1", "canonical_url": "https://example.test/1",
             "snippet": "Agents use memory."},
            {"evidence_id": "e2", "canonical_url": "https://example.test/2",
             "snippet": "Unrelated evidence."})


class FakeClient:
    def complete(self, **kwargs):
        return json.dumps({
            "answer": "Memory stores prior context.",
            "classification": "SUPPORTED",
            "citation_ids": ["e1"],
            "evidence_assessment": [
                {"evidence_id": "e1", "relevant": True, "reason": "Directly addresses memory."},
                {"evidence_id": "e2", "relevant": False, "reason": "Unrelated to memory."},
            ],
        })


class TimedClient(FakeClient):
    """Reports usage the way a provider client does, so timing can be summed."""

    def __init__(self, latency_seconds, output_tokens):
        self.usage = {"latency_seconds": latency_seconds, "output_tokens": output_tokens,
                      "input_tokens": 100, "cost_usd": 0.0}
        self.last_usage = {}

    def complete(self, **kwargs):
        body = super().complete(**kwargs)
        self.last_usage = dict(self.usage)
        return body


class ProviderTimingTests(unittest.TestCase):
    """Ranking providers needs throughput, not just wall clock."""

    def test_summary_reports_provider_time_and_throughput_per_provider(self):
        cases = (BenchmarkCase("memory", "How do agents use memory?", EVIDENCE,
                               "SUPPORTED", ("e1",), ("e2",)),)
        with tempfile.TemporaryDirectory() as directory:
            report = run_model_comparison(
                cases,
                # Same answer, same token count, one provider twice as fast.
                {"open": ("open-model", TimedClient(20.0, 500)),
                 "frontier": ("front-model", TimedClient(10.0, 500))},
                work_dir=Path(directory) / "work",
                output_path=Path(directory) / "report.json")
        self.assertEqual(report["providers"]["open"]["summary"]["model_latency_seconds"], 20.0)
        self.assertEqual(report["providers"]["open"]["summary"]["output_tokens_per_second"], 25.0)
        self.assertEqual(report["providers"]["frontier"]["summary"]["output_tokens_per_second"], 50.0)

    def test_a_provider_without_usage_data_reports_no_throughput(self):
        cases = (BenchmarkCase("memory", "How do agents use memory?", EVIDENCE, "SUPPORTED"),)
        with tempfile.TemporaryDirectory() as directory:
            report = run_model_comparison(
                cases, {"open": ("open-model", FakeClient()),
                        "frontier": ("front-model", FakeClient())},
                work_dir=Path(directory) / "work",
                output_path=Path(directory) / "report.json")
        summary = report["providers"]["open"]["summary"]
        self.assertEqual(summary["model_latency_seconds"], 0.0)
        self.assertIsNone(summary["output_tokens_per_second"])


class ModelEvaluationTests(unittest.TestCase):
    def test_benchmark_cases_load_from_versioned_file(self):
        cases = load_benchmark_cases("config/agent_benchmark.json")
        self.assertEqual([case.case_id for case in cases], [
            "direct_support", "insufficient_evidence", "conflicting_evidence"])
        self.assertEqual(cases[1].expected_outcome, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(len(cases[-1].evidence), 2)

    def test_same_cases_are_run_for_two_providers(self):
        cases = (BenchmarkCase("memory", "How do agents use memory?", EVIDENCE, "SUPPORTED", ("e1",), ("e2",)),)
        with tempfile.TemporaryDirectory() as directory:
            report = run_model_comparison(
                cases, {"open": ("open-model", FakeClient()), "frontier": ("front-model", FakeClient())},
                work_dir=Path(directory) / "work", output_path=Path(directory) / "report.json")
        self.assertEqual(report["comparison_contract"]["same_evidence"], True)
        self.assertEqual(report["loop"]["loop_type"], "MODEL_EVALUATION")
        self.assertTrue(report["loop"]["run_id"])
        self.assertEqual(report["providers"]["open"]["results"][0]["loop"]["parent_run_id"],
                         report["loop"]["run_id"])
        self.assertEqual(report["providers"]["open"]["summary"]["pass_rate"], 1.0)
        self.assertEqual(report["providers"]["open"]["summary"]["classification_accuracy"], 1.0)
        self.assertEqual(report["providers"]["frontier"]["summary"]["model_calls"], 1)
        self.assertEqual(report["providers"]["open"]["summary"]["retries_to_pass"], 0)
        self.assertEqual(report["providers"]["open"]["summary"]["estimated_cost_usd"], 0.0)
        self.assertEqual(report["providers"]["open"]["summary"]["completeness_accuracy"], 1.0)
        self.assertEqual(report["providers"]["open"]["summary"]["unsupported_claim_accuracy"], 1.0)
        self.assertEqual(report["providers"]["open"]["summary"]["stopping_compliance"], 1.0)

    def test_comparison_requires_two_providers(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            run_model_comparison((BenchmarkCase("x", "Question", EVIDENCE),),
                                 {"only": ("model", FakeClient())}, work_dir="/tmp/work", output_path="/tmp/report.json")

    def test_repetitions_report_consistency_and_stopping(self):
        cases = (BenchmarkCase("memory", "How do agents use memory?", EVIDENCE, required_citation_ids=("e1",)),)
        with tempfile.TemporaryDirectory() as directory:
            report = run_model_comparison(
                cases, {"open": ("open-model", FakeClient()), "frontier": ("front-model", FakeClient())},
                work_dir=Path(directory) / "work", output_path=Path(directory) / "report.json", repetitions=2)
        summary = report["providers"]["open"]["summary"]
        self.assertEqual(summary["cases"], 2)
        self.assertEqual(summary["consistency_rate"], 1.0)
        self.assertEqual(summary["stopping_compliance"], 1.0)

    def test_unsupported_claim_metric_runs_without_completeness_labels(self):
        cases = (BenchmarkCase("memory", "How do agents use memory?", EVIDENCE,
                               forbidden_citation_ids=("e2",)),)
        with tempfile.TemporaryDirectory() as directory:
            report = run_model_comparison(
                cases, {"open": ("open-model", FakeClient()), "frontier": ("front-model", FakeClient())},
                work_dir=Path(directory) / "work", output_path=Path(directory) / "report.json")
        summary = report["providers"]["open"]["summary"]
        self.assertIsNone(summary["completeness_accuracy"])
        self.assertEqual(summary["unsupported_claim_accuracy"], 1.0)

    def test_suite_budget_stops_and_reports_incomplete_comparison(self):
        cases = (BenchmarkCase("memory", "How do agents use memory?", EVIDENCE),)
        limits = {"max_minutes": 120, "max_model_calls": 1, "max_cost_usd": 50.0,
                  "stop_at_budget_fraction": 0.8}
        with tempfile.TemporaryDirectory() as directory, patch(
                "llm_gym.agent.model_evaluation.model_evaluation_parameters", return_value=limits):
            report = run_model_comparison(
                cases, {"open": ("open-model", FakeClient()), "frontier": ("front-model", FakeClient())},
                work_dir=Path(directory) / "work", output_path=Path(directory) / "report.json")
        self.assertEqual(report["stop_reason"], "SUITE_BUDGET_EXHAUSTED")
        self.assertFalse(report["suite_usage"]["complete"])
        self.assertFalse(report["comparison_contract"]["same_cases"])
        self.assertFalse(report["comparison_contract"]["complete"])
        self.assertEqual(set(report["providers"]), {"open"})
