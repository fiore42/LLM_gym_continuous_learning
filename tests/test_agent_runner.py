import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm_gym.agent.agent_runner import run_agent_task
from llm_gym.agent.agent_task import TaskSpec
from llm_gym.agent.model_client import ModelProviderError


def contains_ordered(actual: list[str], expected: list[str]) -> bool:
    """Return whether every expected stage appears, in order, within actual.

    Membership alone is too weak for a lifecycle claim: it cannot tell a
    draft->evaluate->revise->draft->evaluate run from one that skipped the
    second draft. Gaps are allowed so wrapper stages such as prepare,
    retrieve, and checkpoint do not have to be restated by every case.
    """
    remaining = iter(actual)
    return all(stage in remaining for stage in expected)


class SequenceClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        raw = next(self.responses)
        payload = json.loads(raw)
        if "evidence_assessment" not in payload:
            ids = [line.split("\n", 1)[0] for line in kwargs["user"].split("EVIDENCE_ID: ")[1:]]
            payload["evidence_assessment"] = [
                {"evidence_id": evidence_id, "relevant": True, "reason": "Relevant test evidence."}
                for evidence_id in ids
            ]
        return json.dumps(payload)


class CrashClient(SequenceClient):
    def complete(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return '{"answer":"bad","classification":"SUPPORTED","citation_ids":["unknown"]}'
        raise RuntimeError("simulated interruption")


class UsageThenProviderFailure:
    def __init__(self):
        self.calls = 0
        self.last_usage = {}

    def complete(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            self.last_usage = {"cost_usd": 1.0}
            return '{"answer":"answer","classification":"SUPPORTED","citation_ids":["e1"]}'
        raise TimeoutError("provider timeout")


class UsageSequenceClient(SequenceClient):
    def complete(self, **kwargs):
        self.last_usage = {"cost_usd": 1.0}
        return super().complete(**kwargs)


class BilledValidationFailureThenCrash:
    def __init__(self):
        self.calls = 0
        self.last_usage = {}

    def complete(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            self.last_usage = {"cost_usd": 1.25, "output_tokens": 10}
            return '{"answer":"bad","classification":"SUPPORTED","citation_ids":["unknown"]}'
        raise RuntimeError("simulated interruption after billed rejection")


class InvalidRequestClient:
    def __init__(self):
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        raise ModelProviderError("HTTP 400: model not found", retryable=False)


class AgentRunnerTests(unittest.TestCase):
    def test_success_is_cached_and_second_run_does_not_call_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "canonical_url": "https://example.test/1",
                         "locator": "00:01", "snippet": "Agents use memory."},)
            response = '{"answer":"Agents use memory.","classification":"SUPPORTED","citation_ids":["e1"]}'
            client = SequenceClient([response])
            spec = TaskSpec.from_global_parameters("task-1", "How do agents use memory?")
            first = run_agent_task(spec, evidence, client, model="test", checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            second = run_agent_task(spec, evidence, SequenceClient([]), model="test", checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertEqual(first["outcome"], "COMPLETED")
            self.assertEqual(first["loop"]["loop_type"], "AGENT_TASK")
            self.assertTrue(first["loop"]["run_id"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(client.calls, 1)

    def test_cache_key_changes_when_task_limits_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            response = '{"answer":"answer","classification":"SUPPORTED","citation_ids":["e1"]}'
            first_client = SequenceClient([response])
            first_spec = TaskSpec("task-limits", "Question", 3, 60, 20, 25.0, 0.8, 0.8)
            run_agent_task(first_spec, evidence, first_client, model="test",
                           checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            second_client = SequenceClient([response])
            changed_spec = TaskSpec("task-limits", "Question", 3, 60, 20, 25.0, 0.8, 0.7)
            result = run_agent_task(changed_spec, evidence, second_client, model="test",
                                    checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertFalse(result["cache_hit"])
            self.assertEqual(second_client.calls, 1)

    def test_cache_key_changes_when_output_schema_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            response = '{"answer":"answer","classification":"SUPPORTED","citation_ids":["e1"]}'
            first = TaskSpec("task-schema", "Question", 3, 60, 20, 25.0, 0.8, 0.8, output_schema_version=1)
            run_agent_task(first, evidence, SequenceClient([response]), model="test",
                           checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            second = TaskSpec("task-schema", "Question", 3, 60, 20, 25.0, 0.8, 0.8, output_schema_version=2)
            client = SequenceClient([response])
            result = run_agent_task(second, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertFalse(result["cache_hit"])
            self.assertEqual(client.calls, 1)

    def test_interrupted_task_resumes_after_completed_round(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            spec = TaskSpec("task-resume", "Question", 2, 60, 20, 25.0, 0.8, 0.8)
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                run_agent_task(spec, evidence, CrashClient([]), model="test",
                               checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            interrupted = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
            interrupted_run_id = interrupted["loop"]["run_id"]
            resumed = run_agent_task(
                spec, evidence,
                SequenceClient(['{"answer":"fixed","classification":"SUPPORTED","citation_ids":["e1"]}']),
                model="test", checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertEqual(resumed["outcome"], "COMPLETED_AFTER_RETRY")
            self.assertEqual([attempt["round"] for attempt in resumed["attempts"]], [1, 2])
            # Trajectory case checkpoint_resume: round one is not repeated, the
            # attempt history survives, and the loop identity is stable across
            # the interruption so both halves belong to the same run.
            #
            self.assertEqual(resumed["attempts"][0]["error_type"], "ValueError")
            self.assertIn("usage", resumed["attempts"][0])
            self.assertEqual(resumed["loop"]["run_id"], interrupted_run_id)

    def test_resume_preserves_billed_spend_from_a_rejected_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            spec = TaskSpec("task-billed-resume", "Question", 2, 60, 20, 25.0, 0.8, 0.8)
            with self.assertRaisesRegex(RuntimeError, "billed rejection"):
                run_agent_task(
                    spec, evidence, BilledValidationFailureThenCrash(), model="test",
                    checkpoint_path=root / "checkpoint.json",
                    cache_path=root / "cache.json")

            checkpoint = json.loads(
                (root / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["attempts"][0]["usage"]["cost_usd"], 1.25)
            self.assertEqual(checkpoint["cost_usd"], 1.25)

            resumed = run_agent_task(
                spec, evidence,
                SequenceClient(['{"answer":"fixed","classification":"SUPPORTED","citation_ids":["e1"]}']),
                model="test", checkpoint_path=root / "checkpoint.json",
                cache_path=root / "cache.json")
            self.assertEqual(resumed["outcome"], "COMPLETED_AFTER_RETRY")
            self.assertEqual(resumed["cost_usd"], 1.25)

    def test_unreadable_checkpoint_and_cache_do_not_block_a_run(self):
        """A kill mid-write can leave truncated JSON on disk. Neither file is
        authoritative enough to fail the run: the task must restart rather than
        refuse to work until an operator deletes the files by hand."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "checkpoint.json").write_text('{"task_id": "task-tru', encoding="utf-8")
            (root / "cache.json").write_text("not json at all", encoding="utf-8")
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            client = SequenceClient(['{"answer":"answer","classification":"SUPPORTED","citation_ids":["e1"]}'])
            spec = TaskSpec("task-truncated", "Question", 2, 60, 20, 25.0, 0.8, 0.8)
            result = run_agent_task(spec, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json",
                                    cache_path=root / "cache.json")
            self.assertEqual(result["outcome"], "COMPLETED")
            self.assertEqual(client.calls, 1)

    def test_running_checkpoint_for_different_inputs_is_not_resumed(self):
        """Resume eligibility is keyed, not positional. A RUNNING checkpoint
        left by a different question, model, or budget must not donate its
        attempt history to an unrelated task sharing the checkpoint path."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            interrupted_spec = TaskSpec("task-key", "Question", 2, 60, 20, 25.0, 0.8, 0.8)
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                run_agent_task(interrupted_spec, evidence, CrashClient([]), model="test",
                               checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            interrupted = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(interrupted["outcome"], "RUNNING")
            other_spec = TaskSpec("task-key", "A different question", 2, 60, 20, 25.0, 0.8, 0.8)
            client = SequenceClient(['{"answer":"answer","classification":"SUPPORTED","citation_ids":["e1"]}'])
            result = run_agent_task(other_spec, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json",
                                    cache_path=root / "cache.json")
            self.assertEqual(result["outcome"], "COMPLETED")
            self.assertEqual([attempt["round"] for attempt in result["attempts"]], [1])
            self.assertNotEqual(result["loop"]["run_id"], interrupted["loop"]["run_id"])

    def test_resume_past_the_time_budget_spends_no_further_call(self):
        """A resumed run inherits its predecessor's clock. If the wall-clock
        budget already elapsed while the process was dead, the resume must stop
        on the budget instead of buying one more round on a fresh timer."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            spec = TaskSpec("task-stale-clock", "Question", 2, 60, 20, 25.0, 0.8, 0.8)
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                run_agent_task(spec, evidence, CrashClient([]), model="test",
                               checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            interrupted = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
            interrupted["started_at"] = (
                datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            (root / "checkpoint.json").write_text(
                json.dumps(interrupted), encoding="utf-8")
            client = SequenceClient(['{"answer":"answer","classification":"SUPPORTED","citation_ids":["e1"]}'])
            result = run_agent_task(spec, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json",
                                    cache_path=root / "cache.json")
            self.assertEqual(client.calls, 0)
            self.assertEqual(result["outcome"], "FAILED_BUDGET")
            self.assertEqual(result["stop_reason"], "BUDGET_EXHAUSTED")
            self.assertEqual(result["model_calls"], len(interrupted["attempts"]))

    def test_cached_result_with_a_non_reusable_outcome_is_ignored(self):
        """The cache is only ever written for outcomes that passed their
        evaluation policy. A file claiming otherwise is not trusted to
        short-circuit a run, or an escalation would answer for a real task."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            spec = TaskSpec("task-stale-cache", "Question", 2, 60, 20, 25.0, 0.8, 0.8)
            escalated = run_agent_task(
                spec, evidence,
                SequenceClient(['{"answer":"bad","classification":"SUPPORTED","citation_ids":["unknown"]}'] * 2),
                model="test", checkpoint_path=root / "checkpoint.json",
                cache_path=root / "cache.json")
            self.assertEqual(escalated["outcome"], "ESCALATED_FOR_REVIEW")
            (root / "cache.json").write_text(json.dumps(escalated), encoding="utf-8")
            client = SequenceClient(['{"answer":"answer","classification":"SUPPORTED","citation_ids":["e1"]}'])
            result = run_agent_task(spec, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json",
                                    cache_path=root / "cache.json")
            self.assertEqual(client.calls, 1)
            self.assertFalse(result["cache_hit"])
            self.assertEqual(result["outcome"], "COMPLETED")

    def test_invalid_responses_escalate_after_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            client = SequenceClient(['{"answer":"bad","classification":"SUPPORTED","citation_ids":["unknown"]}'] * 3)
            spec = TaskSpec.from_global_parameters("task-2", "Question")
            result = run_agent_task(spec, evidence, client, model="test", checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertEqual(result["outcome"], "ESCALATED_FOR_REVIEW")
            self.assertEqual(result["stop_reason"], "QUALITY_GATE_NOT_REACHED")
            self.assertEqual(len(result["attempts"]), 3)
            self.assertIn("rendered_user_prompt", result["attempts"][0]["prompt"])
            self.assertIn("Question: Question", result["attempts"][0]["prompt"]["rendered_user_prompt"])
            self.assertTrue((root / "checkpoint.json").is_file())

    def test_escalation_package_is_actionable_without_the_code(self):
        """Trajectory case actionable_escalation: a reviewer opening only the
        checkpoint must find the failed criteria, the last output, the evidence
        the task was given, the budget state, and an explicit next action."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},
                        {"evidence_id": "e2", "snippet": "more text"})
            response = '{"answer":"thin","classification":"SUPPORTED","citation_ids":["e1"]}'
            client = SequenceClient([response] * 3)
            spec = TaskSpec("task-escalation", "Question", 3, 60, 20, 25.0, 0.8, 0.95)
            result = run_agent_task(spec, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json",
                                    cache_path=root / "cache.json")
            self.assertEqual(result["outcome"], "ESCALATED_FOR_REVIEW")
            package = result["human_review"]
            self.assertIn("citation_coverage", package["failed_criteria"])
            self.assertEqual(package["last_output"]["answer"], "thin")
            self.assertEqual(package["last_output"]["citation_ids"], ["e1"])
            self.assertEqual(package["evidence_ids"], ["e1", "e2"])
            self.assertEqual(package["budget_state"]["max_rounds"], 3)
            self.assertEqual(package["budget_state"]["model_calls"], 3)
            self.assertTrue(package["reviewer_next_action"].strip())
            # The package must survive to disk, not just exist in memory.
            saved = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["human_review"]["evidence_ids"], ["e1", "e2"])

    def test_terminal_failed_checkpoint_starts_a_new_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            spec = TaskSpec.from_global_parameters("task-retry-terminal", "Question")
            first = run_agent_task(
                spec, evidence,
                SequenceClient(['{"answer":"bad","classification":"SUPPORTED","citation_ids":["unknown"]}'] * 3),
                model="test", checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertEqual(first["outcome"], "ESCALATED_FOR_REVIEW")
            client = SequenceClient(['{"answer":"fixed","classification":"SUPPORTED","citation_ids":["e1"]}'])
            second = run_agent_task(spec, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json",
                                    cache_path=root / "cache.json")
            self.assertEqual(client.calls, 1)
            self.assertEqual(second["outcome"], "COMPLETED")
            self.assertNotEqual(first["loop"]["run_id"], second["loop"]["run_id"])

    def test_retry_includes_failed_criterion_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},
                        {"evidence_id": "e2", "snippet": "more text"})
            responses = [
                '{"answer":"answer","classification":"SUPPORTED","citation_ids":["e1"]}',
                '{"answer":"answer","classification":"SUPPORTED","citation_ids":["e1","e2"]}',
            ]
            client = SequenceClient(responses)
            spec = TaskSpec("task-3", "Question", 2, 60, 20, 25.0, 0.8, 0.9)
            result = run_agent_task(spec, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertEqual(result["outcome"], "COMPLETED_AFTER_RETRY")
            self.assertIn("citation_coverage", client.last_kwargs["user"])
            # Trajectory case targeted_revision claims an ordered lifecycle, so
            # assert the order. Membership alone passed even when the second
            # draft/evaluate pair was deleted from the implementation.
            self.assertTrue(
                contains_ordered(
                    result["completed_stages"],
                    ["draft", "evaluate", "revise", "draft", "evaluate", "finalize"],
                ),
                f"stage order not satisfied: {result['completed_stages']}",
            )

    def test_retry_includes_exception_validation_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            responses = [
                '{"answer":"The corpus proves this.","classification":"SUPPORTED","citation_ids":["e1"]}',
                '{"answer":"The retrieved evidence supports this.","classification":"SUPPORTED","citation_ids":["e1"]}',
            ]
            client = SequenceClient(responses)
            spec = TaskSpec("task-exception-feedback", "Question", 2, 60, 20, 25.0, 0.8, 0.8)
            result = run_agent_task(spec, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertEqual(result["outcome"], "COMPLETED_AFTER_RETRY")
            self.assertIn("corpus-wide", client.last_kwargs["user"])

    def test_conflicting_evidence_requires_two_distinct_citations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = (
                {"evidence_id": "e1", "snippet": "Use independent review."},
                {"evidence_id": "e2", "snippet": "Self-review can be sufficient."},
            )
            response = (
                '{"answer":"The retrieved sources disagree.","classification":'
                '"CONFLICTING_EVIDENCE","citation_ids":["e1"]}'
            )
            spec = TaskSpec("task-conflict-citations", "Question", 1, 60, 20, 25.0, 0.8, 0.8)
            result = run_agent_task(spec, evidence, SequenceClient([response]),
                                    model="test", checkpoint_path=root / "checkpoint.json",
                                    cache_path=root / "cache.json")
            self.assertEqual(result["outcome"], "ESCALATED_FOR_REVIEW")
            self.assertEqual(result["stop_reason"], "QUALITY_GATE_NOT_REACHED")
            self.assertIn("conflict_citation_coverage",
                          result["attempts"][0]["evaluation"]["critical_failures"])

    def test_cost_budget_produces_failed_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},)
            response = '{"answer":"answer","classification":"SUPPORTED","citation_ids":["unknown"]}'
            client = UsageSequenceClient([response])
            spec = TaskSpec("task-4", "Question", 3, 60, 20, 1.0, 0.8, 0.8)
            result = run_agent_task(spec, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertEqual(result["outcome"], "FAILED_BUDGET")
            self.assertEqual(result["cost_usd"], 1.0)
            # Trajectory case budget_stop_distinct: a resource stop must be
            # labelled as one and must not spend another call afterwards.
            self.assertEqual(result["stop_reason"], "BUDGET_EXHAUSTED")
            self.assertNotEqual(result["outcome"], "ESCALATED_FOR_REVIEW")
            self.assertEqual(client.calls, len(result["attempts"]))

    def test_failed_provider_call_does_not_reuse_previous_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "text"},
                        {"evidence_id": "e2", "snippet": "more text"})
            client = UsageThenProviderFailure()
            spec = TaskSpec("task-usage", "Question", 2, 60, 20, 25.0, 0.8, 0.9)
            result = run_agent_task(spec, evidence, client, model="test",
                                    checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertEqual(result["cost_usd"], 1.0)
            self.assertEqual(result["attempts"][1]["status"], "FAILED")
            self.assertEqual(result["attempts"][0]["usage"]["cost_usd"], 1.0)
            self.assertEqual(result["attempts"][1]["usage"]["cost_usd"], 0.0)

    def test_non_retryable_provider_error_escalates_once_with_distinct_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = InvalidRequestClient()
            spec = TaskSpec.from_global_parameters("task-invalid-provider", "Question")
            result = run_agent_task(spec, ({"evidence_id": "e1", "snippet": "text"},), client,
                                    model="claude-sonnet-5",
                                    checkpoint_path=root / "checkpoint.json",
                                    cache_path=root / "cache.json")
            self.assertEqual(client.calls, 1)
            self.assertEqual(result["outcome"], "ESCALATED_FOR_REVIEW")
            self.assertEqual(result["stop_reason"], "PROVIDER_REQUEST_FAILED")
            self.assertIn("HTTP 400", result["human_review"]["last_error"])

    def test_resume_after_non_retryable_error_does_not_buy_another_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = InvalidRequestClient()
            spec = TaskSpec.from_global_parameters("task-provider-resume", "Question")
            result = run_agent_task(
                spec, ({"evidence_id": "e1", "snippet": "text"},), client,
                model="bad-model", checkpoint_path=root / "checkpoint.json",
                cache_path=root / "cache.json")
            state = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertTrue(state["attempts"][0]["usage"] == {"cost_usd": 0.0})

            # Recreate the narrow crash state: the after-unit checkpoint was
            # durable, but terminal finalization did not happen.
            state["outcome"] = "RUNNING"
            state["non_retryable_provider_error"] = True
            (root / "checkpoint.json").write_text(json.dumps(state), encoding="utf-8")
            no_more_calls = SequenceClient([])
            resumed = run_agent_task(
                spec, ({"evidence_id": "e1", "snippet": "text"},), no_more_calls,
                model="bad-model", checkpoint_path=root / "checkpoint.json",
                cache_path=root / "cache.json")
            self.assertEqual(no_more_calls.calls, 0)
            self.assertEqual(resumed["outcome"], "ESCALATED_FOR_REVIEW")
            self.assertEqual(resumed["stop_reason"], "PROVIDER_REQUEST_FAILED")
            self.assertEqual(len(resumed["attempts"]), 1)

    def test_insufficient_evidence_has_explicit_terminal_outcome_and_is_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = ({"evidence_id": "e1", "snippet": "No latency data."},)
            response = '{"answer":"The supplied evidence does not report latency.","classification":"INSUFFICIENT_EVIDENCE","citation_ids":["e1"]}'
            client = SequenceClient([response])
            spec = TaskSpec("task-insufficient", "What is the latency?", 3, 60, 20, 25.0, 0.8, 0.8)
            first = run_agent_task(spec, evidence, client, model="test",
                                   checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            second = run_agent_task(spec, evidence, SequenceClient([]), model="test",
                                    checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertEqual(first["outcome"], "INSUFFICIENT_EVIDENCE")
            self.assertTrue(second["cache_hit"])

    def test_conflicting_evidence_has_explicit_terminal_outcome_and_is_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = (
                {"evidence_id": "e1", "snippet": "Use independent review."},
                {"evidence_id": "e2", "snippet": "Self-review can be sufficient."},
            )
            response = (
                '{"answer":"The retrieved sources disagree about self-review.",'
                '"classification":"CONFLICTING_EVIDENCE","citation_ids":["e1","e2"]}'
            )
            client = SequenceClient([response])
            spec = TaskSpec("task-conflict", "Is self-review sufficient?", 3, 60, 20, 25.0, 0.8, 0.8)
            first = run_agent_task(spec, evidence, client, model="test",
                                   checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            second = run_agent_task(spec, evidence, SequenceClient([]), model="test",
                                    checkpoint_path=root / "checkpoint.json", cache_path=root / "cache.json")
            self.assertEqual(first["outcome"], "CONFLICTING_EVIDENCE")
            self.assertTrue(second["cache_hit"])
