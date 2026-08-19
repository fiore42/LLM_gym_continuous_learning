#!/usr/bin/env python3
"""Live-fire the retrieval-retry loop: draft, expand evidence, redraft."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.agent.model_client import model_client_from_environment
from llm_gym.agent.retrieval_retry import relevant_evidence_count, run_retrieval_retry
from llm_gym.corpus.evidence import index_signature, search_index_with_metadata
from llm_gym.shared.atomic import atomic_write_text
from llm_gym.shared.config import load_dotenv
from llm_gym.shared.status import completion_exit_code

SUITE_DEFAULT = "config/agent_eval_suite.json"
INDEX_DEFAULT = "data/evidence.sqlite3"


def live_retriever(index_path: str | Path, limit: int) -> Callable[[str], list[dict[str, Any]]]:
    """Return a deterministic retrieval callable bound to one index and depth."""
    def retrieve(query: str) -> list[dict[str, Any]]:
        return list(search_index_with_metadata(query, index_path, limit)["matches"])
    return retrieve


def default_output_path(case_id: str, provider_prefix: str) -> str:
    """Name traces so two provider arms cannot overwrite each other.

    Running the same case against a second provider used to write the same
    file, silently replacing the arm it was meant to be compared with.
    """
    return f"data/runs/retrieval-retry-{case_id or 'adhoc'}-{provider_prefix.lower()}.json"


def _latency_summary(round_usage: list[dict[str, Any]],
                     failed_usage: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll per-call timings into the figures worth comparing across providers.

    Every billed call counts, including ones rejected by validation. Counting
    only successful rounds made a failed run look *faster* than a clean one —
    it recorded round one's 20 seconds and dropped the 45-second round two
    that had already been paid for — while its cost, tracked separately,
    included that call. Cost and latency must agree about what happened.

    Throughput is recomputed from the totals rather than averaged across
    rounds: averaging per-round rates would weight a short round as heavily as
    a long one.
    """
    billed = list(round_usage) + list(failed_usage)
    latency = sum(float(usage.get("latency_seconds") or 0.0) for usage in billed)
    output_tokens = sum(int(usage.get("output_tokens") or 0) for usage in billed)
    return {
        "model_latency_seconds": round(latency, 3),
        "output_tokens": output_tokens,
        "output_tokens_per_second": round(output_tokens / latency, 2) if latency > 0 else None,
        # Split out so a run's wasted spend stays visible rather than merged.
        "rejected_call_latency_seconds": round(
            sum(float(usage.get("latency_seconds") or 0.0) for usage in failed_usage), 3),
        "rejected_calls_with_usage": len(failed_usage),
    }


