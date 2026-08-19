#!/usr/bin/env python3
"""Validate the reviewable agent evaluation suite without calling a model."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.corpus.evidence import index_signature, search_index_with_metadata


REQUIRED_ANSWER_EVALUATIONS = {
    "evidence_relevant", "claims_supported", "citations_valid", "answer_complete",
}
ALLOWED_BENCHMARK_SPLITS = {"development", "holdout"}
LIST_CASES = "__list__"
# Phrasings that describe what an answer may not say, rather than what the
# supplied evidence establishes. These belong in forbidden_overclaims.
_CONSTRAINT_SHAPED = re.compile(
    r"\bmust not\b|\bmust avoid\b|\bshould not\b|^the answer must\b", re.IGNORECASE
)


def list_answer_cases(payload: dict[str, Any]) -> int:
    """Print every answer case with its split and review status."""
    print("valid --case values (answer cases):\n")
    for case in payload.get("answer_cases") or []:
        print(f"  {str(case.get('case_id')):34} {str(case.get('split')):12}"
              f" {case.get('review_status', 'unreviewed'):11}"
              f" {case.get('expected_outcome')}")
    return 0


def get_answer_case(payload: dict[str, Any], case_id: str) -> dict[str, Any]:
    """Return one answer case for focused human review."""
    for case in payload.get("answer_cases", []):
        if isinstance(case, dict) and case.get("case_id") == case_id:
            return case
    raise ValueError(f"unknown answer case_id: {case_id}")


def validate_retrieval_cases(payload: dict[str, Any], index_path: str | Path) -> dict[str, Any]:
    """Check optional end-to-end retrieval expectations against the live index."""
    checked = 0
    missing_total = 0
    for case in payload.get("answer_cases", []):
        if not isinstance(case, dict) or not case.get("retrieval_query"):
            continue
        expected = {str(item) for item in case.get("retrieval_expected_evidence_ids") or ()}
        if not expected:
            raise ValueError(f"{case.get('case_id')}: retrieval expectations are required")
        result = search_index_with_metadata(
            str(case["retrieval_query"]), index_path, int(case.get("retrieval_limit", 10)))
        found = {str(item.get("evidence_id")) for item in result["matches"]}
        missing = expected - found
        if missing:
            missing_total += len(missing)
            raise ValueError(f"{case.get('case_id')}: retrieval did not return expected evidence: {sorted(missing)}")
        checked += 1
    return {"retrieval_cases_checked": checked, "retrieval_missing": missing_total,
            "index_signature": index_signature(index_path)}


def validate_suite(payload: dict[str, Any], *, index_path: str | Path | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("suite must be a JSON object")
    contract = payload.get("evaluation_contract") or {}
    definitions = {
        item.get("name")
        for key in ("required_answer_evaluations", "optional_answer_evaluations",
                    "trajectory_evaluations", "operational_evaluations")
        for item in contract.get(key, [])
        if isinstance(item, dict)
    }
    missing_definitions = sorted(REQUIRED_ANSWER_EVALUATIONS - definitions)
    if missing_definitions:
        raise ValueError(f"missing required evaluation definitions: {missing_definitions}")

    cases = payload.get("answer_cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("suite must contain answer_cases")
    case_ids: set[str] = set()
    evidence_ids: list[str] = []
    split_counts = {split: 0 for split in ALLOWED_BENCHMARK_SPLITS}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("every answer case must be an object")
        case_id = str(case.get("case_id") or "").strip()
        if not case_id or case_id in case_ids:
            raise ValueError(f"duplicate or empty answer case_id: {case_id!r}")
        case_ids.add(case_id)
        split = case.get("split")
        if split not in ALLOWED_BENCHMARK_SPLITS:
            raise ValueError(f"{case_id}: split must be development or holdout")
        split_counts[split] += 1
        if case.get("review_status") not in {"pending", "reviewed"}:
            raise ValueError(f"{case_id}: review_status must be pending or reviewed")
        failure_modes = case.get("target_failure_modes")
        if not isinstance(failure_modes, list) or not failure_modes or any(
            not isinstance(mode, str) or not mode.strip() for mode in failure_modes
        ):
            raise ValueError(f"{case_id}: target_failure_modes must be a non-empty list")
        if case.get("expected_outcome") not in {"SUPPORTED", "INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE"}:
            raise ValueError(f"{case_id}: invalid expected_outcome")
        evidence = case.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"{case_id}: evidence is required")
        available: set[str] = set()
        for item in evidence:
            if not isinstance(item, dict):
                raise ValueError(f"{case_id}: evidence item must be an object")
            evidence_id = str(item.get("evidence_id") or "").strip()
            if not evidence_id or evidence_id in available:
                raise ValueError(f"{case_id}: duplicate or empty evidence_id")
            if not item.get("canonical_url") or not item.get("snippet"):
                raise ValueError(f"{case_id}: evidence requires canonical_url and snippet")
            available.add(evidence_id)
            evidence_ids.append(evidence_id)
        for field in ("required_citation_ids", "forbidden_citation_ids"):
            unknown = sorted(set(case.get(field) or ()) - available)
            if unknown:
                raise ValueError(f"{case_id}: {field} references unknown evidence: {unknown}")
        unknown_evals = sorted(set(case.get("required_evaluations") or ()) - definitions)
        if unknown_evals:
            raise ValueError(f"{case_id}: unknown evaluations: {unknown_evals}")
        forbidden_overclaims = case.get("forbidden_overclaims")
        if forbidden_overclaims is not None and (
            not isinstance(forbidden_overclaims, list)
            or any(not isinstance(item, str) or not item.strip() for item in forbidden_overclaims)
        ):
            raise ValueError(f"{case_id}: forbidden_overclaims must be a list of non-empty strings")
        # required_claims must state what the evidence establishes, so each one
        # can be mapped to a snippet during review. Constraints on the answer's
        # wording belong in forbidden_overclaims, where they are checked as
        # things the answer must not say rather than things it must contain.
        misplaced = [claim for claim in case.get("required_claims") or []
                     if _CONSTRAINT_SHAPED.search(str(claim))]
        if misplaced:
            raise ValueError(
                f"{case_id}: required_claims must assert what the evidence supports; "
                f"move answer constraints to forbidden_overclaims: {misplaced}"
            )
        if case.get("retrieval_query") and not isinstance(case.get("retrieval_query"), str):
            raise ValueError(f"{case_id}: retrieval_query must be a string")
        retrieval_expected = case.get("retrieval_expected_evidence_ids")
        if retrieval_expected is not None and (
            not isinstance(retrieval_expected, list)
            or any(str(item) not in available for item in retrieval_expected)
        ):
            raise ValueError(f"{case_id}: retrieval expectations must reference supplied evidence")

    trajectory = payload.get("trajectory_cases")
    if not isinstance(trajectory, list) or not trajectory:
        raise ValueError("suite must contain trajectory_cases")
    trajectory_ids = [str(item.get("case_id") or "") for item in trajectory if isinstance(item, dict)]
    if len(trajectory_ids) != len(set(trajectory_ids)) or any(not item for item in trajectory_ids):
        raise ValueError("trajectory case IDs must be unique and non-empty")
    # A reviewed trajectory case must name the test that proves it, and that
    # test must still exist. This keeps the link a contract rather than a
    # comment that can rot when tests are renamed.
    for item in trajectory:
        if not isinstance(item, dict) or item.get("review_status") != "reviewed":
            continue
        case_id = item.get("case_id")
        reference = str(item.get("verified_by") or "").strip()
        if not reference:
            raise ValueError(f"{case_id}: reviewed trajectory case requires verified_by")
        test_path, _, test_name = reference.partition("::")
        source = Path(test_path)
        if not test_name or not source.is_file():
            raise ValueError(f"{case_id}: verified_by does not resolve: {reference}")
        if not re.search(rf"def {re.escape(test_name)}\b", source.read_text(encoding="utf-8")):
            raise ValueError(f"{case_id}: verified_by test not found: {reference}")

    found = len(set(evidence_ids))
    missing: list[str] = []
    if index_path is not None and Path(index_path).is_file():
        connection = sqlite3.connect(index_path)
        placeholders = ",".join("?" for _ in set(evidence_ids))
        rows = connection.execute(
            f"SELECT evidence_id FROM evidence_items WHERE evidence_id IN ({placeholders})",
            tuple(set(evidence_ids)),
        ).fetchall()
        missing = sorted(set(evidence_ids) - {row[0] for row in rows})
        connection.close()
        if missing:
            raise ValueError(f"suite references evidence absent from index: {missing}")
    if split_counts["holdout"] == 0:
        raise ValueError("suite must contain at least one holdout case")
    if split_counts["development"] == 0:
        raise ValueError("suite must contain at least one development case")
    return {
        "answer_cases": len(cases),
        "trajectory_cases": len(trajectory),
        "unique_evidence_references": found,
        "index_checked": bool(index_path and Path(index_path).is_file()),
        "index_signature": index_signature(index_path) if index_path else None,
        "repetitions": (payload.get("repetition_policy") or {}).get("minimum_repetitions_per_case"),
        "split_counts": split_counts,
        "benchmark_status": payload.get("benchmark_status"),
        # Report the review breakdown so the suite-level status is never
        # ambiguous: answer cases and trajectory cases are reviewed separately.
        "review_counts": {
            "answer_cases_reviewed": sum(
                1 for case in cases if case.get("review_status") == "reviewed"
            ),
            "answer_cases_total": len(cases),
            "trajectory_cases_reviewed": sum(
                1 for item in trajectory
                if isinstance(item, dict) and item.get("review_status") == "reviewed"
            ),
            "trajectory_cases_total": len(trajectory),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="config/agent_eval_suite.json")
    parser.add_argument("--index", default="data/evidence.sqlite3")
    parser.add_argument("--case", nargs="?", const=LIST_CASES, default=None,
                        help="pretty-print one answer case after validating the full "
                             "suite; omit the value to list valid cases")
    parser.add_argument("--check-retrieval", action="store_true",
                        help="run optional end-to-end retrieval expectations")
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.suite).read_text(encoding="utf-8"))
        if args.case == LIST_CASES:
            return list_answer_cases(payload)
        result = validate_suite(payload, index_path=args.index)
        if args.check_retrieval:
            result.update(validate_retrieval_cases(payload, args.index))
        selected_case = get_answer_case(payload, args.case) if args.case else None
    except (OSError, json.JSONDecodeError, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}))
        if isinstance(exc, ValueError) and str(exc).startswith("unknown answer case_id"):
            list_answer_cases(json.loads(Path(args.suite).read_text(encoding="utf-8")))
        return 1
    if selected_case is not None:
        print(json.dumps({"status": "VALID", "case": selected_case}, indent=2, ensure_ascii=False))
        return 0
    print(json.dumps({"status": "VALID", **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
