"""Run a frozen corpus window as one long, resumable, budgeted task.

This is the composition step: the window is already frozen (`corpus/window.py`)
and a single item is already assessable (`significance.py`), so this adds no new
machinery. It drives them with the loop extracted from `run_agent_task`
(`bounded_loop.py`), which is what that extraction existed to make possible.

Duration comes from the number of items, not from a padded budget: every call
stays small, and a kill between any two items loses nothing that was paid for.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .agent_task import TaskOutcome, TaskSpec
from .bounded_loop import (BudgetGuard, CheckpointStore, LoopPhase, LoopStop, UnitOutcome,
                           run_bounded_loop, utc_now)
from .model_client import ModelProviderError
from .prompt_registry import load_prompt
from .significance import (DIGEST_PROMPT_ROOT, SIGNIFICANCE_LABELS, SIGNIFICANCE_PROMPT_VERSION,
                           SignificanceRequest, assess_item)
from ..shared.loops import LoopType, new_loop_context
from ..shared.run_log import RunLogger

DIGEST_SCHEMA_VERSION = 1
# A stop that means "every item was assessed" for this loop shape. The driver
# reports units exhausted; only the caller knows that is success here.
_COMPLETE = LoopStop.UNITS_EXHAUSTED


def digest_cache_key(snapshot: dict[str, Any], model: str, prompt_version: str) -> str:
    """Fingerprint everything that could change the digest's content.

    Includes the window, the index it was taken from, the model and the prompt
    version. A checkpoint whose key differs belongs to a different digest even
    at the same path, so it is neither resumed nor reused.
    """
    value = {
        "schema": DIGEST_SCHEMA_VERSION,
        "index_signature": snapshot.get("index_signature"),
        "since": snapshot.get("since"),
        "until": snapshot.get("until"),
        "platforms": sorted(snapshot.get("platforms") or []),
        "item_ids": sorted(str(item.get("evidence_id")) for item in snapshot.get("items") or []),
        "model": model,
        "prompt_version": prompt_version,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass
class DigestProgress:
    """Assessments kept so far, plus the spend and failures behind them."""

    assessments: list[dict[str, Any]]
    rejected: list[dict[str, Any]]
    provider_usage: list[dict[str, Any]] = field(default_factory=list)
    provider_calls_exact: bool = True
    legacy_rejections_cleared: int = 0

    @property
    def assessed_ids(self) -> set[str]:
        return {str(row["item_id"]) for row in self.assessments}

    def label_counts(self) -> dict[str, int]:
        counts = {label: 0 for label in SIGNIFICANCE_LABELS}
        for row in self.assessments:
            counts[row["significance"]] = counts.get(row["significance"], 0) + 1
        return counts


def rank_assessments(assessments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order by significance, then oldest first within a label.

    Deterministic: the model judges one item at a time and never sees the
    ranking, so ordering stays code's responsibility and the same assessments
    always produce the same report.
    """
    priority = {label: index for index, label in enumerate(SIGNIFICANCE_LABELS)}
    return sorted(
        assessments,
        key=lambda row: (priority.get(row["significance"], len(priority)),
                         str(row.get("published_at") or ""), str(row["item_id"])))


