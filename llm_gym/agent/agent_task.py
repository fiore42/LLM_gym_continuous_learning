"""Contracts and deterministic gates for bounded long-running agent tasks."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Any, Iterable

from ..shared.settings import agent_parameters


class TaskStage(StrEnum):
    PREPARE = "prepare"
    RETRIEVE = "retrieve"
    DRAFT = "draft"
    EVALUATE = "evaluate"
    REVISE = "revise"
    FINALIZE = "finalize"
    ESCALATE = "escalate"
    CHECKPOINT = "checkpoint"


class TaskOutcome(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_AFTER_RETRY = "COMPLETED_AFTER_RETRY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    ESCALATED_FOR_REVIEW = "ESCALATED_FOR_REVIEW"
    FAILED_BUDGET = "FAILED_BUDGET"


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    question: str
    max_rounds: int
    max_minutes: int
    max_model_calls: int
    max_cost_usd: float
    stop_at_budget_fraction: float
    minimum_eval_pass_fraction: float
    output_schema_version: int = 1

    @classmethod
    def for_unit_count(cls, task_id: str, question: str, unit_count: int,
                       *, cost_budget_usd: float | None = None) -> "TaskSpec":
        """A spec whose call budget is fitted to the work, under a fixed ceiling.

        An absolute call budget cannot serve both a three-round question and a
        three-hundred-item window: the same number is idle headroom for one and
        a wall for the other. So the runaway guard is derived from the work,
        while the spend cap stays absolute, because money does not scale with
        how much work you intended to do.

        Divided by the stop fraction because the guard stops at that fraction
        of the budget. Fitting the budget exactly to the work would guarantee
        the run stops short: 328 items against a 0.8 fraction halts at 262. The
        threshold must also land strictly above the unit count, not on it, or
        the final unit trips the guard after its work is complete.

        Still capped by ``max_model_calls_ceiling``. A derived budget grows
        along with a bug in the estimate that produced it, so a window
        selection returning fifty thousand items must hit something absolute.

        ``cost_budget_usd`` is the caller's expected spend for the whole run,
        which it knows better than this function does — a digest derives it from
        the window length in days, a measurement harness from its repetitions.
        It is divided by the stop fraction for the same reason as the call
        budget and capped by ``max_cost_usd_ceiling`` for the same reason. Left
        unset, the single-task cap applies: a flat cap that suits one question
        is 44 times looser than that question needs and nearly binding on a
        long run, which is one number doing two jobs badly.
        """
        if unit_count < 1:
            raise ValueError("unit_count must be positive")
        params = agent_parameters()
        fraction = float(params["stop_at_budget_fraction"])
        # unit_count + 1 because the guard tests `>=`: fitting the threshold to
        # exactly the unit count trips it on the final unit, after that unit's
        # work is already done, turning a finished run into FAILED_BUDGET. A
        # 328-item digest did exactly that.
        fitted = math.ceil((unit_count + 1) / fraction)
        ceiling = int(params["max_model_calls_ceiling"])
        base = cls.from_global_parameters(task_id, question)
        cost_ceiling = float(params["max_cost_usd_ceiling"])
        cost = base.max_cost_usd if cost_budget_usd is None else min(
            max(cost_budget_usd / fraction, base.max_cost_usd), cost_ceiling)
        return replace(base,
                       max_model_calls=min(max(fitted, base.max_model_calls), ceiling),
                       max_cost_usd=cost)

    @classmethod
    def from_global_parameters(cls, task_id: str, question: str) -> "TaskSpec":
        params = agent_parameters()
        return cls(task_id, question.strip(), params["max_rounds"], params["max_minutes"],
                   params["max_model_calls"], float(params["max_cost_usd"]),
                   float(params["stop_at_budget_fraction"]),
                   float(params["minimum_eval_pass_fraction"]))

    def validate(self) -> None:
        if not self.task_id.strip() or not self.question.strip():
            raise ValueError("task_id and question must not be empty")
        if self.max_rounds < 1 or self.max_minutes < 1 or self.max_model_calls < 1:
            raise ValueError("task limits must be positive")
        if self.max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be positive")
        if not 0 < self.stop_at_budget_fraction <= 1:
            raise ValueError("stop_at_budget_fraction must be between 0 and 1")
        if not 0 < self.minimum_eval_pass_fraction <= 1:
            raise ValueError("minimum_eval_pass_fraction must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class BooleanEvaluation:
    name: str
    passed: bool
    critical: bool = False
    details: str = ""


def evaluate_quality(
    evaluations: Iterable[BooleanEvaluation],
    *,
    minimum_pass_fraction: float,
) -> dict[str, Any]:
    """Apply a non-100% threshold while requiring every critical gate."""
    items = list(evaluations)
    if not items:
        return {"passed": False, "pass_fraction": 0.0, "failed": [], "reason": "NO_EVALUATIONS"}
    failed = [item.name for item in items if not item.passed]
    critical_failures = [item.name for item in items if item.critical and not item.passed]
    pass_fraction = sum(item.passed for item in items) / len(items)
    passed = not critical_failures and pass_fraction >= minimum_pass_fraction
    reason = "PASSED" if passed else ("CRITICAL_EVALUATION_FAILED" if critical_failures else "EVAL_THRESHOLD_NOT_MET")
    return {"passed": passed, "pass_fraction": round(pass_fraction, 4),
            "failed": failed, "critical_failures": critical_failures, "reason": reason}


def budget_stop_reached(spec: TaskSpec, *, round_number: int, model_calls: int,
                        cost_usd: float, elapsed_minutes: float) -> bool:
    """Return whether a resource budget requires stopping.

    The quality-round limit is intentionally not a resource budget. The
    runner owns that separate stopping condition so it can distinguish a
    quality-gate escalation from a genuine budget failure.
    """
    fraction = spec.stop_at_budget_fraction
    return (model_calls >= spec.max_model_calls * fraction
            or cost_usd >= spec.max_cost_usd * fraction
            or elapsed_minutes >= spec.max_minutes * fraction)
