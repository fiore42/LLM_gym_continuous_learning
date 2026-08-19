"""Deterministic A/B evaluation of model providers on identical task cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_runner import run_agent_task
from .agent_task import TaskOutcome, TaskSpec
from ..shared.settings import agent_parameters, model_evaluation_parameters
from ..shared.atomic import atomic_write_text
from ..shared.loops import LoopType, new_loop_context


MODEL_EVALUATION_VERSION = 1


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    question: str
    evidence: tuple[dict[str, Any], ...]
    expected_outcome: str = "SUPPORTED"
    required_citation_ids: tuple[str, ...] = ()
    forbidden_citation_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkCase":
        case = cls(str(payload["case_id"]), str(payload["question"]),
                   tuple(payload.get("evidence") or ()),
                   str(payload.get("expected_outcome", "SUPPORTED")),
                   tuple(str(item) for item in payload.get("required_citation_ids") or ()),
                   tuple(str(item) for item in payload.get("forbidden_citation_ids") or ()))
        case.validate()
        return case

    def validate(self) -> None:
        if not self.case_id.strip() or not self.question.strip():
            raise ValueError("benchmark case_id and question must not be empty")
        if not self.evidence:
            raise ValueError(f"benchmark case {self.case_id} requires evidence")
        evidence_ids = {str(item.get("evidence_id")) for item in self.evidence}
        unknown = sorted((set(self.required_citation_ids) | set(self.forbidden_citation_ids)) - evidence_ids)
        if unknown:
            raise ValueError(f"benchmark case {self.case_id} requires unknown evidence IDs: {unknown}")


def load_benchmark_cases(path: str | Path) -> tuple[BenchmarkCase, ...]:
    """Load versioned benchmark cases without contacting a model provider."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = tuple(BenchmarkCase.from_dict(item) for item in payload.get("cases", ()))
    if not cases:
        raise ValueError("benchmark file must contain at least one case")
    return cases


