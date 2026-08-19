import contextlib
import io
import unittest
from unittest.mock import patch

from scripts import agent_run_digest
from scripts import agent_run_retrieval_retry
from scripts import agent_run_task_on_checkpoint
from scripts import eval_compare_model_providers
from scripts import eval_run_suite


class PaidCliExitCodeTests(unittest.TestCase):
    """Incomplete paid work must be visible to shell automation."""

    def _quiet(self):
        return contextlib.redirect_stdout(io.StringIO())

    def test_agent_task_exit_tracks_terminal_outcome(self):
        for outcome, expected in (("COMPLETED", 0), ("ESCALATED_FOR_REVIEW", 1)):
            with self.subTest(outcome=outcome), \
                    patch.object(agent_run_task_on_checkpoint, "load_dotenv"), \
                    patch.object(agent_run_task_on_checkpoint, "run_from_checkpoint",
                                 return_value={"outcome": outcome}), \
                    patch("sys.argv", ["agent", "--model", "model"]), self._quiet():
                self.assertEqual(agent_run_task_on_checkpoint.main(), expected)

    def test_eval_suite_exit_tracks_suite_completion(self):
        for reason, expected in (("SUITE_COMPLETE", 0),
                                 ("SUITE_COST_BUDGET_EXHAUSTED", 1)):
            with self.subTest(reason=reason), \
                    patch.object(eval_run_suite, "load_dotenv"), \
                    patch.object(eval_run_suite, "run_suite",
                                 return_value={"suite_stop_reason": reason}), \
                    patch("sys.argv", ["suite", "--model", "model"]), self._quiet():
                self.assertEqual(eval_run_suite.main(), expected)

    def test_digest_exit_tracks_complete_flag(self):
        snapshot = {
            "since": "2026-08-01T00:00:00+00:00",
            "until": "2026-08-02T00:00:00+00:00",
            "items": [{"evidence_id": "e1"}],
        }
        base = {
            "outcome": "COMPLETED", "stop_reason": "UNITS_EXHAUSTED",
            "cache_hit": False, "items_total": 1, "items_assessed": 1,
            "items_rejected": 0, "label_counts": {}, "model_calls": 1,
            "cost_usd": 0.01,
        }
        for complete, expected in ((True, 0), (False, 1)):
            with self.subTest(complete=complete), \
                    patch.object(agent_run_digest, "load_dotenv"), \
                    patch.object(agent_run_digest, "load_snapshot", return_value=snapshot), \
                    patch.object(agent_run_digest, "attach_item_text",
                                 return_value=snapshot["items"]), \
                    patch.object(agent_run_digest, "model_client_from_environment"), \
                    patch.object(agent_run_digest, "run_digest",
                                 return_value={**base, "complete": complete}), \
                    patch("sys.argv", ["digest", "--snapshot", "window.json",
                                       "--model", "model"]), self._quiet():
                self.assertEqual(agent_run_digest.main(), expected)

    def test_retrieval_retry_exit_tracks_trace_error(self):
        for error, expected in ((None, 0), ("provider failed", 1)):
            with self.subTest(error=error), \
                    patch.object(agent_run_retrieval_retry, "load_dotenv"), \
                    patch.object(agent_run_retrieval_retry, "load_case",
                                 return_value={"question": "Q", "expected_outcome": "SUPPORTED"}), \
                    patch.object(agent_run_retrieval_retry, "model_client_from_environment"), \
                    patch.object(agent_run_retrieval_retry, "run_case",
                                 return_value={"error": error}), \
                    patch.object(agent_run_retrieval_retry, "atomic_write_text"), \
                    patch("sys.argv", ["retry", "--case", "case", "--model", "model"]), \
                    self._quiet():
                self.assertEqual(agent_run_retrieval_retry.main(), expected)

    def test_provider_comparison_exit_tracks_contract_completion(self):
        for complete, expected in ((True, 0), (False, 1)):
            report = {"comparison_contract": {"complete": complete}}
            with self.subTest(complete=complete), \
                    patch.object(eval_compare_model_providers, "load_dotenv"), \
                    patch.object(eval_compare_model_providers, "validate_benchmark_source"), \
                    patch.object(eval_compare_model_providers, "load_benchmark_cases",
                                 return_value=[]), \
                    patch.object(eval_compare_model_providers,
                                 "model_client_from_environment"), \
                    patch.object(eval_compare_model_providers, "run_model_comparison",
                                 return_value=report), \
                    patch("sys.argv", ["compare", "--frontier-model", "frontier",
                                       "--open-weight-model", "open"]), self._quiet():
                self.assertEqual(eval_compare_model_providers.main(), expected)


if __name__ == "__main__":
    unittest.main()
