import math
import unittest

from llm_gym.shared.settings import agent_parameters
from llm_gym.agent.agent_task import (
    BooleanEvaluation, TaskOutcome, TaskSpec, budget_stop_reached, evaluate_quality,
)


class AgentTaskContractTests(unittest.TestCase):
    def test_global_task_spec_is_valid_and_bounded(self):
        spec = TaskSpec.from_global_parameters("demo", "Explain agent memory")
        spec.validate()
        self.assertEqual(spec.max_rounds, 3)
        self.assertEqual(TaskOutcome.ESCALATED_FOR_REVIEW, "ESCALATED_FOR_REVIEW")

    def test_quality_gate_allows_imperfect_noncritical_score(self):
        result = evaluate_quality([
            BooleanEvaluation("support", True, True),
            BooleanEvaluation("citations", True, True),
            BooleanEvaluation("style", False),
            BooleanEvaluation("completeness", True),
            BooleanEvaluation("format", True),
        ], minimum_pass_fraction=0.8)
        self.assertTrue(result["passed"])
        self.assertEqual(result["pass_fraction"], 0.8)

    def test_quality_gate_rejects_critical_failure(self):
        result = evaluate_quality([
            BooleanEvaluation("support", False, True),
            BooleanEvaluation("style", True),
            BooleanEvaluation("format", True),
            BooleanEvaluation("citations", True),
            BooleanEvaluation("completeness", True),
        ], minimum_pass_fraction=0.8)
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "CRITICAL_EVALUATION_FAILED")

    def test_budget_stops_at_the_configured_fraction(self):
        """Assert the fraction rule, not the numbers the config happens to hold.

        This previously hardcoded 16 model calls, which was 80% of a
        max_model_calls of 20. Raising that budget for the digest broke the
        test without anything being wrong, so derive the boundary from the spec
        and the test survives a budget change while still pinning the rule.
        """
        spec = TaskSpec.from_global_parameters("demo", "question")
        at_threshold = math.ceil(spec.max_model_calls * spec.stop_at_budget_fraction)
        self.assertTrue(budget_stop_reached(spec, round_number=1, model_calls=at_threshold,
                                            cost_usd=0, elapsed_minutes=1))
        self.assertFalse(budget_stop_reached(spec, round_number=1, model_calls=at_threshold - 1,
                                            cost_usd=0, elapsed_minutes=1))
        # Each budget stops independently of the others.
        self.assertTrue(budget_stop_reached(
            spec, round_number=1, model_calls=1,
            cost_usd=spec.max_cost_usd * spec.stop_at_budget_fraction, elapsed_minutes=1))
        self.assertTrue(budget_stop_reached(
            spec, round_number=1, model_calls=1, cost_usd=0,
            elapsed_minutes=spec.max_minutes * spec.stop_at_budget_fraction))

    def test_round_limit_is_not_reported_as_resource_budget(self):
        spec = TaskSpec.from_global_parameters("demo", "question")
        self.assertFalse(budget_stop_reached(spec, round_number=spec.max_rounds,
                                             model_calls=spec.max_rounds,
                                             cost_usd=0, elapsed_minutes=1))


class FittedCallBudgetTests(unittest.TestCase):
    """The runaway guard scales with the work; the spend cap does not.

    One absolute call budget cannot serve a three-round question and a
    three-hundred-item window. Money does not scale with intended work, so
    max_cost_usd stays absolute.
    """

    def test_a_long_window_gets_a_budget_that_lets_it_finish(self):
        spec = TaskSpec.for_unit_count("digest", "window", 328)
        self.assertGreaterEqual(spec.max_model_calls * spec.stop_at_budget_fraction, 328)

    def test_the_budget_accounts_for_the_stop_fraction(self):
        """Fitting the budget exactly to the work would stop it short."""
        spec = TaskSpec.for_unit_count("digest", "window", 328)
        self.assertGreater(spec.max_model_calls, 328)

    def test_a_short_window_is_not_given_less_than_the_configured_default(self):
        default = TaskSpec.from_global_parameters("task", "question").max_model_calls
        self.assertEqual(TaskSpec.for_unit_count("digest", "window", 3).max_model_calls,
                         default)

    def test_an_absurd_unit_count_is_capped_by_the_ceiling(self):
        """A derived budget grows with a bug in the estimate that produced it."""
        ceiling = int(agent_parameters()["max_model_calls_ceiling"])
        spec = TaskSpec.for_unit_count("digest", "window", 100_000)
        self.assertEqual(spec.max_model_calls, ceiling)

    def test_the_spend_cap_is_untouched_by_the_workload(self):
        absolute = TaskSpec.from_global_parameters("task", "question").max_cost_usd
        self.assertEqual(TaskSpec.for_unit_count("digest", "window", 328).max_cost_usd,
                         absolute)

    def test_a_non_positive_unit_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unit_count must be positive"):
            TaskSpec.for_unit_count("digest", "window", 0)

    def test_a_supplied_cost_budget_is_fitted_and_scales_with_the_run(self):
        """A flat cap is 44x looser than a question needs and nearly binding
        on a long window: one number doing two jobs badly."""
        short = TaskSpec.for_unit_count("d", "w", 5, cost_budget_usd=0.25)
        long_run = TaskSpec.for_unit_count("d", "w", 328, cost_budget_usd=7.5)
        self.assertLess(short.max_cost_usd, long_run.max_cost_usd)
        # Fitted above the request, so the stop fraction does not halt it early.
        self.assertGreaterEqual(long_run.max_cost_usd * long_run.stop_at_budget_fraction, 7.5)

    def test_a_supplied_budget_never_falls_below_the_single_task_cap(self):
        spec = TaskSpec.for_unit_count("d", "w", 1, cost_budget_usd=0.0001)
        self.assertEqual(spec.max_cost_usd,
                         float(agent_parameters()["max_cost_usd_per_task"]))

    def test_an_absurd_cost_budget_is_capped_by_the_ceiling(self):
        ceiling = float(agent_parameters()["max_cost_usd_ceiling"])
        spec = TaskSpec.for_unit_count("d", "w", 10, cost_budget_usd=10_000.0)
        self.assertEqual(spec.max_cost_usd, ceiling)

    def test_omitting_a_cost_budget_keeps_the_single_task_cap(self):
        self.assertEqual(TaskSpec.for_unit_count("d", "w", 328).max_cost_usd,
                         TaskSpec.from_global_parameters("t", "q").max_cost_usd)

    def test_the_stop_threshold_lands_above_the_unit_count_not_on_it(self):
        """A 328-item digest attempted every item and still reported
        FAILED_BUDGET, because the guard tests `>=` and the threshold was
        exactly 328."""
        for units in (1, 5, 49, 328, 1000):
            with self.subTest(units=units):
                spec = TaskSpec.for_unit_count("d", "w", units)
                threshold = spec.max_model_calls * spec.stop_at_budget_fraction
                self.assertGreater(threshold, units,
                                   "the final unit must not trip the guard")
                self.assertFalse(budget_stop_reached(
                    spec, round_number=units, model_calls=units,
                    cost_usd=0, elapsed_minutes=0))