def _provider_timing(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum per-call latency and tokens across every attempt in the suite.

    Throughput is the figure to rank providers by. Raw latency scales with how
    much the model chose to write, so a more verbose model reads as slower
    than it is; and because the totals are summed before dividing, a long case
    is not weighted the same as a short one.
    """
    latency = 0.0
    output_tokens = 0
    for result in results:
        for attempt in result.get("attempts") or []:
            usage = attempt.get("usage") or {}
            latency += float(usage.get("latency_seconds") or 0.0)
            output_tokens += int(usage.get("output_tokens") or 0)
    return {
        "model_latency_seconds": round(latency, 3),
        "output_tokens": output_tokens,
        "output_tokens_per_second": round(output_tokens / latency, 2) if latency > 0 else None,
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    completed = sum(result["outcome"] in {
        TaskOutcome.COMPLETED.value, TaskOutcome.COMPLETED_AFTER_RETRY.value,
        TaskOutcome.INSUFFICIENT_EVIDENCE.value, TaskOutcome.CONFLICTING_EVIDENCE.value,
    } for result in results)
    classification_checks = [
        attempt.get("synthesis", {}).get("classification") == result.get("expected_outcome")
        for result in results
        for attempt in result.get("attempts", [])[-1:]
        if attempt.get("synthesis")
    ]
    by_case: dict[str, list[str]] = {}
    for result in results:
        final_attempt = (result.get("attempts") or [{}])[-1]
        classification = (final_attempt.get("synthesis") or {}).get("classification")
        by_case.setdefault(result["case_id"], []).append(classification)
    consistency_checks = [len(set(values)) == 1 for values in by_case.values() if values]
    completeness_checks = []
    completeness_failures: list[str] = []
    unsupported_claim_checks = []
    unsupported_claim_failures: list[str] = []
    for result in results:
        required = set(result.get("required_citation_ids") or ())
        final_attempt = (result.get("attempts") or [{}])[-1]
        cited = set((final_attempt.get("synthesis") or {}).get("citation_ids") or ())
        if required:
            passed = required <= cited
            completeness_checks.append(passed)
            if not passed:
                completeness_failures.append(result["case_id"])
        forbidden = set(result.get("forbidden_citation_ids") or ())
        if forbidden:
            final_attempt = (result.get("attempts") or [{}])[-1]
            cited = set((final_attempt.get("synthesis") or {}).get("citation_ids") or ())
            passed = not (forbidden & cited)
            unsupported_claim_checks.append(passed)
            if not passed:
                unsupported_claim_failures.append(result["case_id"])
    critical_failures: dict[str, int] = {}
    for result in results:
        for attempt in result.get("attempts", []):
            for criterion in attempt.get("evaluation", {}).get("critical_failures", []):
                critical_failures[criterion] = critical_failures.get(criterion, 0) + 1
    passed_results = [result for result in results if result.get("outcome") in {
        TaskOutcome.COMPLETED.value, TaskOutcome.COMPLETED_AFTER_RETRY.value,
        TaskOutcome.INSUFFICIENT_EVIDENCE.value, TaskOutcome.CONFLICTING_EVIDENCE.value,
    }]
    retries_to_pass = sum(max((result.get("attempts") or [{}])[-1].get("round", 1) - 1, 0)
                          for result in passed_results)
    params = agent_parameters()
    valid_stops = []
    for result in results:
        outcome = result.get("outcome")
        stop_reason = result.get("stop_reason")
        calls_valid = 0 < result.get("model_calls", 0) <= params["max_rounds"]
        reason_valid = ((outcome in {TaskOutcome.COMPLETED.value, TaskOutcome.COMPLETED_AFTER_RETRY.value,
                                     TaskOutcome.INSUFFICIENT_EVIDENCE.value,
                                     TaskOutcome.CONFLICTING_EVIDENCE.value}
                        and stop_reason == "QUALITY_GATE_PASSED")
                        or (outcome == TaskOutcome.FAILED_BUDGET.value and stop_reason == "BUDGET_EXHAUSTED")
                        or (outcome == TaskOutcome.ESCALATED_FOR_REVIEW.value
                            and stop_reason == "QUALITY_GATE_NOT_REACHED"))
        valid_stops.append(calls_valid and reason_valid)
    return {
        "cases": len(results),
        "passed": completed,
        "pass_rate": round(completed / len(results), 4) if results else 0.0,
        "escalated": sum(result["outcome"] == TaskOutcome.ESCALATED_FOR_REVIEW.value for result in results),
        "retries": sum(max(len(result.get("attempts", [])) - 1, 0) for result in results),
        "retries_to_pass": retries_to_pass,
        "critical_failures": critical_failures,
        "budget_failures": sum(result.get("outcome") == TaskOutcome.FAILED_BUDGET.value for result in results),
        "estimated_cost_usd": round(sum(float(result.get("cost_usd", 0.0) or 0.0) for result in results), 8),
        "model_calls": sum(result.get("model_calls", 0) for result in results),
        "elapsed_seconds": round(sum(result.get("elapsed_seconds", 0) for result in results), 3),
        # elapsed_seconds is wall clock and includes local retrieval and
        # checkpoint writes; these two isolate the provider itself.
        **_provider_timing(results),
        "classification_accuracy": round(sum(classification_checks) / len(classification_checks), 4)
        if classification_checks else 0.0,
        "completeness_cases": len(completeness_checks),
        "completeness_accuracy": round(sum(completeness_checks) / len(completeness_checks), 4)
        if completeness_checks else None,
        "completeness_failures": completeness_failures,
        "unsupported_claim_cases": len(unsupported_claim_checks),
        "unsupported_claim_accuracy": round(sum(unsupported_claim_checks) / len(unsupported_claim_checks), 4)
        if unsupported_claim_checks else None,
        "unsupported_claim_failures": unsupported_claim_failures,
        "consistency_rate": round(sum(consistency_checks) / len(consistency_checks), 4)
        if consistency_checks else 0.0,
        "stopping_compliance": round(sum(valid_stops) / len(valid_stops), 4) if valid_stops else 0.0,
    }


def run_model_comparison(
    cases: tuple[BenchmarkCase, ...],
    providers: dict[str, tuple[str, Any]],
    *,
    work_dir: str | Path,
    output_path: str | Path,
    repetitions: int = 1,
) -> dict[str, Any]:
    """Run every case once per provider with the same task inputs and limits."""
    if len(providers) < 2:
        raise ValueError("model comparison requires at least two providers")
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    for case in cases:
        case.validate()
    started_at = datetime.now(timezone.utc)
    loop = new_loop_context(LoopType.MODEL_EVALUATION)
    suite_params = model_evaluation_parameters()
    suite_cost = 0.0
    suite_calls = 0
    suite_stopped = False
    stop_reason = "SUITE_COMPLETED"
    work = Path(work_dir)
    provider_results: dict[str, list[dict[str, Any]]] = {}
    for provider_name, (model, client) in providers.items():
        results = []
        for case in cases:
            for repetition in range(1, repetitions + 1):
                spec = TaskSpec.from_global_parameters(case.case_id, case.question)
                result = run_agent_task(
                    spec, case.evidence, client, model=model,
                    checkpoint_path=work / provider_name / str(repetition) / f"{case.case_id}.json",
                    cache_path=work / provider_name / str(repetition) / f"{case.case_id}.cache.json",
                    parent_run_id=loop["run_id"],
                )
                results.append({"case_id": case.case_id, "repetition": repetition,
                                "expected_outcome": case.expected_outcome,
                                "required_citation_ids": list(case.required_citation_ids),
                                "forbidden_citation_ids": list(case.forbidden_citation_ids), **result})
                suite_cost += float(result.get("cost_usd", 0.0) or 0.0)
                suite_calls += int(result.get("model_calls", 0) or 0)
                elapsed_minutes = (datetime.now(timezone.utc) - started_at).total_seconds() / 60
                fraction = suite_params["stop_at_budget_fraction"]
                suite_stopped = (
                    elapsed_minutes >= suite_params["max_minutes"] * fraction
                    or suite_calls >= suite_params["max_model_calls"] * fraction
                    or suite_cost >= suite_params["max_cost_usd"] * fraction
                )
                if suite_stopped:
                    stop_reason = "SUITE_BUDGET_EXHAUSTED"
                    break
            if suite_stopped:
                break
        provider_results[provider_name] = results
        if suite_stopped:
            break
    report = {
        "report_version": MODEL_EVALUATION_VERSION,
        "loop": loop,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "stop_reason": stop_reason,
        "suite_usage": {"model_calls": suite_calls, "estimated_cost_usd": round(suite_cost, 8),
                         "complete": not suite_stopped},
        "providers": {name: {"model": providers[name][0], "summary": _summary(results),
                             "results": results}
                      for name, results in provider_results.items()},
        "comparison_contract": {
            "same_cases": not suite_stopped,
            "same_evidence": True,
            "same_task_parameters": True,
            "complete": not suite_stopped,
        },
    }
    atomic_write_text(output_path, json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report
