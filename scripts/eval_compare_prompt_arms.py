#!/usr/bin/env python3
"""Compare two prompt arms across repeated evaluation-suite reports."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any, Iterable


def _read_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _expand_paths(values: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        matches = [Path(item) for item in sorted(glob.glob(value))]
        paths.extend(matches or [Path(value)])
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _classification(result_path: str | Path) -> str:
    result = _read_json(result_path)
    attempts = result.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError(f"result has no attempts: {result_path}")
    for attempt in reversed(attempts):
        synthesis = attempt.get("synthesis") if isinstance(attempt, dict) else None
        if isinstance(synthesis, dict) and synthesis.get("classification"):
            return str(synthesis["classification"])
    raise ValueError(f"result has no classification: {result_path}")


def _load_arm(paths: list[Path], name: str) -> dict[str, Any]:
    if not paths:
        raise ValueError(f"{name} has no report files")
    reports = [_read_json(path) for path in paths]
    models = {str(report.get("model")) for report in reports}
    signatures = {str(report.get("index_signature")) for report in reports}
    prompt_versions = {str(report.get("prompt_version")) for report in reports}
    suite_versions = {str(report.get("suite_version")) for report in reports}
    if len(models) != 1:
        raise ValueError(f"{name} reports use different models: {sorted(models)}")
    if len(signatures) != 1:
        raise ValueError(f"{name} reports use different index_signatures: {sorted(signatures)}")
    if len(prompt_versions) != 1:
        raise ValueError(f"{name} reports use different prompt versions: {sorted(prompt_versions)}")
    if len(suite_versions) != 1:
        raise ValueError(f"{name} reports use different suite versions: {sorted(suite_versions)}")

    cases: dict[str, list[dict[str, Any]]] = {}
    for report_path, report in zip(paths, reports):
        for row in report.get("results") or []:
            if not isinstance(row, dict) or not row.get("case_id"):
                raise ValueError(f"invalid result row in {report_path}")
            case_id = str(row["case_id"])
            output_path = row.get("output_path")
            if not output_path:
                raise ValueError(f"missing output_path for {case_id} in {report_path}")
            classification = _classification(output_path)
            expected = row.get("expected_outcome")
            cases.setdefault(case_id, []).append({
                "classification": classification,
                "match": classification == expected,
                "expected_outcome": expected,
                "report_path": str(report_path),
                "output_path": str(output_path),
            })
    return {
        "name": name,
        "prompt_version": next(iter(prompt_versions)),
        "model": next(iter(models)),
        "index_signature": next(iter(signatures)),
        "suite_version": next(iter(suite_versions)),
        "report_count": len(paths),
        "cases": cases,
    }


def _role(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> str:
    if len(set(item["match"] for item in a)) > 1 or len(set(item["match"] for item in b)) > 1:
        return "noise"
    a_match = a[0]["match"]
    b_match = b[0]["match"]
    if a_match and b_match:
        return "saturated_pass"
    if not a_match and not b_match:
        return "saturated_fail"
    return "discriminating"


def compare_reports(arm_a_paths: list[Path], arm_b_paths: list[Path]) -> dict[str, Any]:
    arm_a = _load_arm(arm_a_paths, "arm_a")
    arm_b = _load_arm(arm_b_paths, "arm_b")
    if arm_a["model"] != arm_b["model"]:
        raise ValueError(f"cannot compare different models: {arm_a['model']} vs {arm_b['model']}")
    if arm_a["index_signature"] != arm_b["index_signature"]:
        raise ValueError(
            "cannot compare different index_signatures: "
            f"{arm_a['index_signature']} vs {arm_b['index_signature']}"
        )
    # The benchmark itself is an experimental variable. Comparing arms scored
    # against different suite versions attributes a benchmark change to the
    # prompt, which is how a stale arm once produced a clean but meaningless
    # result.
    if arm_a["suite_version"] != arm_b["suite_version"]:
        raise ValueError(
            "cannot compare different suite versions: "
            f"{arm_a['suite_version']} vs {arm_b['suite_version']}"
        )
    if set(arm_a["cases"]) != set(arm_b["cases"]):
        raise ValueError("arms contain different case sets")

    case_matrix: dict[str, Any] = {}
    role_counts = {key: 0 for key in ("saturated_pass", "saturated_fail", "noise", "discriminating")}
    deltas: list[dict[str, Any]] = []
    for case_id in sorted(arm_a["cases"]):
        a = arm_a["cases"][case_id]
        b = arm_b["cases"][case_id]
        role = _role(a, b)
        role_counts[role] += 1
        a_matches = sum(item["match"] for item in a)
        b_matches = sum(item["match"] for item in b)
        delta = b_matches - a_matches
        row = {
            "arm_a": {
                "classifications": [item["classification"] for item in a],
                "matches": [item["match"] for item in a],
                "match_count": a_matches,
                "consistent": len({item["match"] for item in a}) == 1,
            },
            "arm_b": {
                "classifications": [item["classification"] for item in b],
                "matches": [item["match"] for item in b],
                "match_count": b_matches,
                "consistent": len({item["match"] for item in b}) == 1,
            },
            "role": role,
        }
        case_matrix[case_id] = row
        if role not in ("saturated_pass", "saturated_fail"):
            deltas.append({
                "case_id": case_id,
                "role": role,
                "arm_a_matches": a_matches,
                "arm_b_matches": b_matches,
                "better_arm": "arm_b" if delta > 0 else "arm_a" if delta < 0 else "tie",
                "delta_b_minus_a": delta,
            })

    cases = len(case_matrix)
    discriminating = [case for case, row in case_matrix.items() if row["role"] == "discriminating"]

    def aggregate(case_ids: list[str]) -> dict[str, int]:
        return {
            "arm_a_matches": sum(case_matrix[c]["arm_a"]["match_count"] for c in case_ids),
            "arm_b_matches": sum(case_matrix[c]["arm_b"]["match_count"] for c in case_ids),
            "arm_a_trials": len(case_ids) * len(arm_a_paths),
            "arm_b_trials": len(case_ids) * len(arm_b_paths),
        }

    report = {
        "analysis_version": 1,
        "provenance": {
            "model": arm_a["model"],
            "index_signature": arm_a["index_signature"],
            "suite_version": arm_a["suite_version"],
            "arm_a_prompt_version": arm_a["prompt_version"],
            "arm_b_prompt_version": arm_b["prompt_version"],
            "arm_a_report_count": len(arm_a_paths),
            "arm_b_report_count": len(arm_b_paths),
        },
        "within_arm_variance": {
            "arm_a_consistent_cases": sum(row["arm_a"]["consistent"] for row in case_matrix.values()),
            "arm_a_case_count": cases,
            "arm_a_consistency": f"{sum(row['arm_a']['consistent'] for row in case_matrix.values())}/{cases}",
            "arm_b_consistent_cases": sum(row["arm_b"]["consistent"] for row in case_matrix.values()),
            "arm_b_case_count": cases,
            "arm_b_consistency": f"{sum(row['arm_b']['consistent'] for row in case_matrix.values())}/{cases}",
            "unstable_cases": [case for case, row in case_matrix.items() if row["role"] == "noise"],
        },
        "case_role_counts": role_counts,
        "aggregates": {
            "all_cases": aggregate(sorted(case_matrix)),
            "discriminating_cases": {
                "case_count": len(discriminating),
                **aggregate(discriminating),
            },
        },
        "case_matrix": case_matrix,
        "per_case_deltas": deltas,
    }
    return report


def _table(report: dict[str, Any]) -> str:
    matrix = report["case_matrix"]
    lines = [
        "Case comparison",
        "case_id | arm_a | arm_b | role",
        "--- | --- | --- | ---",
    ]
    for case_id, row in matrix.items():
        def fmt(arm: str) -> str:
            data = row[arm]
            return f"{data['match_count']}/{len(data['matches'])} " + "/".join(
                "match" if value else "miss" for value in data["matches"]
            )
        lines.append(f"{case_id} | {fmt('arm_a')} | {fmt('arm_b')} | {row['role']}")
    variance = report["within_arm_variance"]
    all_cases = report["aggregates"]["all_cases"]
    disc = report["aggregates"]["discriminating_cases"]
    lines.extend([
        "",
        f"Consistency: arm_a {variance['arm_a_consistency']}; arm_b {variance['arm_b_consistency']}",
        f"Unstable/noise cases: {', '.join(variance['unstable_cases']) or 'none'}",
        f"All cases: arm_a {all_cases['arm_a_matches']}/{all_cases['arm_a_trials']} vs "
        f"arm_b {all_cases['arm_b_matches']}/{all_cases['arm_b_trials']}",
        f"Discriminating cases: {disc['case_count']} — arm_a {disc['arm_a_matches']}/{disc['arm_a_trials']} vs "
        f"arm_b {disc['arm_b_matches']}/{disc['arm_b_trials']}",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm-a", nargs="+", required=True, help="Report paths or glob patterns for arm A")
    parser.add_argument("--arm-b", nargs="+", required=True, help="Report paths or glob patterns for arm B")
    parser.add_argument("--output", required=True, help="JSON analysis output path")
    args = parser.parse_args()
    try:
        report = compare_reports(_expand_paths(args.arm_a), _expand_paths(args.arm_b))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"comparison failed: {exc}", file=sys.stderr)
        return 2
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
