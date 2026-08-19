#!/usr/bin/env python3
"""Read a digest report without writing throwaway Python for it.

Reads only; makes no model call and costs nothing. Default view is the run
header plus the significant items. Every assessment carries exact evidence
quotes that deterministic code located in the item text, so `--quotes` is the view that
lets a reader check a judgement rather than take it.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.agent.significance import SIGNIFICANCE_LABELS


def format_header(report: dict) -> list[str]:
    window = report["window"]
    usage = report.get("usage_totals") or {}
    provider_calls = report.get("provider_calls", report.get("model_calls", 0))
    calls_exact = bool(report.get("provider_calls_exact", "provider_calls" in report))
    usage_complete = bool(report.get("provider_usage_complete", calls_exact))
    calls_label = (str(provider_calls) if calls_exact
                   else f">={provider_calls} (legacy lower bound)")
    invocation_seconds = report.get("invocation_elapsed_seconds",
                                    report.get("elapsed_seconds", 0))
    run_wall_seconds = report.get("run_wall_elapsed_seconds")
    lines = [
        f"{window['since'][:10]} -> {window['until'][:10]}"
        f"  ({window.get('days')} days, {', '.join(window.get('platforms') or ['all'])})",
        f"run       {report['loop']['run_id']}  [{report['loop']['loop_type']}]",
        f"model     {report['model']}   prompt {report['prompt_version']}"
        f" ({str(report.get('prompt_sha256'))[:12]})",
        f"corpus    index {window.get('index_signature')}"
        f"   {window.get('considered')} considered -> {report['items_total']} selected",
        f"outcome   {report['outcome']}  ({report['stop_reason']})"
        f"  complete={report['complete']}",
        f"assessed  {report['items_assessed']} of {report['items_total']}"
        f"   rejected {report['items_rejected']}",
        f"spend     ${report['cost_usd']:.4f}   {calls_label} provider calls",
        f"time      {invocation_seconds:.0f}s this invocation"
        + (f"   {run_wall_seconds:.0f}s run wall including pauses"
           if run_wall_seconds is not None else "")
        + "\n"
        f"provider  {usage.get('model_latency_seconds', 0):.0f}s in the provider",
        ("usage>=   " if not usage_complete else "tokens    ")
        + f"{usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out"
        f"   {usage.get('output_tokens_per_second')} out-tok/s"
        f" at {usage.get('mean_output_tokens')} mean out-tok",
    ]
    counts = report["label_counts"]
    lines.append("labels    " + "  ".join(f"{label} {counts.get(label, 0)}"
                                          for label in SIGNIFICANCE_LABELS))
    sources = window.get("sources") or {}
    if len(sources) > 1:
        top = list(sources.items())[:4]
        lines.append("sources   " + "  ".join(f"{name[:24]}={count}" for name, count in top)
                     + (f"  (+{len(sources) - 4} more)" if len(sources) > 4 else ""))
    if report.get("evaluation_note"):
        lines += ["", textwrap.fill(report["evaluation_note"], 78,
                                    initial_indent="note      ", subsequent_indent="          ")]
    return lines


def format_assessment(row: dict, *, quotes: bool, width: int = 76) -> list[str]:
    lines = [f"[{row['significance']}]  {str(row.get('published_at'))[:10]}  "
             f"{str(row.get('title'))[:56]}"]
    for label, key in (("change ", "claimed_change"), ("problem", "problem_addressed"),
                       ("reason ", "reason")):
        if row.get(key):
            lines.append(textwrap.fill(row[key], width, initial_indent=f"  {label}: ",
                                       subsequent_indent="           "))
    if quotes:
        evidence = row.get("supporting_evidence")
        if not isinstance(evidence, list):
            evidence = [{"claim_component": "", "quote": row.get("supporting_quote", "")}]
        for index, item in enumerate(evidence, start=1):
            if item.get("claim_component"):
                lines.append(textwrap.fill(
                    item["claim_component"], width,
                    initial_indent=f"  evidence {index}: ", subsequent_indent="              "))
            lines.append(textwrap.fill(
                f'"{item.get("quote", "")}"', width,
                initial_indent=f"  quote {index}   : ", subsequent_indent="              "))
    lines.append(f"  {row.get('canonical_url')}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="Digest report JSON")
    parser.add_argument("--label", action="append", default=[],
                        help=f"Show only these labels; repeatable. Default SIGNIFICANT. "
                             f"Choices: {', '.join(SIGNIFICANCE_LABELS)}, ALL")
    parser.add_argument("--quotes", action="store_true",
                        help="Show the mapped verbatim evidence quotes for each judgement")
    parser.add_argument("--rejected", action="store_true", help="Show rejected items instead")
    parser.add_argument("--noout", action="store_true", help="Suppress output; preserve exit code")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    wanted = {label.upper() for label in (args.label or ["SIGNIFICANT"])}
    if args.noout:
        return 0 if report.get("complete") else 1

    print("\n".join(format_header(report)))
    if args.rejected:
        print(f"\n{'=' * 78}\nREJECTED ({len(report['rejected'])})")
        for row in report["rejected"]:
            print(f"  {row['item_id'][:16]}  {row['error_type']}: {row['error'][:60]}"
                  f"  (attempts {row['attempts']})")
        return 0 if report.get("complete") else 1

    shown = [row for row in report["ranked"]
             if "ALL" in wanted or row["significance"] in wanted]
    print(f"\n{'=' * 78}\n{len(shown)} of {len(report['ranked'])} assessments"
          f" ({', '.join(sorted(wanted))})")
    for row in shown:
        print()
        print("\n".join(format_assessment(row, quotes=args.quotes)))
    return 0 if report.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
