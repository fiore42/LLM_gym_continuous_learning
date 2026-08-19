#!/usr/bin/env python3
"""Repeat live retrieval-retry runs to measure which signal fires the loop.

The expansion trigger reads two signals: the classification label, and the
model's own count of relevant evidence. Live runs so far have always had the
label say INSUFFICIENT_EVIDENCE in round one, so the relevance signal has
never been the deciding factor. This script repeats a small set of cases to
measure how often each signal is the one that fires.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.agent.model_client import model_client_from_environment
from llm_gym.shared.atomic import atomic_write_text
from llm_gym.shared.config import load_dotenv
from scripts.agent_run_retrieval_retry import live_retriever, load_case, run_case

DEFAULT_CASES = ("what_are_evals", "independent_evaluation")


class CostTrackingClient:
    """Wrap a provider client and accumulate usage across every call."""

    def __init__(self, inner):
        self.inner = inner
        self.total_cost_usd = 0.0
        self.calls = 0
        self.last_usage: dict = {}

    def complete(self, **kwargs):
        try:
            return self.inner.complete(**kwargs)
        finally:
            self.calls += 1
            self.last_usage = getattr(self.inner, "last_usage", {}) or {}
            self.total_cost_usd += float(self.last_usage.get("cost_usd", 0.0) or 0.0)


def classify_trigger(trace: dict) -> str:
    """Name the signal that decided round one, for attribution."""
    rounds = trace.get("rounds") or []
    if not rounds:
        return "no_round_one"
    first = rounds[0]
    label_would_fire = first.get("classification") == "INSUFFICIENT_EVIDENCE"
    if not trace.get("evidence_expanded"):
        return "stopped_label_sufficient" if not label_would_fire else "stopped_no_queries"
    return "label" if label_would_fire else "relevance_only"


def _throughput(results: list[dict]) -> float | None:
    """Aggregate output tokens per second across every measured call."""
    latency = sum(r["model_latency_seconds"] for r in results)
    tokens = sum(r["output_tokens"] for r in results)
    return round(tokens / latency, 2) if latency > 0 else None


def summarise(results: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in results:
        counts[row["trigger"]] = counts.get(row["trigger"], 0) + 1
    expanded = [r for r in results if r["evidence_expanded"]]
    return {
        "runs": len(results),
        "trigger_counts": counts,
        "relevance_only_fired": counts.get("relevance_only", 0),
        "expanded": len(expanded),
        "round_one_labels": {
            label: sum(1 for r in results if r["round_one_classification"] == label)
            for label in {r["round_one_classification"] for r in results}
        },
        "errors": sum(1 for r in results if r["stop_reason"] == "PROVIDER_OR_VALIDATION_ERROR"),
        # Completed rounds versus requests actually sent. They diverge on any
        # failed round, and only the second reflects what was billed.
        "total_completed_rounds": sum(r["model_calls"] for r in results),
        "total_provider_calls": sum(r["provider_calls"] for r in results),
        # Provider time and throughput. Raw latency scales with how much the
        # model chose to write, so tokens per second is the figure that stays
        # comparable when the same suite runs against a different provider.
        "total_model_latency_seconds": round(
            sum(r["model_latency_seconds"] for r in results), 3),
        "output_tokens_per_second": _throughput(results),
        "total_cost_usd": round(sum(r["cost_usd"] for r in results), 6),
    }


REFUSAL_MARKERS = ("usage limit", "quota", "credit balance", "billing")


def measurement_output_dir(provider_prefix: str) -> str:
    """One directory per provider arm.

    Traces are named by case and repetition, so two arms sharing a directory
    silently overwrite each other — and the surviving summary then describes
    a mixture of both, which is indistinguishable from a clean run.
    """
    return f"data/runs/trigger-measurement/{provider_prefix.lower()}"


def provider_refused(trace: dict) -> bool:
    """Return whether the provider signalled that further calls are futile.

    A spend cap or exhausted quota fails every remaining repetition
    identically, so the measurement should stop rather than issue dozens of
    doomed requests. Anthropic reports this as an HTTP 400, which is already
    classified non-retryable, so the run stops for the right reason — but only
    that one run, unless the whole measurement notices.
    """
    error = str(trace.get("error") or "").lower()
    return bool(error) and any(marker in error for marker in REFUSAL_MARKERS)


def _row_line(row: dict) -> str:
    """One line per run. A run that failed in round one has no classification,
    so format a placeholder rather than crashing on None and taking every
    measurement still queued behind it down as well."""
    return (f"{row['case_id']} rep {row['repetition']}: {row['trigger']:26} "
            f"round1={str(row['round_one_classification'] or 'NONE'):22} "
            f"relevant={row['round_one_relevant']}/{row['round_one_assessed']} "
            f"calls={row['provider_calls']} "
            f"{row['model_latency_seconds']:.1f}s "
            f"${row['cost_usd']:.4f}")


def _write_report(output_dir: Path, model: str, results: list[dict],
                  provider_prefix: str = "AGENT") -> None:
    report = {
        "measurement_version": 1,
        "model": model,
        "provider_prefix": provider_prefix,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": summarise(results),
        "runs": results,
    }
    atomic_write_text(output_dir / "summary.json",
                      json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("\n" + json.dumps(report["summary"], indent=2))


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--cases", nargs="*", default=list(DEFAULT_CASES))
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--suite", default="config/agent_eval_suite.json")
    parser.add_argument("--index", default="data/evidence.sqlite3")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-cost-usd", type=float, default=2.0,
                        help="Stop before starting a run that could exceed this total")
    parser.add_argument("--output-dir", default="",
                        help="Defaults to a directory named for the provider, so "
                             "two arms cannot overwrite each other's traces")
    parser.add_argument("--provider-prefix", default="AGENT",
                        help="Environment prefix selecting the provider "
                             "(AGENT, FRONTIER, OPEN_WEIGHT)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir or measurement_output_dir(args.provider_prefix))
    retrieve = live_retriever(args.index, args.limit)
    results: list[dict] = []
    spent = 0.0

    try:
        for case_id in args.cases:
            case = load_case(args.suite, case_id)
            for repetition in range(1, args.repetitions + 1):
                if spent >= args.max_cost_usd:
                    print(f"stopping: spend ${spent:.4f} reached cap ${args.max_cost_usd}",
                          file=sys.stderr)
                    break
                client = CostTrackingClient(
                    model_client_from_environment(prefix=args.provider_prefix))
                trace = run_case(
                    question=case["question"], model=args.model, client=client,
                    retrieve=retrieve, case_id=case_id,
                    provider_prefix=args.provider_prefix,
                    frozen_expected_outcome=case.get("expected_outcome"),
                    index_path=args.index,
                )
                trace["repetition"] = repetition
                trace["cost_usd"] = round(client.total_cost_usd, 6)
                spent += client.total_cost_usd
                # Write each trace as it completes so an interruption keeps the
                # runs already paid for.
                atomic_write_text(output_dir / f"{case_id}-rep-{repetition}.json",
                                  json.dumps(trace, indent=2, ensure_ascii=False) + "\n")
                first_round = (trace["rounds"] or [{}])[0]
                results.append({
                    "case_id": case_id,
                    "repetition": repetition,
                    "trigger": classify_trigger(trace),
                    "round_one_classification": first_round.get("classification"),
                    "round_one_relevant": first_round.get("relevant_evidence_count"),
                    "round_one_assessed": first_round.get("assessed_evidence_count"),
                    "evidence_expanded": trace["evidence_expanded"],
                    "stop_reason": trace["stop_reason"],
                    "error": trace["error"],
                    "model_calls": trace["model_calls"],
                    "provider_calls": trace["provider_calls"],
                    "model_latency_seconds": trace["model_latency_seconds"],
                    "output_tokens": trace["output_tokens"],
                    "cost_usd": trace["cost_usd"],
                })
                print(_row_line(results[-1]), flush=True)
                if provider_refused(trace):
                    # Every remaining repetition would fail the same way. Stop
                    # rather than issuing dozens of doomed requests.
                    print(f"stopping: provider refused further work: {trace['error']}",
                          file=sys.stderr)
                    return 0
    finally:
        # These runs were paid for; a crash or interrupt must not discard the
        # aggregate along with them.
        if results:
            _write_report(output_dir, args.model, results, args.provider_prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
