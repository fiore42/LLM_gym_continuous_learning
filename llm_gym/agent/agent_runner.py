"""Bounded agent-task orchestration with retries, cache, and escalation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_task import BooleanEvaluation, TaskOutcome, TaskSpec, TaskStage, evaluate_quality
from .bounded_loop import (BudgetGuard, CheckpointStore, LoopPhase, UnitOutcome,
                           run_bounded_loop, utc_now)
from ..shared.loops import LoopType, new_loop_context
from .model_client import ModelProviderError
from .prompt_registry import load_prompt
from .synthesis import PROMPT_VERSION, SynthesisRequest, SynthesisResult, render_prompt, synthesize


EVALUATION_POLICY_VERSION = "answer-gates-v3"
_CACHEABLE_OUTCOMES = frozenset({
    TaskOutcome.COMPLETED.value, TaskOutcome.COMPLETED_AFTER_RETRY.value,
    TaskOutcome.INSUFFICIENT_EVIDENCE.value, TaskOutcome.CONFLICTING_EVIDENCE.value,
})


def _cache_key(spec: TaskSpec, evidence: tuple[dict[str, Any], ...], model: str,
               prompt_version: str) -> str:
    value = {
        "task_id": spec.task_id, "question": spec.question,
        "evidence_ids": sorted(str(item["evidence_id"]) for item in evidence),
        "model": model, "prompt_version": prompt_version,
        "output_schema_version": spec.output_schema_version,
        "evaluation_policy": EVALUATION_POLICY_VERSION,
        "limits": {
            "max_rounds": spec.max_rounds, "max_minutes": spec.max_minutes,
            "max_model_calls": spec.max_model_calls, "max_cost_usd": spec.max_cost_usd,
            "stop_at_budget_fraction": spec.stop_at_budget_fraction,
            "minimum_eval_pass_fraction": spec.minimum_eval_pass_fraction,
        },
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _revision_feedback(attempts: list[dict[str, Any]], *, prompt_version: str) -> str:
    """Turn the latest failed attempt into targeted revision instructions."""
    if not attempts:
        return ""
    templates = load_prompt(version=prompt_version).revision_templates
    last_attempt = attempts[-1]
    if last_attempt.get("status") == "FAILED":
        return templates["validation_error"].format(
            error=str(last_attempt.get("error") or "unknown validation error")
        )
    failed = last_attempt.get("evaluation", {}).get("failed", [])
    return (templates["failed_criteria"].format(criteria=", ".join(failed))
            if failed else "")


_REVIEWER_ACTIONS = {
    "BUDGET_EXHAUSTED": "Raise the task budget or narrow the question, then rerun.",
    "PROVIDER_REQUEST_FAILED": "Check provider credentials and status, then rerun.",
    "QUALITY_GATE_NOT_REACHED": "Review the failed criteria against the cited evidence; "
                                "repair the evidence or adjust the question, then rerun.",
}


def _human_review_package(
    spec: TaskSpec,
    evidence: tuple[dict[str, Any], ...],
    attempts: list[dict[str, Any]],
    *,
    reason: str,
    cost_usd: float,
    model: str,
) -> dict[str, Any]:
    """Build an escalation package a reviewer can act on without the code.

    Carries the failed criteria, the last output actually produced, the
    evidence the task was given, the budget state at the stop, and an
    explicit next action, so unresolved work is diagnosable from the
    checkpoint alone.
    """
    last_attempt = attempts[-1] if attempts else {}
    last_synthesis = last_attempt.get("synthesis") or {}
    return {
        "reason": reason,
        "attempt_count": len(attempts),
        "failed_criteria": last_attempt.get("evaluation", {}).get("failed", []),
        "last_error": last_attempt.get("error"),
        "last_output": {
            "answer": last_synthesis.get("answer"),
            "classification": last_synthesis.get("classification"),
            "citation_ids": list(last_synthesis.get("citation_ids") or ()),
        },
        "evidence_ids": [str(item.get("evidence_id")) for item in evidence],
        "budget_state": {
            "model": model,
            "model_calls": len(attempts),
            "max_rounds": spec.max_rounds,
            "cost_usd": round(cost_usd, 8),
            "max_cost_usd": spec.max_cost_usd,
        },
        "reviewer_next_action": _REVIEWER_ACTIONS.get(
            reason, "Inspect the attempt history and decide whether to rerun."
        ),
    }


def _evaluate(result: SynthesisResult, evidence: tuple[dict[str, Any], ...], *, minimum_pass_fraction: float) -> dict[str, Any]:
    # Requiring citations for at least two available evidence items makes the
    # non-critical partial-credit gate meaningful on multi-source cases.
    coverage_target = min(2, len(evidence))
    conflict_citation_coverage = (
        result.classification != TaskOutcome.CONFLICTING_EVIDENCE.value
        or len(set(result.citation_ids)) >= 2
    )
    return evaluate_quality([
        BooleanEvaluation("answer_nonempty", bool(result.answer.strip()), critical=True),
        BooleanEvaluation("citations_present", bool(result.citation_ids), critical=True),
        BooleanEvaluation("citation_validation", bool(result.validation.get("passed")), critical=True),
        BooleanEvaluation("classification_valid", result.classification in {
            "SUPPORTED", "INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE",
        }, critical=True),
        BooleanEvaluation("conflict_citation_coverage", conflict_citation_coverage, critical=True,
                          details="conflicting evidence requires at least two distinct citations"),
        BooleanEvaluation("citation_coverage", len(set(result.citation_ids)) >= coverage_target),
        BooleanEvaluation("output_schema", bool(result.answer) and bool(result.classification)),
    ], minimum_pass_fraction=minimum_pass_fraction)


def run_agent_task(
    spec: TaskSpec,
    evidence: tuple[dict[str, Any], ...],
    client,
    *,
    model: str,
    checkpoint_path: str | Path,
    cache_path: str | Path,
    parent_run_id: str | None = None,
    prompt_version: str = PROMPT_VERSION,
) -> dict[str, Any]:
    """Run a bounded synthesis task and resume matching in-progress checkpoints."""
    spec.validate()
    selected_prompt = load_prompt(version=prompt_version)
    prompt_version = selected_prompt.prompt_version
    key = _cache_key(spec, evidence, model, prompt_version)
    store = CheckpointStore(Path(checkpoint_path), Path(cache_path),
                            reusable_outcomes=_CACHEABLE_OUTCOMES)
    resume = store.resume(key)
    if resume.reusable is not None:
        return {**resume.reusable, "cache_hit": True}

    checkpoint_state = resume.resumable
    loop = (checkpoint_state.get("loop") if checkpoint_state else None) or new_loop_context(
        LoopType.AGENT_TASK, parent_run_id=parent_run_id)
    started_at = (checkpoint_state or {}).get("started_at") or utc_now().isoformat()
    started = datetime.fromisoformat(started_at)
    attempts: list[dict[str, Any]] = list((checkpoint_state or {}).get("attempts") or [])
    # Deliberately the ORIGINAL start, not this invocation's. A task's rounds are
    # one conversation with a deadline, so a resume must not buy a fresh timer;
    # test_resume_past_the_time_budget_spends_no_further_call pins that. The
    # digest does the opposite for a stated reason — see run_digest.
    guard = BudgetGuard(spec, started, units=len(attempts), model_calls=len(attempts),
                        cost_usd=sum(float((attempt.get("usage") or {}).get("cost_usd", 0.0) or 0.0)
                                     for attempt in attempts))
    revision_feedback = _revision_feedback(attempts, prompt_version=prompt_version)
    non_retryable_provider_error = bool(
        (checkpoint_state or {}).get("non_retryable_provider_error"))

    def snapshot(phase: LoopPhase, round_number: int) -> dict[str, Any]:
        drafting = phase is LoopPhase.BEFORE_UNIT and round_number == 1
        return {"task_id": spec.task_id, "question": spec.question,
                "outcome": TaskOutcome.RUNNING.value, "cache_key": key,
                "cache_hit": False, "loop": loop, "started_at": started_at,
                "attempts": attempts, "model_calls": len(attempts),
                "cost_usd": round(guard.cost_usd, 8),
                "non_retryable_provider_error": non_retryable_provider_error,
                "current_stage": (TaskStage.DRAFT if drafting else TaskStage.REVISE).value}

    def perform(round_number: int, remaining_seconds: int) -> UnitOutcome:
        nonlocal revision_feedback, non_retryable_provider_error
        request = SynthesisRequest(
            spec.question, evidence, model, revision_feedback=revision_feedback,
            request_timeout_seconds=remaining_seconds)
        prompt_record = render_prompt(request)[2]
        round_cost = 0.0
        try:
            if hasattr(client, "last_usage"):
                client.last_usage = {}
            synthesis = synthesize(request, client)
            usage = getattr(client, "last_usage", {}) or {}
            round_cost = float(usage.get("cost_usd", 0.0) or 0.0)
            evaluation = _evaluate(synthesis, evidence,
                                   minimum_pass_fraction=spec.minimum_eval_pass_fraction)
            attempt = {"round": round_number, "status": "EVALUATED",
                        "synthesis": synthesis.to_dict(), "evaluation": evaluation,
                        "usage": {**usage, "cost_usd": round_cost}}
            attempts.append(attempt)
            if evaluation["passed"]:
                if synthesis.classification == TaskOutcome.INSUFFICIENT_EVIDENCE.value:
                    outcome = TaskOutcome.INSUFFICIENT_EVIDENCE
                elif synthesis.classification == TaskOutcome.CONFLICTING_EVIDENCE.value:
                    outcome = TaskOutcome.CONFLICTING_EVIDENCE
                elif round_number > 1:
                    outcome = TaskOutcome.COMPLETED_AFTER_RETRY
                else:
                    outcome = TaskOutcome.COMPLETED

                def finish() -> dict[str, Any]:
                    return {"task_id": spec.task_id, "question": spec.question,
                            "outcome": outcome.value, "cache_key": key,
                            "cache_hit": False, "attempts": attempts,
                            "loop": loop, "started_at": started_at,
                            "finished_at": utc_now().isoformat(),
                            "stop_reason": "QUALITY_GATE_PASSED",
                            "model_calls": len(attempts),
                            "cost_usd": round(guard.cost_usd, 8),
                            "elapsed_seconds": round(guard.elapsed_seconds(), 3),
                            "completed_stages": ["prepare", "retrieve", "draft", "evaluate"]
                            + (["revise", "draft", "evaluate"] if round_number > 1 else [])
                            + ["finalize", "checkpoint"]}

                return UnitOutcome(cost_usd=round_cost, finish=finish)
        except ModelProviderError as exc:
            usage = dict(getattr(client, "last_usage", {}) or {})
            round_cost = float(usage.get("cost_usd", 0.0) or 0.0)
            attempts.append({"round": round_number, "status": "FAILED",
                             "error_type": type(exc).__name__, "error": str(exc),
                             "prompt": prompt_record,
                             "usage": {**usage, "cost_usd": round_cost}})
            if not exc.retryable:
                non_retryable_provider_error = True
                return UnitOutcome(cost_usd=round_cost, stop=True)
        except (ValueError, TimeoutError) as exc:
            usage = dict(getattr(client, "last_usage", {}) or {})
            round_cost = float(usage.get("cost_usd", 0.0) or 0.0)
            attempts.append({"round": round_number, "status": "FAILED",
                             "error_type": type(exc).__name__, "error": str(exc),
                             "prompt": prompt_record,
                             "usage": {**usage, "cost_usd": round_cost}})
        revision_feedback = _revision_feedback(attempts, prompt_version=prompt_version)
        if not revision_feedback:
            revision_feedback = selected_prompt.revision_templates["fallback"]
        # Failed provider responses are still attempts. Their usage is stored
        # in the attempt before the post-unit checkpoint so a killed process
        # cannot lose billed spend when it resumes.
        return UnitOutcome(cost_usd=round_cost)

    remaining_rounds = (() if non_retryable_provider_error
                        else range(len(attempts) + 1, spec.max_rounds + 1))
    run = run_bounded_loop(remaining_rounds,
                           guard=guard, store=store, perform=perform, snapshot=snapshot)
    if run.finished is not None:
        return run.finished

    resource_budget_exhausted = guard.stop_reached()
    outcome = (TaskOutcome.FAILED_BUDGET if resource_budget_exhausted
               else TaskOutcome.ESCALATED_FOR_REVIEW)
    reason = ("BUDGET_EXHAUSTED" if resource_budget_exhausted
              else "PROVIDER_REQUEST_FAILED" if non_retryable_provider_error
              else "QUALITY_GATE_NOT_REACHED")
    result = {"task_id": spec.task_id, "question": spec.question,
              "outcome": outcome.value, "cache_key": key,
              "cache_hit": False, "attempts": attempts,
              "loop": loop, "started_at": started_at,
              "finished_at": utc_now().isoformat(),
              "stop_reason": reason,
              "model_calls": len(attempts),
              "cost_usd": round(guard.cost_usd, 8),
              "elapsed_seconds": round(guard.elapsed_seconds(), 3),
              "completed_stages": ["prepare", "retrieve", "draft", "evaluate", "escalate", "checkpoint"],
              "human_review": _human_review_package(
                  spec, evidence, attempts, reason=reason,
                  cost_usd=guard.cost_usd, model=model)}
    store.finish(result)
    return result
