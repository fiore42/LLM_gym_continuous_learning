import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.eval_build_benchmark_from_corpus import build_cases


class CorpusBenchmarkTests(unittest.TestCase):
    def test_requires_human_expected_outcome(self):
        with self.assertRaisesRegex(ValueError, "expected_outcome"):
            build_cases([{"case_id": "one", "question": "What happened?"}], "index", 3)

    @patch("scripts.eval_build_benchmark_from_corpus.search_index")
    def test_preserves_corpus_evidence_and_label(self, search):
        search.return_value = [{
            "evidence_id": "real-evidence",
            "canonical_url": "https://example.test/source",
            "published_at": "2026-08-01T00:00:00Z",
            "title": "A source",
            "locator": "00:01–00:02",
            "snippet": "Grounded evidence",
            "artifact_path": "/private/source",
        }, {
            "evidence_id": "other-evidence",
            "canonical_url": "https://example.test/other",
            "published_at": None,
            "title": None,
            "locator": None,
            "snippet": "Other evidence",
        }]
        cases = build_cases([{
            "case_id": "grounded",
            "question": "What happened?",
            "expected_outcome": "supported",
            "required_citation_ids": ["real-evidence"],
            "forbidden_citation_ids": ["other-evidence"],
        }], "index", 3)
        self.assertEqual(cases[0]["expected_outcome"], "SUPPORTED")
        self.assertEqual(cases[0]["evidence"][0]["evidence_id"], "real-evidence")
        self.assertEqual(cases[0]["required_citation_ids"], ["real-evidence"])
        self.assertEqual(cases[0]["forbidden_citation_ids"], ["other-evidence"])
        self.assertNotIn("artifact_path", cases[0]["evidence"][0])


if __name__ == "__main__":
    unittest.main()
