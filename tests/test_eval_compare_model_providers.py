import json
import tempfile
import unittest
from pathlib import Path

from scripts.eval_compare_model_providers import validate_benchmark_source


class ModelComparisonCliTests(unittest.TestCase):
    def _write(self, directory: str, payload: dict) -> Path:
        path = Path(directory) / "benchmark.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_rejects_unmarked_synthetic_benchmark(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "corpus-grounded"):
                validate_benchmark_source(self._write(directory, {"cases": []}))

    def test_accepts_corpus_benchmark(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, {"source": "local_evidence_index", "cases": []})
            self.assertEqual(validate_benchmark_source(path), "local_evidence_index")

    def test_allows_synthetic_only_when_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, {"source": "synthetic", "cases": []})
            self.assertEqual(validate_benchmark_source(path, allow_synthetic=True), "synthetic")


if __name__ == "__main__":
    unittest.main()
