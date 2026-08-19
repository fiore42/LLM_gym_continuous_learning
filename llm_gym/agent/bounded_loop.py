"""Checkpoint, budget, and driver machinery shared by bounded agent loops.

Extracted from ``run_agent_task``, which iterates over quality rounds. The
digest loop iterates over corpus items instead, but wants the same three
guarantees: work is durable after every unit, a kill resumes without repeating
paid work, and the resource budgets stop the loop rather than the workload
running to completion. Only the unit of work differs, so only the unit of work
is injected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Iterable

from .agent_task import TaskOutcome, TaskSpec, budget_stop_reached
from ..shared.atomic import atomic_write_text


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_state(path: Path) -> dict[str, Any] | None:
    """Read a JSON object, treating an unreadable file as an absent one.

    A process killed mid-write can leave truncated JSON behind. Neither the
    checkpoint nor the cache is authoritative enough to fail the next run over,
    so a file that will not parse is discarded and the run restarts.
    """
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


@dataclass(frozen=True)
class ResumeState:
    """What the checkpoint and cache pair say about a run with a given key.

    The two fields are mutually exclusive: either a finished result may be
    returned without calling the provider, or in-progress work may continue.
    """

    reusable: dict[str, Any] | None = None
    resumable: dict[str, Any] | None = None


@dataclass(frozen=True)
class CheckpointStore:
    """Durable loop state, keyed so unrelated work cannot inherit it.

    ``key`` is a fingerprint of everything that would change the answer. A
    checkpoint whose key does not match belongs to a different run even when it
    sits at the same path, so it is neither reused nor resumed.
    """

    checkpoint_path: Path
    cache_path: Path | None = None
    reusable_outcomes: frozenset[str] = frozenset()
    # Which outcomes still have work worth continuing. RUNNING always does. A
    # caller whose terminal state leaves retryable work behind adds it here: an
    # escalated digest has items that could not be assessed, and restarting it
    # from scratch would rerun every assessment already paid for.
    resumable_outcomes: frozenset[str] = frozenset({TaskOutcome.RUNNING.value})

    def resume(self, key: str) -> ResumeState:
        cached = _read_state(self.cache_path) if self.cache_path is not None else None
        if (cached is not None and cached.get("cache_key") == key
                and cached.get("outcome") in self.reusable_outcomes):
            return ResumeState(reusable=cached)
        state = _read_state(self.checkpoint_path)
        if state is None or state.get("cache_key") != key:
            return ResumeState()
        if state.get("outcome") in self.reusable_outcomes:
            return ResumeState(reusable=state)
        # A terminal failure is a historical run, not resumable progress. Only
        # an in-progress checkpoint may continue its units; otherwise a later
        # command would reopen an exhausted failure and return it without
        # calling the provider again.
        if state.get("outcome") not in self.resumable_outcomes:
            return ResumeState()
        return ResumeState(resumable=state)

    def write(self, state: dict[str, Any]) -> None:
        atomic_write_text(self.checkpoint_path,
                          json.dumps(state, indent=2, ensure_ascii=False) + "\n")

    def finish(self, result: dict[str, Any]) -> None:
        """Persist a terminal result, caching it only if it may be reused."""
        self.write(result)
        if self.cache_path is not None and result.get("outcome") in self.reusable_outcomes:
            atomic_write_text(self.cache_path,
                              json.dumps(result, indent=2, ensure_ascii=False) + "\n")


@dataclass
class BudgetGuard:
    """Accumulated spend and elapsed time measured against a spec's budgets.

    ``units`` and ``cost_usd`` are seeded from a resumed checkpoint and
    ``started`` from the original run's start time, so a resume continues the
    predecessor's budget instead of restarting it on a fresh timer.
    """

    spec: TaskSpec
    started: datetime
    units: int = 0
    model_calls: int | None = None
    cost_usd: float = 0.0
    clock: Callable[[], datetime] = utc_now

    def __post_init__(self) -> None:
        # Most loops make exactly one provider request per unit. Callers with
        # internal retries pass the independently recovered request count.
        if self.model_calls is None:
            self.model_calls = self.units

    def elapsed_seconds(self) -> float:
        return (self.clock() - self.started).total_seconds()

    def remaining_seconds(self) -> int:
        return int(self.spec.max_minutes * 60 - self.elapsed_seconds())

    def charge(self, cost_usd: float) -> None:
        self.cost_usd += float(cost_usd or 0.0)

    def count_unit(self) -> None:
        self.units += 1

    def count_model_calls(self, count: int) -> None:
        self.model_calls = int(self.model_calls or 0) + count

    def stop_reached(self) -> bool:
        return budget_stop_reached(self.spec, round_number=self.units,
                                   model_calls=int(self.model_calls or 0),
                                   cost_usd=self.cost_usd,
                                   elapsed_minutes=self.elapsed_seconds() / 60)


class LoopPhase(StrEnum):
    """Which side of a unit of work a checkpoint is being written from."""

    BEFORE_UNIT = "BEFORE_UNIT"
    AFTER_UNIT = "AFTER_UNIT"


class LoopStop(StrEnum):
    FINISHED = "FINISHED"
    UNITS_EXHAUSTED = "UNITS_EXHAUSTED"
    TIME_EXHAUSTED = "TIME_EXHAUSTED"
    BUDGET_REACHED = "BUDGET_REACHED"
    UNIT_STOPPED = "UNIT_STOPPED"


@dataclass(frozen=True)
class UnitOutcome:
    """What one unit of work cost and what it decided about the loop."""

    cost_usd: float = 0.0
    # A unit usually makes one provider request, but a digest item may retry
    # inside the unit. Resource accounting must count requests, not loop items.
    model_calls: int = 1
    # Builds the terminal result. Called after this unit's cost is charged so
    # the result records the spend that produced it.
    finish: Callable[[], dict[str, Any]] | None = None
    # A stop the budgets cannot see, such as a provider error that must not be
    # retried. The driver still writes the post-unit checkpoint first so a
    # process death before terminal finalization cannot lose the attempt.
    stop: bool = False


@dataclass(frozen=True)
class LoopRun:
    stop: LoopStop
    finished: dict[str, Any] | None = None


def run_bounded_loop(
    units: Iterable[Any],
    *,
    guard: BudgetGuard,
    store: CheckpointStore,
    perform: Callable[[Any, int], UnitOutcome],
    snapshot: Callable[[LoopPhase, Any], dict[str, Any]],
) -> LoopRun:
    """Drive checkpoint, do one unit, account for usage, check budgets, repeat.

    ``perform`` receives the unit and the seconds left in the wall-clock
    budget, which is passed rather than re-read so the request deadline matches
    the value the loop itself just tested. ``snapshot`` renders the caller's
    durable state; the driver owns when it is written, not what is in it.
    """
    for unit in units:
        remaining_seconds = guard.remaining_seconds()
        if remaining_seconds < 1:
            return LoopRun(LoopStop.TIME_EXHAUSTED)
        store.write(snapshot(LoopPhase.BEFORE_UNIT, unit))
        outcome = perform(unit, remaining_seconds)
        guard.count_unit()
        guard.count_model_calls(outcome.model_calls)
        guard.charge(outcome.cost_usd)
        if outcome.finish is not None:
            result = outcome.finish()
            store.finish(result)
            return LoopRun(LoopStop.FINISHED, result)
        store.write(snapshot(LoopPhase.AFTER_UNIT, unit))
        if outcome.stop:
            return LoopRun(LoopStop.UNIT_STOPPED)
        if guard.stop_reached():
            return LoopRun(LoopStop.BUDGET_REACHED)
    return LoopRun(LoopStop.UNITS_EXHAUSTED)
