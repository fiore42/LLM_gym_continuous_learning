import tempfile
import unittest
from pathlib import Path

from llm_gym.shared.atomic import atomic_write_text


class AtomicWriteTests(unittest.TestCase):
    def test_replaces_file_and_leaves_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "report.json"
            atomic_write_text(path, "first")
            atomic_write_text(path, "second")
            self.assertEqual(path.read_text(encoding="utf-8"), "second")
            self.assertEqual(list(path.parent.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
