"""Small, deterministic retrieve-observe-adapt loop for offline testing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .model_client import ModelProviderError
from .synthesis import (MAX_OUTPUT_TOKENS, PROMPT_VERSION, SynthesisRequest,
                        SynthesisResult, synthesize)


@dataclass(frozen=True)
class RetrievalRetryResult:
    """The bounded loop's inspectable result."""

    attempts: tuple[SynthesisResult, ...]
    evidence: tuple[dict[str, Any], ...]
    queries: tuple[str, ...]
    stop_reason: str
    error: str | None = None
    # Every request sent to the provider, including ones rejected by
    # validation. ``attempts`` holds only responses that survived validation,
    # so counting it understates work and spend: a run whose second round was
    # truncated bills for a call that never reaches ``attempts``.
    provider_calls: int = 0
    # Provider-reported tokens, cost and latency for each entry in
    # ``attempts``, positionally aligned with it.
    usage: tuple[dict[str, Any], ...] = ()
    # The same, for calls that were billed but rejected by validation. Without
    # this the trace's latency and tokens count only successful calls while
    # its cost counts every call, so the two disagree about what happened.
    failed_usage: tuple[dict[str, Any], ...] = ()


def relevant_evidence_count(result: SynthesisResult) -> int:
    """Count evidence items the model itself judged usable for the question.

    This is the stable signal: across repeated live runs on identical input
    the classification label flipped between SUPPORTED and
    INSUFFICIENT_EVIDENCE, while the per-item relevance assessment did not.
    """
    return sum(
        1 for item in result.evidence_assessment
        if isinstance(item, dict) and item.get("relevant") is True
    )


def _merge_evidence(existing: tuple[dict[str, Any], ...], additions: list[dict[str, Any]],
                    max_items: int | None = None) -> tuple[dict[str, Any], ...]:
    """Merge ranked additions into the evidence set, bounded by ``max_items``.

    The synthesis contract requires one assessment entry per supplied item, so
    output length grows linearly with the evidence set while the output cap is
    fixed. Unbounded expansion therefore walks the loop past its own output
    ceiling: measured live, sets of 26 or more items truncated in five of
    seven runs while sets of 25 or fewer always completed.

    Additions arrive in rank order, so truncating keeps the best of them.
    Evidence already shown to the model is never dropped, even if the set is
    already at or above the cap.
    """
    merged = list(existing)
    known = {str(item.get("evidence_id")) for item in merged}
    for item in additions:
        if max_items is not None and len(merged) >= max_items:
            break
        evidence_id = str(item.get("evidence_id"))
        if evidence_id and evidence_id not in known:
            merged.append(item)
            known.add(evidence_id)
    return tuple(merged)


def run_retrieval_retry(
    *,
    question: str,
    evidence: tuple[dict[str, Any], ...],
    model: str,
    client,
    retrieve: Callable[[str], list[dict[str, Any]]],
    prompt_version: str | None = None,
    max_rounds: int = 2,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
    min_relevant_evidence: int = 3,
    max_validation_retries: int = 1,
    max_evidence_items: int = 20,
) -> RetrievalRetryResult:
    """Run at most one evidence-expansion round after an insufficient draft.

    The model may suggest queries, but only the injected deterministic
    ``retrieve`` function can add evidence. This function is intentionally
    offline-friendly and does not own provider budgets or checkpoints yet.
    """
    if max_rounds < 1:
        raise ValueError("max_rounds must be positive")
    current = tuple(evidence)
    attempts: list[SynthesisResult] = []
    usages: list[dict[str, Any]] = []
    failed_usages: list[dict[str, Any]] = []
    provider_calls = 0
    queries: list[str] = []
    revision_feedback = ""
    for round_number in range(max_rounds):
        # Validation failures here are stochastic, not deterministic: emitting
        # exactly one assessment per supplied item gets less reliable as the
        # evidence set grows, so the same request often succeeds on a second
        # try. run_agent_task already retries this class of failure with the
        # error fed back as feedback; this loop does the same rather than
        # discarding rounds that were already paid for.
        result = None
        last_error: Exception | None = None
        attempt_feedback = revision_feedback
        for validation_attempt in range(1 + max_validation_retries):
            request = SynthesisRequest(
                question, current, model, prompt_version=prompt_version or PROMPT_VERSION,
                revision_feedback=attempt_feedback, max_output_tokens=max_output_tokens,
            )
            provider_calls += 1
            # Clear first: a failure raised before usage is recorded would
            # otherwise be attributed the previous call's tokens and cost.
            if hasattr(client, "last_usage"):
                client.last_usage = {}
            try:
                result = synthesize(request, client)
                break
            except (ModelProviderError, ValueError) as exc:
                last_error = exc
                # A validation failure still completed an HTTP call, so its
                # usage exists and was billed. Truncation raises before usage
                # is recorded, leaving nothing to collect.
                billed = dict(getattr(client, "last_usage", {}) or {})
                if billed:
                    failed_usages.append(billed)
                if isinstance(exc, ModelProviderError) and not exc.retryable:
                    break
                attempt_feedback = (
                    f"{revision_feedback}\n\nThe previous response was rejected: {exc}. "
                    "Return a corrected JSON response that satisfies every requirement."
                ).strip()
        if result is None:
            return RetrievalRetryResult(
                tuple(attempts), current, tuple(queries),
                "PROVIDER_OR_VALIDATION_ERROR",
                f"{type(last_error).__name__}: {last_error}",
                provider_calls, tuple(usages), tuple(failed_usages),
            )
        attempts.append(result)
        usages.append(dict(getattr(client, "last_usage", {}) or {}))
        # Expand on either signal. Live runs showed the classification label is
        # unstable on borderline evidence: identical inputs produced SUPPORTED
        # on one run and INSUFFICIENT_EVIDENCE on another, while the model's
        # per-item relevance assessment stayed consistent. Keying only on the
        # label made expansion fire at random on exactly the thin-evidence
        # cases this loop exists to repair.
        # Scale the bar to what was actually retrieved: two relevant items out
        # of two is not thin evidence, but two out of eight is.
        relevant = relevant_evidence_count(result)
        thin = relevant < min(min_relevant_evidence, len(current))
        if result.classification != "INSUFFICIENT_EVIDENCE" and not thin:
            return RetrievalRetryResult(tuple(attempts), current, tuple(queries),
                                        "QUALITY_GATE_PASSED", None, provider_calls, tuple(usages), tuple(failed_usages))
        if round_number == max_rounds - 1 or not result.suggested_queries:
            return RetrievalRetryResult(tuple(attempts), current, tuple(queries),
                                        "RETRIEVAL_RETRY_NOT_REQUESTED", None, provider_calls, tuple(usages), tuple(failed_usages))
        new_queries = [query for query in result.suggested_queries if query not in queries]
        queries.extend(new_queries)
        additions: list[dict[str, Any]] = []
        for query in new_queries:
            additions.extend(retrieve(query))
        expanded = _merge_evidence(current, additions, max_evidence_items)
        if len(expanded) == len(current):
            return RetrievalRetryResult(tuple(attempts), current, tuple(queries),
                                        "RETRIEVAL_NO_NEW_EVIDENCE", None, provider_calls, tuple(usages), tuple(failed_usages))
        current = expanded
        revision_feedback = "New evidence was retrieved for the refined query; reassess the expanded evidence set."
    return RetrievalRetryResult(tuple(attempts), current, tuple(queries),
                                "RETRIEVAL_ROUND_LIMIT", None, provider_calls, tuple(usages), tuple(failed_usages))
