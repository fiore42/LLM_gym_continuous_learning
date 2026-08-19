#!/usr/bin/env python3
"""Inspect the shared chronological project run log."""

import argparse
import json
from collections import deque
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llm_gym.shared.settings import load_parameters


def _last_run_id(path: Path) -> str | None:
    last = None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                last = json.loads(line).get("run_id") or last
            except json.JSONDecodeError:
                continue
    return last


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default="data/run-log.jsonl", help="Run log path")
    parser.add_argument("--run-id", help="Show only events for one run")
    parser.add_argument("--all-runs", action="store_true", help="Search all runs instead of the latest run")
    parser.add_argument("--limit", type=int, default=100, help="Maximum events to show")
    parser.add_argument("--noout", action="store_true", help="Suppress output")
    args = parser.parse_args()
    try:
        load_parameters()
    except (OSError, ValueError) as exc:
        print(f"Global parameter validation failed: {exc}", file=sys.stderr)
        return 1
    if args.limit < 1:
        parser.error("--limit must be positive")

    path = Path(args.log)
    if not path.exists():
        print(f"Run log not found: {path}")
        return 1

    target_run = args.run_id or (None if args.all_runs else _last_run_id(path))
    records = deque(maxlen=args.limit)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if target_run and record.get("run_id") != target_run:
                continue
            records.append(record)
    if not args.noout:
        print(json.dumps(list(records), indent=2, ensure_ascii=False))
        scope = target_run or "all runs"
        print(f"Showing {len(records)} event(s) from {scope} in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