def run_case(
    *,
    question: str,
    model: str,
    client,
    retrieve: Callable[[str], list[dict[str, Any]]],
    case_id: str = "",
    provider_prefix: str = "AGENT",
    frozen_expected_outcome: str | None = None,
    max_rounds: int = 2,
    max_evidence_items: int = 20,
    index_path: str | Path = INDEX_DEFAULT,
) -> dict[str, Any]:
    """Run one question through the retrieval-retry loop and build a trace.

    The initial evidence comes from live retrieval, not a frozen case, because
    the point is to see whether a second retrieval round can repair a thin
    first result.
    """
    started = datetime.now(timezone.utc)
    initial = retrieve(question)
    result = run_retrieval_retry(
        question=question, evidence=tuple(initial), model=model, client=client,
        retrieve=retrieve, max_rounds=max_rounds,
        max_evidence_items=max_evidence_items,
    )
    # A client that reports no usage must not cost the trace its rounds, so
    # pad rather than letting zip truncate.
    round_usage = list(result.usage) + [{}] * (len(result.attempts) - len(result.usage))
    rounds = [
        {
            "round": number + 1,
            "classification": attempt.classification,
            # The trigger keys on this, not on the classification label, so it
            # must be visible when reading the trace.
            "relevant_evidence_count": relevant_evidence_count(attempt),
            "assessed_evidence_count": len(attempt.evidence_assessment),
            "citation_ids": list(attempt.citation_ids),
            "suggested_queries": list(attempt.suggested_queries),
            "answer": attempt.answer,
            # Tokens, cost and time-to-last-token for this round. Latency alone
            # is confounded by answer length, so provider comparison should use
            # output_tokens_per_second.
            "usage": dict(usage),
        }
        for number, (attempt, usage) in enumerate(zip(result.attempts, round_usage))
    ]
    return {
        "case_id": case_id,
        "question": question,
        "mode": "live_retrieval",
        "model": model,
        # Which provider environment served this run. The trace has to record
        # what it actually ran against, not what the default happened to be.
        "provider_prefix": provider_prefix,
        "index_signature": index_signature(index_path),
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "stop_reason": result.stop_reason,
        "error": result.error,
        "rounds": rounds,
        # Rounds that produced a validated result.
        "model_calls": len(result.attempts),
        # Requests actually sent, including ones rejected by validation. These
        # differ whenever a round failed: the rejected call still cost money.
        "provider_calls": result.provider_calls,
        # Time spent inside the provider, as distinct from wall-clock elapsed,
        # which also covers local retrieval. Counts every billed call.
        **_latency_summary(round_usage, list(result.failed_usage)),
        "evidence_count_initial": len(initial),
        "evidence_count_final": len(result.evidence),
        "evidence_expanded": len(result.evidence) > len(initial),
        # Bounds belong in the trace: expansion past ~25 items truncated the
        # response in five of seven measured runs.
        "max_evidence_items": max_evidence_items,
        "refined_queries": list(result.queries),
        "final_evidence_ids": [str(item.get("evidence_id")) for item in result.evidence],
        # Recorded for triage only. Per EVALS.md, a live-retrieval run must not
        # be scored against a frozen case's expected_outcome: the inputs differ,
        # so a different classification is a retrieval finding, not a failure.
        "frozen_expected_outcome": frozen_expected_outcome,
        "comparison_note": (
            "Live retrieval supplies different evidence than the frozen case. "
            "Diff the evidence sets before attributing any difference to the model."
        ),
    }


def load_case(suite_path: str | Path, case_id: str) -> dict[str, Any]:
    payload = json.loads(Path(suite_path).read_text(encoding="utf-8"))
    for case in payload.get("answer_cases") or []:
        if case.get("case_id") == case_id:
            return case
    known = ", ".join(str(c.get("case_id")) for c in payload.get("answer_cases") or [])
    raise ValueError(f"unknown answer case: {case_id}\nknown cases: {known}")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="answer case whose question to run live")
    parser.add_argument("--question", help="ad-hoc question instead of a suite case")
    parser.add_argument("--suite", default=SUITE_DEFAULT)
    parser.add_argument("--index", default=INDEX_DEFAULT)
    parser.add_argument("--model", required=True)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-rounds", type=int, default=2)
    parser.add_argument("--output", default="")
    parser.add_argument("--provider-prefix", default="AGENT",
                        help="Environment prefix selecting the provider "
                             "(AGENT, FRONTIER, OPEN_WEIGHT)")
    args = parser.parse_args()
    if bool(args.case) == bool(args.question):
        parser.error("supply exactly one of --case or --question")

    if args.case:
        case = load_case(args.suite, args.case)
        question, case_id = case["question"], args.case
        expected = case.get("expected_outcome")
    else:
        question, case_id, expected = args.question, "", None

    trace = run_case(
        question=question, model=args.model,
        client=model_client_from_environment(prefix=args.provider_prefix),
        retrieve=live_retriever(args.index, args.limit),
        case_id=case_id, provider_prefix=args.provider_prefix,
        frozen_expected_outcome=expected,
        max_rounds=args.max_rounds, index_path=args.index,
    )
    output = args.output or default_output_path(case_id, args.provider_prefix)
    atomic_write_text(output, json.dumps(trace, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(trace, indent=2, ensure_ascii=False))
    return completion_exit_code(not bool(trace.get("error")))


if __name__ == "__main__":
    raise SystemExit(main())
