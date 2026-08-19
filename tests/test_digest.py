import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm_gym.agent.agent_task import TaskOutcome, TaskSpec
from llm_gym.agent.digest import digest_cache_key, rank_assessments, run_digest
from llm_gym.agent.significance import SIGNIFICANCE_PROMPT_VERSION
from llm_gym.agent.model_client import ModelProviderError

START = datetime(2026, 8, 17, 9, tzinfo=timezone.utc)


def _item(number: int, text: str, source_key: str | None = None) -> dict:
    return {"evidence_id": f"id{number}", "title": f"title {number}",
            "canonical_url": f"https://example.test/{number}", "platform": "youtube",
            "source_key": source_key or f"channel-{number}",
            "published_at_utc": f"2026-08-{number:02d}T00:00:00+00:00", "text": text}


def _snapshot(*items, index_signature: str = "sig-1") -> dict:
    return {"index_signature": index_signature, "since": "2026-08-01T00:00:00+00:00",
            "until": "2026-08-07T00:00:00+00:00", "platforms": ["youtube"],
            "items": list(items)}


# Two items share a source so the breakdown has to distinguish and total.
ITEMS = (_item(1, "The router cut p95 latency in half.", "channel-a"),
         _item(2, "We shipped a brand new logo today.", "channel-a"),
         _item(3, "Batching raised throughput by forty percent.", "channel-b"))


def _spec(**overrides) -> TaskSpec:
    values = {"task_id": "digest", "question": "window", "max_rounds": 3,
              "max_minutes": 60, "max_model_calls": 100, "max_cost_usd": 5.0,
              "stop_at_budget_fraction": 0.8, "minimum_eval_pass_fraction": 0.8}
    values.update(overrides)
    return TaskSpec(**values)


class Client:
    """Quotes a real span of whatever item it is given."""

    def __init__(self, fail_on: set[str] | None = None, retryable: bool = True):
        self.last_usage = {}
        self.seen: list[str] = []
        self.fail_on = fail_on or set()
        self.retryable = retryable

    def complete(self, **kwargs):
        user = kwargs["user"]
        item_id = user.split("ITEM_ID: ")[1].split("\n")[0].strip()
        self.seen.append(item_id)
        if item_id in self.fail_on:
            raise ModelProviderError(f"provider refused {item_id}", retryable=self.retryable)
        self.last_usage = {
            "cost_usd": 0.01,
            "input_tokens": 200,
            "output_tokens": 100,
            "latency_seconds": 2.0,
        }
        text = user.split("TEXT:\n")[1].split("\n\n")[0]
        return json.dumps({"supporting_evidence": [{
                               "claim_component": "a change", "quote": text[:24]}],
                           "claimed_change": "a change", "problem_addressed": "a problem",
                           "significance": "PROMOTIONAL" if "logo" in text else "SIGNIFICANT",
                           "reason": "because the item says so"})


class DigestRunTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.checkpoint = Path(self._tmp.name) / "digest-checkpoint.json"
        self.addCleanup(self._tmp.cleanup)

    def _run(self, client, snapshot=None, **overrides):
        return run_digest(snapshot=snapshot or _snapshot(*ITEMS), model="test-model",
                          client=client, spec=overrides.pop("spec", _spec()),
                          checkpoint_path=self.checkpoint, clock=lambda: START, **overrides)

    def test_every_item_is_assessed_once_and_ranked_deterministically(self):
        client = Client()
        result = self._run(client)
        self.assertEqual(result["outcome"], TaskOutcome.COMPLETED.value)
        self.assertTrue(result["complete"])
        self.assertEqual(client.seen, ["id1", "id2", "id3"])
        self.assertEqual(result["label_counts"]["SIGNIFICANT"], 2)
        self.assertEqual(result["label_counts"]["PROMOTIONAL"], 1)
        # Significant first, then oldest-first inside a label.
        self.assertEqual([row["item_id"] for row in result["ranked"]],
                         ["id1", "id3", "id2"])

    def test_resuming_skips_assessed_items_but_retries_refused_ones(self):
        """The property the whole long run depends on.

        A successful assessment was paid for and must never be repeated. A
        refusal may have been transient — a spend cap, a provider outage — so
        the item returns to the queue rather than being written off.
        """
        first = Client(fail_on={"id2"}, retryable=False)
        self._run(first)
        self.assertEqual(first.seen, ["id1", "id2", "id3"])

        state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        state["outcome"] = TaskOutcome.RUNNING.value
        self.checkpoint.write_text(json.dumps(state), encoding="utf-8")
        second = Client()
        result = self._run(second)
        self.assertEqual(second.seen, ["id2"], "only the refused item is retried")
        self.assertEqual(len(result["assessments"]), 3)
        # Spend from the interrupted run is carried, not restarted.
        self.assertGreater(result["cost_usd"], 0.01)

    def test_resuming_a_fully_assessed_window_calls_nothing(self):
        client = Client()
        self._run(client)
        state = json.loads(self.checkpoint.read_text(encoding="utf-8"))
        state["outcome"] = TaskOutcome.RUNNING.value
        self.checkpoint.write_text(json.dumps(state), encoding="utf-8")
        second = Client()
        result = self._run(second)
        self.assertEqual(second.seen, [])
        self.assertEqual(len(result["assessments"]), 3)

    def test_a_completed_digest_is_reused_without_calling_the_model(self):
        self._run(Client())
        again = Client()
        result = self._run(again)
        self.assertTrue(result["cache_hit"])
        self.assertEqual(again.seen, [])

    def test_a_changed_index_is_a_different_digest(self):
        """A rebuilt index may hold different items for the same window."""
        self._run(Client())
        fresh = Client()
        result = self._run(fresh, snapshot=_snapshot(*ITEMS, index_signature="sig-2"))
        self.assertFalse(result["cache_hit"])
        self.assertEqual(fresh.seen, ["id1", "id2", "id3"])

    def test_one_refused_item_does_not_end_the_window_but_does_escalate(self):
        """Every item is attempted; a window with unassessed items is not done.

        Reporting COMPLETED here would cache the report as reusable, so a later
        invocation would return it and never retry the item. ESCALATED_FOR_REVIEW
        sits outside the reusable set, so the next run retries exactly the items
        that failed.
        """
        client = Client(fail_on={"id2"}, retryable=False)
        result = self._run(client)
        self.assertEqual(len(result["assessments"]), 2)
        self.assertEqual(len(result["rejected"]), 1)
        self.assertEqual(result["rejected"][0]["item_id"], "id2")
        self.assertTrue(result["attempted_every_item"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["outcome"], TaskOutcome.ESCALATED_FOR_REVIEW.value)

    def test_a_window_with_rejections_is_not_cached_as_reusable(self):
        """Otherwise the rejected items are lost behind a cache hit."""
        self._run(Client(fail_on={"id2"}, retryable=False))
        retry = Client()
        result = self._run(retry)
        self.assertFalse(result["cache_hit"])
        self.assertEqual(retry.seen, ["id2"], "only the previously refused item is retried")
        self.assertTrue(result["complete"])
        self.assertEqual(result["outcome"], TaskOutcome.COMPLETED.value)

    def test_a_rejection_records_the_failure_that_actually_happened(self):
        """Fifteen rejections in a long run all read "retries exhausted", which
        told a reader nothing about any of them (Rule 4)."""
        class AlwaysInvalid(Client):
            def complete(self, **kwargs):
                super().complete(**kwargs)
                return json.dumps({"claimed_change": "c", "problem_addressed": "p",
                                   "significance": "SIGNIFICANT", "reason": "r",
                                   "supporting_evidence": [{
                                       "claim_component": "c",
                                       "quote": "words that are not in the item"}]})

        result = self._run(AlwaysInvalid())
        self.assertEqual(len(result["rejected"]), len(ITEMS))
        error = result["rejected"][0]
        self.assertEqual(error["error_type"], "ValueError")
        self.assertIn("does not appear in the item text", error["error"])
        self.assertNotIn("retries exhausted", error["error"])

    def test_a_retryable_failure_is_retried_with_feedback(self):
        class RecoverOnRetry(Client):
            def complete(self, **kwargs):
                item_id = kwargs["user"].split("ITEM_ID: ")[1].split("\n")[0].strip()
                if item_id == "id2" and "id2" not in self.seen:
                    self.seen.append("id2")
                    raise ModelProviderError("transient", retryable=True)
                return super().complete(**kwargs)

        client = RecoverOnRetry()
        result = self._run(client)
        self.assertEqual(len(result["assessments"]), 3)
        self.assertEqual(result["rejected"], [])
        self.assertEqual(result["max_item_retries"], 1)

    def test_retries_count_provider_requests_and_all_known_usage(self):
        class InvalidQuoteThenValid(Client):
            def __init__(self):
                super().__init__()
                self.id2_attempts = 0

            def complete(self, **kwargs):
                item_id = kwargs["user"].split("ITEM_ID: ")[1].split("\n")[0].strip()
                if item_id == "id2":
                    self.id2_attempts += 1
                    if self.id2_attempts == 1:
                        self.seen.append(item_id)
                        self.last_usage = {
                            "cost_usd": 0.01, "input_tokens": 200,
                            "output_tokens": 100, "latency_seconds": 2.0,
                        }
                        return json.dumps({
                            "claimed_change": "c", "problem_addressed": "p",
                            "significance": "SIGNIFICANT", "reason": "r",
                            "supporting_evidence": [{
                                "claim_component": "c",
                                "quote": "not present in the source",
                            }],
                        })
                return super().complete(**kwargs)

        result = self._run(InvalidQuoteThenValid())
        self.assertEqual(result["items_attempted"], 3)
        self.assertEqual(result["provider_calls"], 4)
        self.assertEqual(result["model_calls"], 4)
        self.assertTrue(result["provider_usage_complete"])
        self.assertEqual(len(result["provider_usage"]), 4)
        self.assertEqual(result["cost_usd"], 0.04)
        self.assertEqual(result["usage_totals"]["input_tokens"], 800)
        self.assertEqual(result["usage_totals"]["output_tokens"], 400)
        self.assertEqual(result["usage_totals"]["model_latency_seconds"], 8.0)

    def test_failed_request_does_not_reuse_the_previous_request_usage(self):
        result = self._run(Client(fail_on={"id2"}, retryable=False))
        self.assertEqual(result["provider_calls"], 3)
        self.assertFalse(result["provider_usage_complete"])
        self.assertEqual(result["cost_usd"], 0.02)
        self.assertEqual(result["usage_totals"]["output_tokens"], 200)
        self.assertEqual(result["usage_totals"]["model_latency_seconds"], 4.0)

    def test_a_cost_budget_stops_the_window_and_reports_failed_budget(self):
        client = Client()
        # 80% of $0.02 is reached after two items at $0.01 each.
        result = self._run(client, spec=_spec(max_cost_usd=0.02))
        self.assertEqual(result["outcome"], TaskOutcome.FAILED_BUDGET.value)
        self.assertFalse(result["complete"])
        self.assertLess(len(result["assessments"]), 3)

    def test_the_report_states_that_rankings_are_unvalidated(self):
        """A tidy report must not imply a claim no labels support."""
        result = self._run(Client())
        self.assertIn("M6.2", result["evaluation_note"])
        self.assertIn("unvalidated", result["evaluation_note"])
        self.assertIn("selected model decisions", result["evaluation_note"])
        self.assertIn("not missed claims or corpus-level ranking", result["evaluation_note"])

    def test_the_window_and_its_provenance_travel_with_the_result(self):
        result = self._run(Client())
        self.assertEqual(result["window"]["index_signature"], "sig-1")
        self.assertEqual(result["window"]["platforms"], ["youtube"])
        self.assertTrue(result["prompt_version"])
        self.assertEqual(result["model"], "test-model")

    def test_an_empty_window_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no items"):
            self._run(Client(), snapshot=_snapshot())


class CacheKeyTests(unittest.TestCase):
    def test_the_key_covers_every_input_that_changes_the_content(self):
        base = _snapshot(*ITEMS)
        key = digest_cache_key(base, "model-a", "significance-v1")
        variants = {
            "index": digest_cache_key(_snapshot(*ITEMS, index_signature="other"),
                                      "model-a", "significance-v1"),
            "items": digest_cache_key(_snapshot(*ITEMS[:2]), "model-a", "significance-v1"),
            "model": digest_cache_key(base, "model-b", "significance-v1"),
            "prompt": digest_cache_key(base, "model-a", "significance-v2"),
        }
        for name, other in variants.items():
            with self.subTest(field=name):
                self.assertNotEqual(key, other)

    def test_the_key_is_stable_for_identical_inputs(self):
        base = _snapshot(*ITEMS)
        self.assertEqual(digest_cache_key(base, "m", "p"), digest_cache_key(base, "m", "p"))


class RankingTests(unittest.TestCase):
    def test_ranking_is_by_label_then_oldest_first(self):
        rows = [
            {"item_id": "b", "significance": "PROMOTIONAL", "published_at": "2026-08-01"},
            {"item_id": "c", "significance": "SIGNIFICANT", "published_at": "2026-08-05"},
            {"item_id": "a", "significance": "SIGNIFICANT", "published_at": "2026-08-02"},
            {"item_id": "d", "significance": "UNSUPPORTED", "published_at": "2026-08-03"},
        ]
        self.assertEqual([row["item_id"] for row in rank_assessments(rows)],
                         ["a", "c", "d", "b"])


if __name__ == "__main__":
    unittest.main()


class RunRecordTests(unittest.TestCase):
    """Each run must be findable and describable without opening the corpus.

    The first version embedded the full rendered prompt in every assessment,
    which duplicated each item's text into the report: 48 items produced a
    1.24 MB report plus an identical checkpoint, and every checkpoint write
    reserialised the whole file, so I/O grew with progress.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _run(self, **overrides):
        return run_digest(snapshot=_snapshot(*ITEMS), model="test-model",
                          client=Client(), spec=_spec(),
                          checkpoint_path=self.root / "cp.json",
                          run_log_path=self.root / "run-log.jsonl",
                          clock=lambda: START, **overrides)

    def test_an_assessment_keeps_the_prompt_identity_not_its_rendering(self):
        result = self._run()
        row = result["assessments"][0]
        self.assertTrue(row["prompt_sha256"])
        self.assertNotIn("prompt", row)
        # The identity lives once at run level, where it cannot be duplicated.
        self.assertEqual(result["prompt_sha256"], row["prompt_sha256"])
        self.assertTrue(result["prompt_source_path"])

    def test_the_run_carries_its_own_identity(self):
        result = self._run()
        self.assertEqual(result["loop"]["loop_type"], "DIGEST")
        self.assertTrue(result["loop"]["run_id"])

    def test_a_resumed_run_keeps_the_original_run_id(self):
        first = self._run()
        state = json.loads((self.root / "cp.json").read_text(encoding="utf-8"))
        state["outcome"] = TaskOutcome.RUNNING.value
        (self.root / "cp.json").write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self._run()["loop"]["run_id"], first["loop"]["run_id"])

    def test_the_report_describes_the_window_without_the_corpus(self):
        result = self._run()
        window = result["window"]
        self.assertEqual(window["days"], 6.0)
        self.assertEqual(window["platforms"], ["youtube"])
        self.assertTrue(window["index_signature"])
        self.assertEqual(sum(window["sources"].values()), len(ITEMS))
        # A skewed window must be visible: two of three items share a source.
        self.assertEqual(window["sources"], {"channel-a": 2, "channel-b": 1})

    def test_provider_time_is_reported_separately_from_wall_clock(self):
        """Wall clock spans an interruption; model time does not."""
        result = self._run()
        self.assertIn("elapsed_seconds", result)
        self.assertIn("invocation_elapsed_seconds", result)
        self.assertIn("run_wall_elapsed_seconds", result)
        totals = result["usage_totals"]
        self.assertEqual(totals["model_latency_seconds"], 2.0 * len(ITEMS))
        self.assertGreater(totals["output_tokens"], 0)
        self.assertIsNotNone(totals["output_tokens_per_second"])
        # Throughput is only meaningful beside the output size it came from.
        self.assertGreater(totals["mean_output_tokens"], 0)

    def test_the_run_is_appended_to_the_shared_run_log(self):
        result = self._run()
        lines = (self.root / "run-log.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["run_id"], result["loop"]["run_id"])
        self.assertEqual(entry["loop_type"], "DIGEST")
        self.assertEqual(entry["output"]["label_counts"], result["label_counts"])
        self.assertIn(str(self.root / "cp.json"), entry["artifact_paths"])


class ResumeAfterEveryFailureTests(unittest.TestCase):
    """No terminal state may force a paid window to be reassessed.

    Enumerating the resumable states by hand missed FAILED_BUDGET: a 328-item
    run tripped its own budget on the final unit, and a re-run would have
    reassessed all 328 items and paid twice. The set is now "anything that is
    not COMPLETED", so a new outcome cannot silently fall outside it.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.checkpoint = Path(self._tmp.name) / "cp.json"
        self.addCleanup(self._tmp.cleanup)

    def _run(self, client, **overrides):
        return run_digest(snapshot=_snapshot(*ITEMS), model="test-model", client=client,
                          spec=overrides.pop("spec", _spec()),
                          checkpoint_path=self.checkpoint, clock=lambda: START, **overrides)

    def test_every_non_completed_outcome_is_resumable(self):
        non_completed = {o.value for o in TaskOutcome} - {TaskOutcome.COMPLETED.value}
        for outcome in sorted(non_completed):
            with self.subTest(outcome=outcome):
                self.checkpoint.write_text(json.dumps({
                    "cache_key": digest_cache_key(_snapshot(*ITEMS), "test-model",
                                                  SIGNIFICANCE_PROMPT_VERSION),
                    "outcome": outcome, "assessments": [], "rejected": [],
                    "started_at": START.isoformat(), "cost_usd": 0.0,
                }), encoding="utf-8")
                client = Client()
                self._run(client)
                self.assertEqual(len(client.seen), len(ITEMS),
                                 f"{outcome} must resume, not be discarded")

    def test_a_budget_stop_resumes_and_finishes_the_remaining_items(self):
        """The exact situation the 30-day run left behind."""
        stopped = self._run(Client(), spec=_spec(max_cost_usd=0.02))
        self.assertEqual(stopped["outcome"], TaskOutcome.FAILED_BUDGET.value)
        done_first = len(stopped["assessments"])
        self.assertLess(done_first, len(ITEMS))

        resumed_client = Client()
        resumed = self._run(resumed_client)
        self.assertEqual(len(resumed_client.seen), len(ITEMS) - done_first,
                         "only the unassessed items are paid for again")
        self.assertEqual(resumed["outcome"], TaskOutcome.COMPLETED.value)
        self.assertEqual(len(resumed["assessments"]), len(ITEMS))


class ResumeClockTests(unittest.TestCase):
    """A digest measures elapsed time per invocation, unlike run_agent_task.

    Inheriting the original start would make a window paused for longer than
    max_minutes permanently unfinishable, stranding every assessment already
    paid for. The task runner deliberately does the opposite, because its rounds
    are one conversation with a deadline rather than a queue of independent
    items. Both sites carry the reason.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.checkpoint = Path(self._tmp.name) / "cp.json"
        self.addCleanup(self._tmp.cleanup)

    def test_a_window_paused_longer_than_the_budget_still_resumes(self):
        much_later = START + timedelta(hours=5)
        self.checkpoint.write_text(json.dumps({
            "cache_key": digest_cache_key(_snapshot(*ITEMS), "test-model",
                                          SIGNIFICANCE_PROMPT_VERSION),
            "outcome": TaskOutcome.RUNNING.value, "assessments": [], "rejected": [],
            "started_at": START.isoformat(), "cost_usd": 0.0,
        }), encoding="utf-8")
        client = Client()
        result = run_digest(snapshot=_snapshot(*ITEMS), model="test-model", client=client,
                            spec=_spec(max_minutes=60), checkpoint_path=self.checkpoint,
                            clock=lambda: much_later)
        self.assertEqual(len(client.seen), len(ITEMS),
                         "five hours later, the queue still runs")
        self.assertEqual(result["outcome"], TaskOutcome.COMPLETED.value)
        self.assertEqual(result["invocation_elapsed_seconds"], 0.0)
        self.assertEqual(result["run_wall_elapsed_seconds"], 5 * 60 * 60)


class LegacyCheckpointRepairTests(unittest.TestCase):
    def test_an_accepted_item_wins_over_its_stale_legacy_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "cp.json"
            snapshot = _snapshot(*ITEMS)
            checkpoint.write_text(json.dumps({
                "cache_key": digest_cache_key(
                    snapshot, "test-model", SIGNIFICANCE_PROMPT_VERSION),
                "outcome": TaskOutcome.ESCALATED_FOR_REVIEW.value,
                "started_at": START.isoformat(),
                "assessments": [{
                    "item_id": "id1", "significance": "SIGNIFICANT",
                    "usage": {"cost_usd": 0.01, "output_tokens": 100,
                              "latency_seconds": 2.0},
                }],
                "rejected": [
                    {"item_id": "id1", "error_type": "ValueError",
                     "error": "old failure", "attempts": 1},
                    {"item_id": "id2", "error_type": "ValueError",
                     "error": "retry me", "attempts": 1},
                ],
                "cost_usd": 0.02,
                "model_calls": 2,
            }), encoding="utf-8")

            client = Client()
            result = run_digest(
                snapshot=snapshot, model="test-model", client=client,
                spec=_spec(), checkpoint_path=checkpoint, clock=lambda: START)

            self.assertEqual(client.seen, ["id2", "id3"])
            self.assertEqual(result["outcome"], TaskOutcome.COMPLETED.value)
            self.assertEqual(result["rejected"], [])
            self.assertEqual(result["legacy_rejections_cleared"], 1)
            self.assertFalse(result["provider_calls_exact"])
            self.assertGreaterEqual(result["provider_calls"], 4)
