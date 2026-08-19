import unittest

from llm_gym.shared.status import completion_exit_code, task_outcome_exit_code


class ExitCodeTests(unittest.TestCase):
    def test_consumable_task_outcomes_exit_successfully(self):
        for outcome in (
            "COMPLETED", "COMPLETED_AFTER_RETRY",
            "INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE",
        ):
            with self.subTest(outcome=outcome):
                self.assertEqual(task_outcome_exit_code(outcome), 0)

    def test_incomplete_or_unresolved_task_outcomes_exit_nonzero(self):
        for outcome in (
            None, "RUNNING", "FAILED_BUDGET", "ESCALATED_FOR_REVIEW",
        ):
            with self.subTest(outcome=outcome):
                self.assertEqual(task_outcome_exit_code(outcome), 1)

    def test_multi_unit_completion_controls_exit_status(self):
        self.assertEqual(completion_exit_code(True), 0)
        self.assertEqual(completion_exit_code(False), 1)


if __name__ == "__main__":
    unittest.main()
