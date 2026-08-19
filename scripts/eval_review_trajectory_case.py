#!/usr/bin/env python3
"""Show one trajectory case beside the test that proves it, and run that test."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SUITE_DEFAULT = "config/agent_eval_suite.json"
TEST_CLASS = "AgentRunnerTests"


def _test_source(path: Path, name: str) -> str:
    """Return the body of one test function, without importing the module."""
    lines = path.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(rf"def {re.escape(name)}\b")
    start = next((i for i, line in enumerate(lines) if pattern.search(line)), None)
    if start is None:
        raise ValueError(f"test not found in {path}: {name}")
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = [lines[start]]
    for line in lines[start + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line)
    return "\n".join(body)


def review(case_id: str, *, suite_path: str, run_test: bool) -> int:
    payload = json.loads(Path(suite_path).read_text(encoding="utf-8"))
    cases = payload.get("trajectory_cases") or []
    case = next((item for item in cases if item.get("case_id") == case_id), None)
    if case is None:
        print(f"unknown trajectory case: {case_id}\n")
        list_cases(suite_path)
        return 1

    print("=" * 70)
    print(f"CASE: {case_id}   [{case.get('review_status', 'unreviewed')}]")
    print("=" * 70)
    print(f"fixture : {case.get('fixture')}")
    for key, value in (case.get("expected") or {}).items():
        print(f"expects : {key} = {value}")
    if case.get("review_rationale"):
        print(f"\nrationale: {case['review_rationale']}")

    reference = str(case.get("verified_by") or "")
    test_path, _, test_name = reference.partition("::")
    if not test_name:
        print("\nNo verified_by reference on this case.")
        return 1

    print("\n" + "=" * 70)
    print(f"PROOF: {reference}")
    print("=" * 70)
    print(_test_source(Path(test_path), test_name))

    if not run_test:
        return 0
    node = f"{test_path}::{TEST_CLASS}::{test_name}"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", node], capture_output=True, text=True
    )
    print("=" * 70)
    print("RESULT:", "PASSED" if result.returncode == 0 else "FAILED")
    if result.returncode != 0:
        print(result.stdout[-2000:])
    return result.returncode


LIST_CASES = "__list__"


def list_cases(suite_path: str) -> int:
    """Print every trajectory case with its review status and proving test."""
    payload = json.loads(Path(suite_path).read_text(encoding="utf-8"))
    print("valid --case values (trajectory cases):\n")
    for item in payload.get("trajectory_cases") or []:
        status = item.get("review_status", "unreviewed")
        proof = str(item.get("verified_by") or "").partition("::")[2] or "(none)"
        print(f"  {item.get('case_id'):26} {status:11} {proof}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", nargs="?", const=LIST_CASES, default=None,
                        help="trajectory case to review; omit the value to list valid cases")
    parser.add_argument("--suite", default=SUITE_DEFAULT)
    parser.add_argument("--no-run", action="store_true", help="do not execute the test")
    args = parser.parse_args()

    if args.case is None or args.case == LIST_CASES:
        return list_cases(args.suite)
    return review(args.case, suite_path=args.suite, run_test=not args.no_run)


if __name__ == "__main__":
    raise SystemExit(main())
