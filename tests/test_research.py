import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from llm_gym.corpus.evidence import build_index, collect_records
from llm_gym.agent.research import run_research


class ResearchLoopTests(unittest.TestCase):
    def _index(self, root: Path) -> Path:
        post = root / "x" / "alice" / "posts" / "20260801_post1"
        post.mkdir(parents=True)
        (post / "post.json").write_text(json.dumps({"id": "post1", "created_at": "2026-08-01T00:00:00Z", "text": "agents need memory"}), encoding="utf-8")
        index = root / "evidence.sqlite3"
        build_index(collect_records(root)[0], index)
        return index

    def test_retrieves_citations_and_resumes_same_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = self._index(root)
            checkpoint = root / "checkpoint.json"
            first = run_research("agents memory", index_path=index, checkpoint_path=checkpoint)
            second = run_research("agents memory", index_path=index, checkpoint_path=checkpoint)
            self.assertEqual(first["classification"], "SUPPORTED")
            self.assertEqual(first["completed_stages"], ["retrieve", "cite", "classify", "checkpoint"])
            self.assertEqual(first, second)
            self.assertTrue(first["evidence"][0]["canonical_url"].startswith("https://x.com/"))
            self.assertEqual(first["retrieval"]["scope"], "supplied retrieved evidence")
            self.assertEqual(first["retrieval"]["returned_count"], 1)
            self.assertFalse(first["retrieval"]["truncated"])

    def test_empty_result_is_explicitly_insufficient(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "evidence.sqlite3"
            sqlite3.connect(index).close()
            result = run_research("topic absent", index_path=index, checkpoint_path=root / "checkpoint.json")
            self.assertEqual(result["classification"], "INSUFFICIENT_EVIDENCE")
            self.assertEqual(result["evidence"], [])

    def test_index_change_invalidates_checkpoint_without_force(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = self._index(root)
            checkpoint = root / "checkpoint.json"
            first = run_research("agents memory", index_path=index, checkpoint_path=checkpoint)
            connection = sqlite3.connect(index)
            connection.execute("UPDATE evidence_items SET indexed_at = 'changed'")
            connection.commit()
            connection.close()
            second = run_research("agents memory", index_path=index, checkpoint_path=checkpoint)
            self.assertNotEqual(first["created_at"], second["created_at"])
            self.assertEqual(first["retrieval"]["index_version"], second["retrieval"]["index_version"])
            self.assertNotEqual(first["retrieval"]["index_signature"], second["retrieval"]["index_signature"])


class RetrievalBreadthTests(unittest.TestCase):
    """Breadth changes what was retrieved, so it belongs in the reuse test.

    Asking for eight items returned a cached three-item checkpoint and reported
    limit=3, silently ignoring the request. Rule 30: a guard protects only the
    fields it names.
    """

    def test_a_larger_limit_is_not_served_from_a_narrower_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            narrow = run_research("How do agents use memory?",
                                  checkpoint_path=checkpoint, limit=3)
            wide = run_research("How do agents use memory?",
                               checkpoint_path=checkpoint, limit=8)
            self.assertEqual(narrow["retrieval"]["limit"], 3)
            self.assertEqual(wide["retrieval"]["limit"], 8)
            self.assertNotEqual(narrow["run_id"], wide["run_id"],
                                "a different breadth is a different retrieval")

    def test_an_identical_request_is_still_served_from_the_checkpoint(self):
        """The fix must not defeat resume for the case it was built for."""
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            first = run_research("How do agents use memory?",
                                 checkpoint_path=checkpoint, limit=3)
            again = run_research("How do agents use memory?",
                                 checkpoint_path=checkpoint, limit=3)
            self.assertEqual(first["run_id"], again["run_id"])
