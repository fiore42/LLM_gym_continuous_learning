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
                  suite_version=4, prompt_version=None, provider_prefix=None,
                  stop_reason="SUITE_COMPLETE", repetitions=1,
                  completed=None, total=None, effective_prompt=None):
    report_dir = root / arm / f"rep-{rep}"
    report_dir.mkdir(parents=True)
    results = []
    for case_id, classification, expected in rows:
        result_path = report_dir / f"{case_id}.json"
        result_path.write_text(json.dumps({
            "attempts": [{"synthesis": {
                "classification": classification,
                "prompt_version": effective_prompt or prompt_version or arm,
            }}]
        }))
        results.append({
            "case_id": case_id,
            "expected_outcome": expected,
            "output_path": str(result_path),
        })
    report_path = report_dir / "report.json"
    payload = {
        "model": model,
        "prompt_version": prompt_version or arm,
        "index_signature": signature,
        "suite_version": suite_version,
        "suite_stop_reason": stop_reason,
        "repetitions": repetitions,
        "completed_tasks": len(results) if completed is None else completed,
        "total_tasks": len(results) if total is None else total,
        "results": results,
    }
    if provider_prefix is not None:
        payload["provider_prefix"] = provider_prefix
    report_path.write_text(json.dumps(payload))
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


ROWS = [("case_a", "SUPPORTED", "SUPPORTED"), ("case_b", "SUPPORTED", "SUPPORTED")]


def test_two_models_on_one_prompt_are_comparable(tmp_path):
    """Comparing models was refused outright; now it is the second valid mode.

    The arms must still agree on prompt version, index signature and suite
    version — only the model and its provider arm may move.
    """
    a = _write_report(tmp_path, "a", 1, ROWS, model="claude-sonnet-5",
                      prompt_version="synthesis-v7", provider_prefix="AGENT")
    b = _write_report(tmp_path, "b", 1, ROWS, model="glm-5.2",
                      prompt_version="synthesis-v7", provider_prefix="OPEN_WEIGHT")
    report = MODULE.compare_reports([a], [b])
    prov = report["provenance"]
    assert prov["comparison_variable"] == "model"
    assert prov["arm_a_model"] == "claude-sonnet-5"
    assert prov["arm_b_model"] == "glm-5.2"
    assert prov["arm_a_provider_prefix"] == "AGENT"
    assert prov["arm_b_provider_prefix"] == "OPEN_WEIGHT"


def test_the_same_model_on_two_prompts_still_reports_a_prompt_comparison(tmp_path):
    a = _write_report(tmp_path, "a", 1, ROWS, prompt_version="synthesis-v5")
    b = _write_report(tmp_path, "b", 1, ROWS, prompt_version="synthesis-v6")
    assert MODULE.compare_reports([a], [b])["provenance"]["comparison_variable"] == "prompt_version"


def test_arms_that_differ_in_both_model_and_prompt_are_refused(tmp_path):
    """Two variables moving at once is the defect Rule 30 exists to prevent."""
    a = _write_report(tmp_path, "a", 1, ROWS, model="claude-sonnet-5",
                      prompt_version="synthesis-v5")
    b = _write_report(tmp_path, "b", 1, ROWS, model="glm-5.2",
                      prompt_version="synthesis-v6")
    with pytest.raises(ValueError, match="both model and prompt"):
        MODULE.compare_reports([a], [b])


def test_identical_arms_are_refused_because_nothing_varies(tmp_path):
    a = _write_report(tmp_path, "a", 1, ROWS, prompt_version="synthesis-v7")
    b = _write_report(tmp_path, "b", 1, ROWS, prompt_version="synthesis-v7")
    with pytest.raises(ValueError, match="no variable to compare"):
        MODULE.compare_reports([a], [b])


