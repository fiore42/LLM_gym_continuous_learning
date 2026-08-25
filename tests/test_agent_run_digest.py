import argparse
import unittest

from llm_gym.agent.agent_task import TaskSpec
from llm_gym.agent.significance import SIGNIFICANCE_PROMPT_VERSION
from scripts.agent_run_digest import (MAX_ITEM_RETRIES,
                                      available_digest_prompt_versions,
                                      bounded_item_retries,
                                      digest_artifact_prefix,
                                      digest_prompt_version,
                                      provider_request_budget_units, window_days)


class WindowDaysTests(unittest.TestCase):
    """Cost scales with the window, so the denominator has to reflect it.

    Per day of content spans 1.7x across measured windows while per item spans
    15x, because item cost tracks transcript length and day cost averages over
    however many items that day produced.
    """

    def test_the_window_length_drives_the_denominator(self):
        week = window_days({"since": "2026-07-31T00:00:00+00:00",
                            "until": "2026-08-07T00:00:00+00:00"})
        month = window_days({"since": "2026-07-08T00:00:00+00:00",
                             "until": "2026-08-07T00:00:00+00:00"})
        self.assertEqual(week, 7.0)
        self.assertEqual(month, 30.0)

    def test_a_sub_day_window_still_bills_as_one_day(self):
        """Otherwise a one-hour window derives a budget near zero."""
        self.assertEqual(window_days({"since": "2026-08-06T00:00:00+00:00",
                                      "until": "2026-08-06T01:00:00+00:00"}), 1.0)


class ArtifactPathTests(unittest.TestCase):
    def test_windows_models_and_arms_each_get_their_own_path(self):
        paths = {
            digest_artifact_prefix("data/w/a.json", "glm-5.2", "OPEN_WEIGHT"),
            digest_artifact_prefix("data/w/b.json", "glm-5.2", "OPEN_WEIGHT"),
            digest_artifact_prefix("data/w/a.json", "claude-sonnet-5", "AGENT"),
        }
        self.assertEqual(len(paths), 3)

    def test_prompt_versions_cannot_overwrite_each_other(self):
        self.assertNotEqual(
            digest_artifact_prefix("data/w/a.json", "glm-5.2", "OPEN_WEIGHT", "significance-v1"),
            digest_artifact_prefix("data/w/a.json", "glm-5.2", "OPEN_WEIGHT", "significance-v2"),
        )


class DigestBudgetTests(unittest.TestCase):
    def test_call_budget_reserves_the_configured_retry_for_each_item(self):
        item_count = 328
        self.assertEqual(MAX_ITEM_RETRIES, 1)
        self.assertEqual(provider_request_budget_units(item_count), 656)
        self.assertEqual(provider_request_budget_units(item_count, 3), 1312)
        spec = TaskSpec.for_unit_count(
            "digest", "window", provider_request_budget_units(item_count))
        self.assertGreaterEqual(
            spec.max_model_calls * spec.stop_at_budget_fraction,
            item_count * (1 + MAX_ITEM_RETRIES),
        )

    def test_retry_override_is_bounded(self):
        self.assertEqual(bounded_item_retries("3"), 3)
        with self.assertRaises(argparse.ArgumentTypeError):
            bounded_item_retries("6")


if __name__ == "__main__":
    unittest.main()


class PromptVersionSelectionTests(unittest.TestCase):
    """An older digest prompt must be selectable, and must change the paths.

    Without this flag the runner always used the latest registered prompt, so
    two prompt versions could never be compared on the same window — the only
    v1-vs-v2 evidence in the repository compares different windows as a result.
    """

    def test_every_registered_version_is_offered(self):
        available = available_digest_prompt_versions()
        self.assertIn(SIGNIFICANCE_PROMPT_VERSION, available)
        self.assertIn("significance-v1", available)
        self.assertEqual(available, sorted(available, reverse=True))

    def test_an_unknown_version_is_rejected_before_any_call(self):
        with self.assertRaises(argparse.ArgumentTypeError) as raised:
            digest_prompt_version("significance-v99")
        self.assertIn("available", str(raised.exception))

    def test_a_registered_version_is_accepted(self):
        self.assertEqual(digest_prompt_version("significance-v1"), "significance-v1")

    def test_two_versions_of_one_window_write_to_different_paths(self):
        first = digest_artifact_prefix("data/digest-windows/w.json", "glm-5.2",
                                       "OPEN_WEIGHT", "significance-v1")
        second = digest_artifact_prefix("data/digest-windows/w.json", "glm-5.2",
                                        "OPEN_WEIGHT", "significance-v2")
        self.assertNotEqual(first, second)
        self.assertTrue(first.endswith("significance-v1"))
        self.assertTrue(second.endswith("significance-v2"))


class PromptVersionReachesTheRunTests(unittest.TestCase):
    """The flag has to reach `run_digest` and the artifact paths, not just parse.

    Rule 29: `main()` decides the output path from the flag, and that decision
    needs its own test. Asserting only that the validator accepts a version
    leaves the wiring uncovered — a `main()` that parses the flag and then keeps
    passing the module default still passes every other test in this class.
    """

    def _main_with(self, version):
        import json, sys, tempfile
        from pathlib import Path
        from unittest import mock
        import scripts.agent_run_digest as cli

        from llm_gym.corpus.window import SNAPSHOT_VERSION
        snapshot = {"snapshot_version": SNAPSHOT_VERSION,
                    "since": "2026-07-31T00:00:00+00:00",
                    "until": "2026-08-07T00:00:00+00:00",
                    "platforms": ["youtube"], "index_signature": "i:1:2",
                    "items": [{"evidence_id": "e1"}]}
        captured = {}

        def fake_run_digest(**kwargs):
            captured.update(kwargs)
            return {"outcome": "COMPLETED", "stop_reason": "UNITS_EXHAUSTED",
                    "complete": True, "cache_hit": False, "items_total": 1,
                    "items_assessed": 1, "items_rejected": 0, "label_counts": {},
                    "model_calls": 1, "cost_usd": 0.0, "provider_calls": 1,
                    "provider_calls_exact": True}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "w.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            argv = ["agent_run_digest.py", "--snapshot", str(path),
                    "--model", "m", "--prompt-version", version]
            with mock.patch.object(sys, "argv", argv), \
                 mock.patch.object(cli, "run_digest", fake_run_digest), \
                 mock.patch.object(cli, "model_client_from_environment", lambda **k: object()), \
                 mock.patch.object(cli, "attach_item_text", lambda index, items: [
                     {**item, "text": "some source text"} for item in items]):
                cli.main()
        return captured

    def test_the_requested_version_is_what_the_run_receives(self):
        for version in ("significance-v1", "significance-v2"):
            with self.subTest(version=version):
                captured = self._main_with(version)
                self.assertEqual(captured["prompt_version"], version)

    def test_the_requested_version_is_what_the_paths_carry(self):
        for version in ("significance-v1", "significance-v2"):
            with self.subTest(version=version):
                captured = self._main_with(version)
                self.assertTrue(str(captured["output_path"]).endswith(f"{version}-report.json"))
                self.assertTrue(str(captured["checkpoint_path"]).endswith(f"{version}-checkpoint.json"))
