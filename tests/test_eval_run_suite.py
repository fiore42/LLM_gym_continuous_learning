import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval_run_suite import run_suite, suite_artifact_prefix


class SuiteClient:
    def __init__(self):
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        self.last_usage = {"input_tokens": 10, "output_tokens": 10, "cost_usd": 0.001}
        ids = [line.split("\n", 1)[0] for line in kwargs["user"].split("EVIDENCE_ID: ")[1:]]
        return json.dumps({
            "answer": "The evidence supports the answer.",
            "classification": "SUPPORTED",
            "citation_ids": ids,
            "evidence_assessment": [
                {"evidence_id": evidence_id, "relevant": True, "reason": "Direct test evidence."}
                for evidence_id in ids
            ],
        })


class EvalSuiteRunnerTests(unittest.TestCase):
    def _suite(self, path: Path):
        path.write_text(json.dumps({
            "suite_version": "test-suite-v1",
            "answer_cases": [
                {"case_id": "case-a", "question": "Question A", "expected_outcome": "SUPPORTED",
                 "evidence": [{"evidence_id": "a", "snippet": "Evidence A"}]},
                {"case_id": "case-b", "question": "Question B", "expected_outcome": "SUPPORTED",
                 "evidence": [{"evidence_id": "b", "snippet": "Evidence B"}]},
            ],
        }), encoding="utf-8")

    def test_runs_cases_and_resumes_without_new_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "suite.json"
            self._suite(suite)
            client = SuiteClient()
            first = run_suite(suite_path=suite, output_path=root / "report.json",
                              state_path=root / "state.json", cache_dir=root / "cache",
                              model="test-model", client=client)
            self.assertEqual(first["suite_stop_reason"], "SUITE_COMPLETE")
            self.assertEqual(first["completed_tasks"], 2)
            self.assertEqual(first["cache_hit_count"], 0)
            self.assertTrue(first["index_signature"])
            self.assertEqual(client.calls, 2)
            second = run_suite(suite_path=suite, output_path=root / "report.json",
                               state_path=root / "state.json", cache_dir=root / "cache",
                               model="test-model", client=client)
            self.assertEqual(second["completed_tasks"], 2)
            self.assertEqual(second["cache_hit_count"], 0)
            self.assertEqual(client.calls, 2)

    def test_suite_cost_cap_stops_before_next_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "suite.json"
            self._suite(suite)
            report = run_suite(suite_path=suite, output_path=root / "report.json",
                               state_path=root / "state.json", cache_dir=root / "cache",
                               model="test-model", client=SuiteClient(), max_cost_usd=0.000001)
            self.assertEqual(report["suite_stop_reason"], "SUITE_COST_BUDGET_EXHAUSTED")
            self.assertEqual(report["completed_tasks"], 1)

    def test_prompt_version_is_explicit_and_namespaces_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "suite.json"
            self._suite(suite)
            report = run_suite(suite_path=suite, output_path=root / "report.json",
                               state_path=root / "state.json", cache_dir=root / "cache",
                               model="test-model", prompt_version="synthesis-v4",
                               client=SuiteClient())
            self.assertEqual(report["prompt_version"], "synthesis-v4")
            output_path = Path(report["results"][0]["output_path"])
            self.assertIn("eval-suite/synthesis-v4/", str(output_path))
            self.assertIn(report["run_id"], str(output_path))


class SuiteArtifactPathTests(unittest.TestCase):
    """Two arms must not default to the same report, state, or cache path.

    A stale artifact read as the current one is how a prompt comparison once
    reported a clean win between two different benchmark versions.
    """

    def test_each_arm_gets_its_own_prefix(self):
        a = suite_artifact_prefix("claude-sonnet-5", "synthesis-v7")
        b = suite_artifact_prefix("claude-sonnet-5", "synthesis-v6")
        c = suite_artifact_prefix("glm-5.2", "synthesis-v7")
        self.assertEqual(len({a, b, c}), 3)
        # Both fields that select an arm have to appear, or one of them
        # silently stops distinguishing arms.
        self.assertIn("synthesis-v7", a)
        self.assertIn("claude-sonnet-5", a)

    def test_a_prefix_is_a_usable_path_fragment(self):
        prefix = suite_artifact_prefix("Vendor/Model:2025", "synthesis-v7")
        self.assertNotIn("/", prefix[len("data/eval-suite/"):])
        self.assertNotIn(":", prefix)
        self.assertTrue(prefix.startswith("data/eval-suite/"))


