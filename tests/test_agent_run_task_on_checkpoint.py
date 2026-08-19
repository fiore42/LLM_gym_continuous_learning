import json
import tempfile
import unittest
from pathlib import Path

from scripts.agent_run_task_on_checkpoint import run_from_checkpoint


CHECKPOINT = {
    "question": "How do agents use memory?",
    "evidence": [
        {
            "evidence_id": "e1",
            "canonical_url": "https://example.test/1",
            "title": "Memory talk",
            "locator": "00:01:00-00:01:10",
            "artifact_path": "/tmp/example.srt",
            "snippet": "Agents keep prior context so later steps can use it.",
        },
        {
            "evidence_id": "e2",
            "canonical_url": "https://example.test/2",
            "title": None,
            "locator": None,
            "artifact_path": "/tmp/example.json",
            "snippet": "A second source describing retrieval alongside memory.",
        },
    ],
}

ANSWER = json.dumps({
    "answer": "The retrieved evidence describes agents keeping prior context.",
    "classification": "SUPPORTED",
    "citation_ids": ["e1", "e2"],
    "evidence_assessment": [
        {"evidence_id": "e1", "relevant": True, "reason": "states context is kept"},
        {"evidence_id": "e2", "relevant": True, "reason": "pairs retrieval with memory"},
    ],
})


class RecordingClient:
    """Offline stand-in for a provider; records what it was asked."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.last_kwargs = None
        self.last_usage = {}

    def complete(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return self.responses.pop(0)


class RunFromCheckpointTests(unittest.TestCase):
    def _checkpoint(self, root: Path) -> Path:
        path = root / "research-checkpoint.json"
        path.write_text(json.dumps(CHECKPOINT), encoding="utf-8")
        return path

    def test_runs_offline_and_writes_reviewable_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = RecordingClient([ANSWER])
            payload = run_from_checkpoint(
                checkpoint_path=self._checkpoint(root),
                output_path=root / "answer.json",
                cache_path=root / "cache.json",
                model="test-model",
                client=client,
            )
            self.assertEqual(payload["outcome"], "COMPLETED")
            self.assertEqual(client.calls, 1)
            # The reviewer must see the same bounded evidence the model saw.
            self.assertEqual(
                [item["evidence_id"] for item in payload["retrieved_evidence"]], ["e1", "e2"]
            )
            self.assertEqual(payload["source_checkpoint"], str(self._checkpoint(root)))
            saved = json.loads((root / "answer.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["outcome"], "COMPLETED")
            self.assertIn("retrieved_evidence", saved)

    def test_task_id_is_derived_from_the_question_when_not_supplied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = run_from_checkpoint(
                checkpoint_path=self._checkpoint(root),
                output_path=root / "answer.json",
                cache_path=root / "cache.json",
                model="test-model",
                client=RecordingClient([ANSWER]),
            )
            self.assertTrue(payload["task_id"].startswith("research-"))

            explicit = run_from_checkpoint(
                checkpoint_path=self._checkpoint(root),
                output_path=root / "answer2.json",
                cache_path=root / "cache2.json",
                model="test-model",
                task_id="chosen-id",
                client=RecordingClient([ANSWER]),
            )
            self.assertEqual(explicit["task_id"], "chosen-id")

    def test_only_checkpoint_evidence_reaches_the_model(self):
        """The closed-book contract: the prompt carries the supplied snippets."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = RecordingClient([ANSWER])
            run_from_checkpoint(
                checkpoint_path=self._checkpoint(root),
                output_path=root / "answer.json",
                cache_path=root / "cache.json",
                model="test-model",
                client=client,
            )
            sent = client.last_kwargs["user"]
            self.assertIn("Agents keep prior context", sent)
            self.assertIn("e1", sent)
            self.assertIn("How do agents use memory?", sent)


if __name__ == "__main__":
    unittest.main()
