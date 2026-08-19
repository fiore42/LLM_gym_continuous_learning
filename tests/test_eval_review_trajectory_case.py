import json
import unittest
from pathlib import Path

from scripts.eval_review_trajectory_case import list_cases, review


SUITE = "config/agent_eval_suite.json"


class ReviewTrajectoryCaseTests(unittest.TestCase):
    def test_listing_every_case_succeeds(self):
        self.assertEqual(list_cases(SUITE), 0)

    def test_reviewing_a_known_case_resolves_its_proof(self):
        # --no-run keeps this offline: the proving test is located and printed,
        # but pytest is not invoked recursively from inside a test.
        self.assertEqual(
            review("budget_stop_distinct", suite_path=SUITE, run_test=False), 0
        )

    def test_unknown_case_fails_and_does_not_raise(self):
        self.assertEqual(review("no_such_case", suite_path=SUITE, run_test=False), 1)

    def test_every_case_can_be_reviewed_without_a_missing_proof(self):
        """Each trajectory case must resolve to a test that still exists.

        The validator enforces this too; asserting it here means a renamed
        test breaks the suite even if nobody runs the validator.
        """
        payload = json.loads(Path(SUITE).read_text(encoding="utf-8"))
        for case in payload["trajectory_cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertEqual(
                    review(case["case_id"], suite_path=SUITE, run_test=False), 0
                )


if __name__ == "__main__":
    unittest.main()
