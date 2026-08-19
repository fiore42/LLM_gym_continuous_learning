import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm_gym.agent.agent_task import TaskOutcome, TaskSpec
from llm_gym.agent.bounded_loop import (BudgetGuard, CheckpointStore, LoopPhase, LoopStop,
                                        UnitOutcome, run_bounded_loop)

KEY = "digest-window-2026-08"
START = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)


def _spec(**overrides) -> TaskSpec:
    values = {"task_id": "digest", "question": "Summarise the window",
              "max_rounds": 3, "max_minutes": 60, "max_model_calls": 100,
              "max_cost_usd": 1.0, "stop_at_budget_fraction": 0.8,
              "minimum_eval_pass_fraction": 0.8}
    values.update(overrides)
    return TaskSpec(**values)


class PerItemLoopTests(unittest.TestCase):
    """Drive the extracted loop with a workload it was not written for.

    ``run_agent_task`` iterates over quality rounds, re-drafting one answer.
    This drives the same machinery over a list of corpus items, one bounded
    unit each, which is the shape the digest needs. An abstraction that only
    ever serves its original caller has not been shown to be reusable, so this
    is the deliverable of the extraction rather than an extra test.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.checkpoint = root / "digest-checkpoint.json"
        self.store = CheckpointStore(
            checkpoint_path=self.checkpoint,
            reusable_outcomes=frozenset({TaskOutcome.COMPLETED.value}),
        )
        self.addCleanup(self._tmp.cleanup)

    def _snapshot(self, processed: list[str]):
        def snapshot(phase: LoopPhase, item: str) -> dict:
            return {"cache_key": KEY, "outcome": TaskOutcome.RUNNING.value,
                    "phase": phase.value, "current_item": item,
                    "processed": list(processed)}
        return snapshot

    def test_every_item_is_durable_before_the_next_one_starts(self):
        """A kill between items must not cost the items already paid for."""
        items = ["a", "b", "c", "d"]
        processed: list[str] = []
        observed_on_disk: list[list[str]] = []

        def perform(item: str, remaining_seconds: int) -> UnitOutcome:
            # Read what a killed process would have found at this instant.
            observed_on_disk.append(json.loads(
                self.checkpoint.read_text(encoding="utf-8"))["processed"])
            processed.append(item)
            return UnitOutcome(cost_usd=0.01)

        run = run_bounded_loop(
            items,
            guard=BudgetGuard(_spec(), started=START, clock=lambda: START),
            store=self.store, perform=perform, snapshot=self._snapshot(processed))

        self.assertEqual(run.stop, LoopStop.UNITS_EXHAUSTED)
        self.assertEqual(processed, items)
        # Each item started with its predecessors already on disk, which is the
        # per-item durability the digest needs and the round loop never showed.
        self.assertEqual(observed_on_disk, [[], ["a"], ["a", "b"], ["a", "b", "c"]])

    def test_resuming_skips_completed_items_and_keeps_their_spend(self):
        items = ["a", "b", "c", "d"]
        processed: list[str] = []

        def perform_until_c(item: str, remaining_seconds: int) -> UnitOutcome:
            processed.append(item)
            # Simulate a non-retryable provider failure part-way through.
            return UnitOutcome(cost_usd=0.02, stop=item == "b")

        first = run_bounded_loop(
            items, guard=BudgetGuard(_spec(), started=START, clock=lambda: START),
            store=self.store, perform=perform_until_c,
            snapshot=self._snapshot(processed))
        self.assertEqual(first.stop, LoopStop.UNIT_STOPPED)
        self.assertEqual(processed, ["a", "b"])

        # A later invocation reads the checkpoint rather than starting over.
        resumed = self.store.resume(KEY)
        self.assertIsNone(resumed.reusable)
        self.assertIsNotNone(resumed.resumable)
        done = resumed.resumable["processed"]
        # The stopped unit is an attempted, non-retryable call. Its result and
        # spend are durable even though it stopped the sequence.
        self.assertEqual(done, ["a", "b"])

        # The resumed guard continues the predecessor's budget rather than
        # restarting it: spend already made still counts against the cap.
        second_processed = list(done)
        guard = BudgetGuard(_spec(), started=START, units=len(done), cost_usd=0.04,
                            clock=lambda: START)
        second = run_bounded_loop(
            [item for item in items if item not in done],
            guard=guard, store=self.store,
            perform=lambda item, remaining: (second_processed.append(item)
                                             or UnitOutcome(cost_usd=0.02)),
            snapshot=self._snapshot(second_processed))

        self.assertEqual(second.stop, LoopStop.UNITS_EXHAUSTED)
        # Neither attempted item is repeated, and every remaining item runs once.
        self.assertEqual(second_processed, ["a", "b", "c", "d"])
        self.assertEqual(guard.units, 4)
        self.assertEqual(guard.model_calls, 4)
        self.assertAlmostEqual(guard.cost_usd, 0.08)

    def test_internal_retries_count_as_provider_calls_not_loop_units(self):
        processed: list[str] = []
        guard = BudgetGuard(
            _spec(max_model_calls=2, stop_at_budget_fraction=1.0),
            started=START, clock=lambda: START)
        run = run_bounded_loop(
            ["a", "b"], guard=guard, store=self.store,
            perform=lambda item, remaining: (processed.append(item)
                                             or UnitOutcome(model_calls=2)),
            snapshot=self._snapshot(processed))

        self.assertEqual(run.stop, LoopStop.BUDGET_REACHED)
        self.assertEqual(processed, ["a"])
        self.assertEqual(guard.units, 1)
        self.assertEqual(guard.model_calls, 2)

    def test_a_cost_budget_stops_the_sequence_before_it_is_finished(self):
        """A resource stop must halt mid-sequence, not run the workload out."""
        items = ["a", "b", "c", "d", "e"]
        processed: list[str] = []

        run = run_bounded_loop(
            items,
            # 80% of $1.00 is reached once three items have cost $0.30 each.
            guard=BudgetGuard(_spec(max_cost_usd=1.0), started=START, clock=lambda: START),
            store=self.store,
            perform=lambda item, remaining: (processed.append(item)
                                             or UnitOutcome(cost_usd=0.30)),
            snapshot=self._snapshot(processed))

        self.assertEqual(run.stop, LoopStop.BUDGET_REACHED)
        self.assertEqual(processed, ["a", "b", "c"])

    def test_a_resume_with_no_time_left_starts_no_further_item(self):
        """The wall clock is inherited, so a resume can be out of time at once.

        A resumed guard keeps its predecessor's ``started``. If that budget is
        already spent, the loop must refuse before performing any unit rather
        than doing one more item's work it cannot afford.
        """
        items = ["a", "b", "c"]
        processed: list[str] = []
        long_after = START + timedelta(minutes=61)

        run = run_bounded_loop(
            items,
            guard=BudgetGuard(_spec(max_minutes=60), started=START,
                              clock=lambda: long_after),
            store=self.store,
            perform=lambda item, remaining: (processed.append(item)
                                             or UnitOutcome(cost_usd=0.0)),
            snapshot=self._snapshot(processed))

        self.assertEqual(run.stop, LoopStop.TIME_EXHAUSTED)
        self.assertEqual(processed, [])

    def test_a_stopped_unit_is_checkpointed_after_its_work(self):
        processed: list[str] = []
        run = run_bounded_loop(
            ["a", "b"],
            guard=BudgetGuard(_spec(), started=START, clock=lambda: START),
            store=self.store,
            perform=lambda item, remaining: (processed.append(item)
                                             or UnitOutcome(cost_usd=0.25, stop=True)),
            snapshot=self._snapshot(processed),
        )
        saved = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        self.assertEqual(run.stop, LoopStop.UNIT_STOPPED)
        self.assertEqual(processed, ["a"])
        self.assertEqual(saved["phase"], LoopPhase.AFTER_UNIT.value)
        self.assertEqual(saved["processed"], ["a"])

    def test_the_deadline_handed_to_a_unit_is_the_one_just_tested(self):
        """A unit's request timeout must match the budget the loop checked."""
        seen: list[int] = []
        run = run_bounded_loop(
            ["only"],
            guard=BudgetGuard(_spec(max_minutes=60), started=START,
                              clock=lambda: START + timedelta(minutes=15)),
            store=self.store,
            perform=lambda item, remaining: (seen.append(remaining)
                                             or UnitOutcome(cost_usd=0.0)),
            snapshot=self._snapshot([]))
        self.assertEqual(run.stop, LoopStop.UNITS_EXHAUSTED)
        self.assertEqual(seen, [45 * 60])

    def _store_with_cache(self) -> CheckpointStore:
        return CheckpointStore(
            checkpoint_path=self.checkpoint,
            cache_path=self.checkpoint.with_name("cache.json"),
            reusable_outcomes=frozenset({TaskOutcome.COMPLETED.value}),
        )

    def test_a_cached_success_outlives_a_later_run_taking_the_checkpoint(self):
        """The cache is the durable success store; the checkpoint is scratch.

        ``finish`` writes the checkpoint for every outcome but the cache only
        for reusable ones. That distinction is invisible while the checkpoint
        still holds the same key — ``resume`` will return it from there — so it
        only shows once another run has taken the checkpoint over.
        """
        store = self._store_with_cache()
        store.finish({"cache_key": KEY, "outcome": TaskOutcome.COMPLETED.value,
                      "answer": "the finished work"})

        # A different task now runs and leaves its own state behind.
        store.write({"cache_key": "some-other-question",
                     "outcome": TaskOutcome.RUNNING.value})

        resumed = store.resume(KEY)
        self.assertIsNotNone(resumed.reusable)
        self.assertEqual(resumed.reusable["answer"], "the finished work")

    def test_a_terminal_failure_is_never_cached_as_reusable(self):
        """Otherwise a later run returns an exhausted failure without retrying.

        Guarded twice, deliberately: ``finish`` declines to write it and
        ``resume`` declines to return it. Assert both, because either alone
        leaves the other free to rot — widening ``reusable_outcomes`` later
        would otherwise silently make a stale cached failure reusable.
        """
        store = self._store_with_cache()
        store.finish({"cache_key": KEY, "outcome": TaskOutcome.FAILED_BUDGET.value})
        store.write({"cache_key": "some-other-question",
                     "outcome": TaskOutcome.RUNNING.value})

        self.assertFalse(store.cache_path.is_file(), "a failure must not reach the cache")
        resumed = store.resume(KEY)
        self.assertIsNone(resumed.reusable)
        self.assertIsNone(resumed.resumable)

    def test_a_checkpoint_from_different_work_is_not_resumed(self):
        """Keying is what stops one run inheriting another's progress."""
        self.store.write({"cache_key": "a-different-window",
                          "outcome": TaskOutcome.RUNNING.value, "processed": ["x", "y"]})
        resumed = self.store.resume(KEY)
        self.assertIsNone(resumed.reusable)
        self.assertIsNone(resumed.resumable)


if __name__ == "__main__":
    unittest.main()
