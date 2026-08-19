import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "eval_compare_prompt_arms.py"
SPEC = importlib.util.spec_from_file_location("compare_suite_runs", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _write_report(root, arm, rep, rows, *, signature="index:1", model="model",
                  suite_version=4):
    report_dir = root / arm / f"rep-{rep}"
    report_dir.mkdir(parents=True)
    results = []
    for case_id, classification, expected in rows:
        result_path = report_dir / f"{case_id}.json"
        result_path.write_text(json.dumps({
            "attempts": [{"synthesis": {"classification": classification}}]
        }))
        results.append({
            "case_id": case_id,
            "expected_outcome": expected,
            "output_path": str(result_path),
        })
    report_path = report_dir / "report.json"
    report_path.write_text(json.dumps({
        "model": model,
        "prompt_version": arm,
        "index_signature": signature,
        "suite_version": suite_version,
        "results": results,
    }))
    return report_path


def test_arms_scored_against_different_suite_versions_are_refused(tmp_path):
    """A stale arm from an earlier benchmark version must not be comparable.

    The benchmark itself is an experimental variable: an arm scored against
    repaired goldens will beat one scored against broken goldens for reasons
    that have nothing to do with the prompt.
    """
    rows = [("one", "SUPPORTED", "SUPPORTED")]
    old = _write_report(tmp_path, "arm-old", 1, rows, suite_version=2)
    new = _write_report(tmp_path, "arm-new", 1, rows, suite_version=4)
    with pytest.raises(ValueError, match="different suite versions"):
        MODULE.compare_reports([old], [new])


def test_mixed_suite_versions_within_one_arm_are_refused(tmp_path):
    rows = [("one", "SUPPORTED", "SUPPORTED")]
    first = _write_report(tmp_path, "arm-a", 1, rows, suite_version=2)
    second = _write_report(tmp_path, "arm-a", 2, rows, suite_version=4)
    with pytest.raises(ValueError, match="different suite versions"):
        MODULE.compare_reports([first, second], [second])


def test_hidden_composition_difference_is_discriminating(tmp_path):
    cases_a = [("one", "SUPPORTED", "SUPPORTED"), ("two", "INSUFFICIENT_EVIDENCE", "SUPPORTED")]
    cases_b = [("one", "INSUFFICIENT_EVIDENCE", "SUPPORTED"), ("two", "SUPPORTED", "SUPPORTED")]
    a = [_write_report(tmp_path, "v4", 1, cases_a), _write_report(tmp_path, "v4", 2, cases_a)]
    b = [_write_report(tmp_path, "v5", 1, cases_b), _write_report(tmp_path, "v5", 2, cases_b)]
    report = MODULE.compare_reports(a, b)
    assert report["aggregates"]["all_cases"]["arm_a_matches"] == 2
    assert report["aggregates"]["all_cases"]["arm_b_matches"] == 2
    assert report["case_role_counts"]["discriminating"] == 2
    assert report["aggregates"]["discriminating_cases"]["case_count"] == 2


def test_unstable_case_is_noise_and_excluded(tmp_path):
    a = [_write_report(tmp_path, "v4", 1, [("stable", "SUPPORTED", "SUPPORTED"), ("noisy", "SUPPORTED", "SUPPORTED")]),
         _write_report(tmp_path, "v4", 2, [("stable", "SUPPORTED", "SUPPORTED"), ("noisy", "INSUFFICIENT_EVIDENCE", "SUPPORTED")])]
    b = [_write_report(tmp_path, "v5", 1, [("stable", "INSUFFICIENT_EVIDENCE", "SUPPORTED"), ("noisy", "SUPPORTED", "SUPPORTED")]),
         _write_report(tmp_path, "v5", 2, [("stable", "INSUFFICIENT_EVIDENCE", "SUPPORTED"), ("noisy", "SUPPORTED", "SUPPORTED")])]
    report = MODULE.compare_reports(a, b)
    assert report["case_matrix"]["noisy"]["role"] == "noise"
    assert report["aggregates"]["discriminating_cases"]["case_count"] == 1
    assert report["within_arm_variance"]["unstable_cases"] == ["noisy"]


def test_mismatched_index_signature_refuses(tmp_path):
    a = [_write_report(tmp_path, "v4", 1, [("one", "SUPPORTED", "SUPPORTED")])]
    b = [_write_report(tmp_path, "v5", 1, [("one", "SUPPORTED", "SUPPORTED")], signature="index:2")]
    with pytest.raises(ValueError, match="index_signatures"):
        MODULE.compare_reports(a, b)