def run_digest(
    *,
    snapshot: dict[str, Any],
    model: str,
    client,
    spec: TaskSpec,
    checkpoint_path: str | Path,
    output_path: str | Path | None = None,
    prompt_version: str = SIGNIFICANCE_PROMPT_VERSION,
    max_item_retries: int = 1,
    run_log_path: str | Path | None = None,
    clock: Callable[[], Any] = utc_now,
) -> dict[str, Any]:
    """Assess every item in a frozen window, resuming an interrupted run."""
    items = list(snapshot.get("items") or [])
    if not items:
        raise ValueError("window snapshot contains no items")
    key = digest_cache_key(snapshot, model, prompt_version)
    prompt = load_prompt(version=prompt_version, root=DIGEST_PROMPT_ROOT)
    store = CheckpointStore(
        Path(checkpoint_path),
        reusable_outcomes=frozenset({TaskOutcome.COMPLETED.value}),
        # For this loop shape, every non-reusable terminal state leaves items
        # worth retrying and assessments worth keeping, so all of them resume.
        # Stated as "not COMPLETED" rather than a list, because enumerating it
        # once already missed FAILED_BUDGET: a 328-item run tripped its own
        # budget on the final unit and a re-run would then have reassessed all
        # 328 items and paid for them twice.
        resumable_outcomes=frozenset(
            outcome.value for outcome in TaskOutcome
            if outcome is not TaskOutcome.COMPLETED))
    resume = store.resume(key)
    if resume.reusable is not None:
        return {**resume.reusable, "cache_hit": True}

    state = resume.resumable or {}
    progress = DigestProgress(
        assessments=list(state.get("assessments") or []),
        rejected=list(state.get("rejected") or []),
        provider_usage=list(state.get("provider_usage") or []),
        provider_calls_exact=bool(state.get("provider_calls_exact", not state)),
    )
    # Older digest code could leave the same item both accepted and rejected.
    # Accepted work is the stronger terminal record; retaining the stale
    # rejection makes the window escalate forever because accepted IDs never
    # return to the pending queue.
    accepted_ids = progress.assessed_ids
    stale_rejections = [row for row in progress.rejected
                        if str(row.get("item_id")) in accepted_ids]
    if stale_rejections:
        progress.rejected = [row for row in progress.rejected
                             if str(row.get("item_id")) not in accepted_ids]
        progress.legacy_rejections_cleared = len(stale_rejections)

    if state and not progress.provider_usage:
        # Legacy checkpoints stored usage only on accepted assessments. Recover
        # what is knowable and mark the totals explicitly incomplete; failed
        # historical responses cannot be reconstructed after the fact.
        progress.provider_usage = [
            {"item_id": row.get("item_id"), "status": "ACCEPTED",
             **dict(row.get("usage") or {})}
            for row in progress.assessments if row.get("usage")
        ]
        progress.provider_calls_exact = False
    started_at = state.get("started_at") or clock().isoformat()
    loop = state.get("loop") or new_loop_context(LoopType.DIGEST)
    invocation_started = clock()
    # Deliberately THIS invocation's clock, unlike run_agent_task, which measures
    # from the original start so a resume cannot buy a fresh timer. The shapes
    # differ: a task's rounds are one conversation with a deadline, while a digest
    # is a queue of independent items. Inheriting the clock here would make a
    # window paused longer than max_minutes permanently unfinishable — 315 paid
    # assessments stranded because the calendar moved. Total work stays bounded by
    # the call and cost budgets, which are carried across resumes.
    legacy_call_floor = len(progress.assessments) + sum(
        int(row.get("attempts") or 1) for row in progress.rejected)
    recovered_provider_calls = int(
        state.get("provider_calls", state.get("model_calls", 0)) or 0)
    if state and "provider_calls" not in state:
        recovered_provider_calls = max(recovered_provider_calls, legacy_call_floor)
        progress.provider_calls_exact = False
    recovered_units = int(
        state.get("items_attempted", state.get("model_calls", len(progress.assessments))) or 0)
    guard = BudgetGuard(spec, started=clock(), units=recovered_units,
                        model_calls=recovered_provider_calls,
                        cost_usd=float(state.get("cost_usd") or 0.0), clock=clock)

    already = progress.assessed_ids
    pending = [item for item in items if str(item.get("evidence_id")) not in already]
    # A rejection records the current state of an item, not the history of every
    # attempt on it. Anything going back into the queue is no longer rejected,
    # and will be re-recorded if it fails again — otherwise a successful retry
    # leaves the window permanently escalated by its own stale entry.
    retrying = {str(item.get("evidence_id")) for item in pending}
    progress.rejected = [row for row in progress.rejected
                         if str(row.get("item_id")) not in retrying]

    def base(phase: str) -> dict[str, Any]:
        provider_calls = int(guard.model_calls or 0)
        usage_complete = (
            progress.provider_calls_exact
            and len(progress.provider_usage) >= provider_calls
            and all(any(key in row for key in (
                "input_tokens", "output_tokens", "cost_usd", "latency_seconds"))
                    for row in progress.provider_usage)
        )
        return {
            "schema_version": DIGEST_SCHEMA_VERSION,
            "cache_key": key,
            "loop": loop,
            "window": {**{k: snapshot.get(k) for k in ("since", "until", "platforms",
                                                       "index_signature")},
                       "days": _window_days(snapshot),
                       "considered": snapshot.get("considered"),
                       "sources": _source_counts(items)},
            "model": model,
            "prompt_version": prompt_version,
            "max_item_retries": max_item_retries,
            "prompt_sha256": prompt.sha256,
            "prompt_source_path": prompt.source_path,
            "started_at": started_at,
            "current_stage": phase,
            "items_total": len(items),
            "items_assessed": len(progress.assessments),
            "items_rejected": len(progress.rejected),
            "assessments": progress.assessments,
            "rejected": progress.rejected,
            "provider_usage": progress.provider_usage,
            "provider_calls": provider_calls,
            "provider_calls_exact": progress.provider_calls_exact,
            "provider_usage_complete": usage_complete,
            "legacy_rejections_cleared": progress.legacy_rejections_cleared,
            "cost_usd": round(guard.cost_usd, 8),
            # Compatibility alias. Both fields count provider requests, not
            # digest items; items_attempted is the separate workload counter.
            "model_calls": provider_calls,
            "items_attempted": guard.units,
        }

    def snapshot_state(phase: LoopPhase, item: dict[str, Any]) -> dict[str, Any]:
        return {**base(phase.value), "outcome": TaskOutcome.RUNNING.value,
                "current_item": str(item.get("evidence_id"))}

    def perform(item: dict[str, Any], remaining_seconds: int) -> UnitOutcome:
        feedback = ""
        cost = 0.0
        last_error: Exception | None = None
        attempts_made = 0
        for attempt in range(1 + max_item_retries):
            attempts_made += 1
            request = SignificanceRequest(
                item=item, model=model, prompt_version=prompt_version,
                revision_feedback=feedback, request_timeout_seconds=remaining_seconds)
            try:
                if hasattr(client, "last_usage"):
                    client.last_usage = {}
                result = assess_item(request, client)
            except (ModelProviderError, ValueError) as exc:
                usage = dict(getattr(client, "last_usage", {}) or {})
                cost += float(usage.get("cost_usd", 0.0) or 0.0)
                progress.provider_usage.append({
                    "item_id": str(item.get("evidence_id")), "attempt": attempt + 1,
                    "status": "REJECTED", "error_type": type(exc).__name__, **usage,
                })
                last_error = exc
                if isinstance(exc, ModelProviderError) and not exc.retryable:
                    progress.rejected.append(_rejection(item, exc, attempt))
                    # Non-retryable for this item only: the window continues.
                    return UnitOutcome(cost_usd=cost, model_calls=attempts_made)
                feedback = f"{exc}. {prompt.revision_templates['fallback']}"
                continue
            usage = dict(getattr(client, "last_usage", {}) or {})
            cost += float(usage.get("cost_usd", 0.0) or 0.0)
            progress.provider_usage.append({
                "item_id": str(item.get("evidence_id")), "attempt": attempt + 1,
                "status": "ACCEPTED", **usage,
            })
            row = result.to_dict()
            # The rendered prompt is a pure function of this item and the
            # versioned template, so storing it per assessment duplicates the
            # item text into the report: 48 items produced a 1.24 MB report and
            # an identical checkpoint, and every checkpoint write reserialised
            # the whole file. Keep the identity, drop the rendering.
            row["prompt_sha256"] = (row.pop("prompt", None) or {}).get("prompt_sha256")
            row["published_at"] = item.get("published_at_utc") or item.get("published_at")
            row["canonical_url"] = item.get("canonical_url")
            row["title"] = item.get("title")
            row["usage"] = usage
            progress.assessments.append(row)
            return UnitOutcome(cost_usd=cost, model_calls=attempts_made)
        # Report the failure that actually happened. Replacing it with "retries
        # exhausted" cost nothing until a long run produced fifteen rejections
        # that all said the same uninformative thing (Rule 4).
        progress.rejected.append(_rejection(
            item, last_error or RuntimeError("no attempt was made"), max_item_retries))
        return UnitOutcome(cost_usd=cost, model_calls=attempts_made)

    run = run_bounded_loop(pending, guard=guard, store=store, perform=perform,
                           snapshot=snapshot_state)

    attempted_every_item = run.stop is _COMPLETE
    # Every item was attempted, but some could not be assessed. That is an
    # escalation, not a completion: ESCALATED_FOR_REVIEW is outside the
    # reusable set, so the next invocation retries exactly those items instead
    # of returning a cached report that silently omits them.
    complete = attempted_every_item and not progress.rejected
    outcome = (TaskOutcome.COMPLETED if complete
               else TaskOutcome.FAILED_BUDGET if run.stop in {LoopStop.BUDGET_REACHED,
                                                              LoopStop.TIME_EXHAUSTED}
               else TaskOutcome.ESCALATED_FOR_REVIEW)
    ranked = rank_assessments(progress.assessments)
    invocation_elapsed = round((clock() - invocation_started).total_seconds(), 3)
    finished_at = clock().isoformat()
    run_wall_elapsed = round(
        (datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds(),
        3,
    )
    result = {
        **base("finalize"),
        "outcome": outcome.value,
        "stop_reason": run.stop.value,
        "cache_hit": False,
        "finished_at": finished_at,
        "complete": complete,
        "attempted_every_item": attempted_every_item,
        "label_counts": progress.label_counts(),
        # Wall clock spans an interruption; model time does not. Reporting one
        # without the other makes a resumed run look slow or a paused one fast.
        # Keep elapsed_seconds as a compatibility alias for this invocation.
        "elapsed_seconds": invocation_elapsed,
        "invocation_elapsed_seconds": invocation_elapsed,
        "run_wall_elapsed_seconds": run_wall_elapsed,
        "usage_totals": _usage_totals(progress.provider_usage),
        "ranked": ranked,
        # An unmeasured claim must not be implied by a tidy report.
        "evaluation_note": (
            "Rankings remain unvalidated: ROADMAP M6.2 audited selected model "
            "decisions, not missed claims or corpus-level ranking. Every assessment "
            "carries exact evidence quotes located in its source, so each judgement "
            "is checkable individually."
        ),
    }
    store.finish(result)
    # Rule 12: one chronological log across loops. The report is the detail; the
    # log is how a run is found later without knowing its artifact path.
    logger = RunLogger(**({"path": run_log_path} if run_log_path else {}),
                       run_id=loop["run_id"], loop_type=LoopType.DIGEST)
    logger.event(
        stage="digest", operation="run_digest", status=outcome.value,
        category="INFO" if complete else "WARNING",
        parameters={"window": result["window"], "model": model,
                    "prompt_version": prompt_version, "prompt_sha256": prompt.sha256,
                    "items_total": len(items)},
        output={"items_assessed": len(progress.assessments),
                "items_rejected": len(progress.rejected),
                "label_counts": result["label_counts"], "cost_usd": result["cost_usd"],
                "stop_reason": run.stop.value, "usage_totals": result["usage_totals"]},
        artifact_paths=[str(checkpoint_path)] + ([str(output_path)] if output_path else []),
        started_at=started_at, ended_at=result["finished_at"],
        duration_ms=result["run_wall_elapsed_seconds"] * 1000.0)
    if output_path is not None:
        from ..shared.atomic import atomic_write_text
        atomic_write_text(Path(output_path),
                          json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result


def _window_days(snapshot: dict[str, Any]) -> float:
    since = datetime.fromisoformat(str(snapshot["since"]))
    until = datetime.fromisoformat(str(snapshot["until"]))
    return round(max((until - since).total_seconds() / 86400.0, 1.0), 3)


def _source_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    """Which sources contributed, so a skewed window is visible in the report."""
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("source_key") or item.get("platform") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def _usage_totals(usage_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate provider time and tokens over every request with known usage."""
    latency = sum(float((row.get("usage") or {}).get("latency_seconds") or 0.0)
                  if "usage" in row else float(row.get("latency_seconds") or 0.0)
                  for row in usage_records)
    output = sum(int((row.get("usage") or {}).get("output_tokens") or 0)
                     if "usage" in row else int(row.get("output_tokens") or 0)
                 for row in usage_records)
    supplied = sum(int((row.get("usage") or {}).get("input_tokens") or 0)
                       if "usage" in row else int(row.get("input_tokens") or 0)
                   for row in usage_records)
    return {
        "model_latency_seconds": round(latency, 3),
        "input_tokens": supplied,
        "output_tokens": output,
        # Stated with the output size, because throughput is not comparable
        # across call shapes: short outputs let fixed per-call overhead dominate.
        "output_tokens_per_second": round(output / latency, 2) if latency > 0 else None,
        "mean_output_tokens": round(output / len(usage_records), 1) if usage_records else 0,
    }


def _rejection(item: dict[str, Any], error: Exception, attempt: int) -> dict[str, Any]:
    return {"item_id": str(item.get("evidence_id")),
            "error_type": type(error).__name__, "error": str(error), "attempts": attempt + 1}