def test_one_arm_mixing_provider_prefixes_is_refused(tmp_path):
    """A single arm served by two environments is not one arm."""
    a1 = _write_report(tmp_path, "a1", 1, ROWS, prompt_version="p", provider_prefix="AGENT")
    a2 = _write_report(tmp_path, "a2", 1, ROWS, prompt_version="p", provider_prefix="OPEN_WEIGHT")
    with pytest.raises(ValueError, match="different provider arms"):
        MODULE._load_arm([a1, a2], "arm_a")


def test_an_incomplete_arm_is_refused(tmp_path):
    """A truncated run compared against a complete one reports a difference
    that is an artifact of stopping, not of the variable under test."""
    a = _write_report(tmp_path, "a", 1, ROWS, prompt_version="p1",
                      stop_reason="SUITE_COST_BUDGET_EXHAUSTED")
    b = _write_report(tmp_path, "b", 1, ROWS, prompt_version="p2")
    with pytest.raises(ValueError, match="did not complete"):
        MODULE.compare_reports([a], [b])


def test_a_report_missing_results_is_refused(tmp_path):
    a = _write_report(tmp_path, "a", 1, ROWS, prompt_version="p1", total=5)
    b = _write_report(tmp_path, "b", 1, ROWS, prompt_version="p2")
    with pytest.raises(ValueError, match="incomplete"):
        MODULE.compare_reports([a], [b])


def test_multiple_repetitions_inside_one_report_are_refused(tmp_path):
    """The trial denominator is cases x reports, so 3 reps in one report would
    be counted once. Refusing is better than reporting a wrong denominator."""
    a = _write_report(tmp_path, "a", 1, ROWS, prompt_version="p1", repetitions=3)
    b = _write_report(tmp_path, "b", 1, ROWS, prompt_version="p2")
    with pytest.raises(ValueError, match="one repetition per report"):
        MODULE.compare_reports([a], [b])


def test_unequal_report_counts_are_refused(tmp_path):
    a1 = _write_report(tmp_path, "a1", 1, ROWS, prompt_version="p1")
    a2 = _write_report(tmp_path, "a2", 1, ROWS, prompt_version="p1")
    b = _write_report(tmp_path, "b", 1, ROWS, prompt_version="p2")
    with pytest.raises(ValueError, match="different report counts"):
        MODULE.compare_reports([a1, a2], [b])


def test_a_model_comparison_requires_the_same_effective_prompt(tmp_path):
    """The header naming a prompt is not evidence the model received it.

    A header once named one version while every attempt rendered another, which
    is what invalidated this repository's only prompt comparison.
    """
    a = _write_report(tmp_path, "a", 1, ROWS, model="m1", prompt_version="p",
                      provider_prefix="AGENT", effective_prompt="synthesis-v7")
    b = _write_report(tmp_path, "b", 1, ROWS, model="m2", prompt_version="p",
                      provider_prefix="OPEN_WEIGHT", effective_prompt="synthesis-v6")
    with pytest.raises(ValueError, match="same effective prompt"):
        MODULE.compare_reports([a], [b])


def test_one_arm_rendering_two_prompts_is_refused(tmp_path):
    a1 = _write_report(tmp_path, "a1", 1, ROWS, prompt_version="p1",
                       effective_prompt="synthesis-v6")
    a2 = _write_report(tmp_path, "a2", 1, ROWS, prompt_version="p1",
                       effective_prompt="synthesis-v7")
    with pytest.raises(ValueError, match="more than one prompt version"):
        MODULE._load_arm([a1, a2], "arm_a")


def test_the_effective_prompt_is_reported_even_when_it_matches(tmp_path):
    a = _write_report(tmp_path, "a", 1, ROWS, prompt_version="p1", effective_prompt="v6")
    b = _write_report(tmp_path, "b", 1, ROWS, prompt_version="p2", effective_prompt="v6")
    prov = MODULE.compare_reports([a], [b])["provenance"]
    # Headers say p1/p2; both actually rendered v6. Surfacing that is the point.
    assert prov["arm_a_effective_prompt"] == ["v6"]
    assert prov["arm_b_effective_prompt"] == ["v6"]