class ProviderArmTests(unittest.TestCase):
    """A report must record which environment arm answered, not just the model.

    Without this the CLI could only reach the AGENT_* arm, and the report named
    the model requested rather than the provider that served it — so two arms
    could not be compared without trusting the filename.
    """

    def _suite(self, path: Path):
        path.write_text(json.dumps({
            "suite_version": "test-suite-v1",
            "answer_cases": [
                {"case_id": "case-a", "question": "Question A",
                 "expected_outcome": "SUPPORTED",
                 "evidence": [{"evidence_id": "a", "snippet": "Evidence A"}]},
            ],
        }), encoding="utf-8")

    def test_the_report_records_the_provider_arm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._suite(root / "suite.json")
            report = run_suite(suite_path=root / "suite.json",
                               output_path=root / "r.json", state_path=root / "s.json",
                               cache_dir=root / "c", model="glm-5.2",
                               client=SuiteClient(), provider_prefix="OPEN_WEIGHT")
            self.assertEqual(report["provider_prefix"], "OPEN_WEIGHT")

    def test_the_default_arm_is_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._suite(root / "suite.json")
            report = run_suite(suite_path=root / "suite.json",
                               output_path=root / "r.json", state_path=root / "s.json",
                               cache_dir=root / "c", model="m", client=SuiteClient())
            self.assertEqual(report["provider_prefix"], "AGENT")

    def test_switching_arm_restarts_rather_than_resuming(self):
        """The same model name served by another arm is a different run."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._suite(root / "suite.json")
            client = SuiteClient()
            common = dict(suite_path=root / "suite.json", output_path=root / "r.json",
                          state_path=root / "s.json", cache_dir=root / "c",
                          model="same-name", client=client)
            run_suite(**common, provider_prefix="AGENT")
            self.assertEqual(client.calls, 1)
            run_suite(**common, provider_prefix="OPEN_WEIGHT")
            self.assertEqual(client.calls, 2)   # not resumed from the other arm

    def test_the_default_artifact_path_separates_arms(self):
        agent = suite_artifact_prefix("m", "synthesis-v7", "AGENT")
        other = suite_artifact_prefix("m", "synthesis-v7", "OPEN_WEIGHT")
        self.assertNotEqual(agent, other)
        self.assertIn("agent", agent)
        self.assertIn("open-weight", other)


class ProviderArmWiringTests(unittest.TestCase):
    """The prefix must reach the client factory, not just the report.

    Every other test in this file injects a client, so the `client is None`
    branch — the one the CLI actually takes — was never exercised. Removing the
    prefix from the factory call survived all of them.
    """

    def test_the_prefix_reaches_the_client_factory(self):
        from unittest import mock
        import scripts.eval_run_suite as runner
        seen = {}

        def fake_factory(*, prefix="AGENT", **kwargs):
            seen["prefix"] = prefix
            return SuiteClient()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "suite.json").write_text(json.dumps({
                "suite_version": "test-suite-v1",
                "answer_cases": [
                    {"case_id": "case-a", "question": "Q", "expected_outcome": "SUPPORTED",
                     "evidence": [{"evidence_id": "a", "snippet": "E"}]},
                ],
            }), encoding="utf-8")
            with mock.patch.object(runner, "model_client_from_environment", fake_factory):
                runner.run_suite(suite_path=root / "suite.json",
                                 output_path=root / "r.json", state_path=root / "s.json",
                                 cache_dir=root / "c", model="glm-5.2",
                                 provider_prefix="OPEN_WEIGHT")
        self.assertEqual(seen["prefix"], "OPEN_WEIGHT")
