import argparse
import unittest

from llm_gym.agent.agent_task import TaskSpec
from scripts.agent_run_digest import (MAX_ITEM_RETRIES, bounded_item_retries,
                                      digest_artifact_prefix,
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
