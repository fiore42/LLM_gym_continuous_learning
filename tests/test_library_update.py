import subprocess
import tempfile
import unittest
from pathlib import Path

from llm_gym.corpus.library_update import run_library_update


class LibraryUpdateTests(unittest.TestCase):
    def test_ingestion_runs_before_index_and_checkpoint_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            calls = []

            def fake_run(command, **kwargs):
                calls.append((command, kwargs))
                return subprocess.CompletedProcess(command, 0)

            result = run_library_update(project_root=root, run_command=fake_run)
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["completed_stages"], ["ingest", "index", "checkpoint"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1]["cwd"], root)
            self.assertTrue((root / "data" / "evidence.sqlite3").is_file())
            self.assertTrue((root / "data" / "library-update.json").is_file())

    def test_failed_ingestion_still_indexes_successful_local_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def fake_run(command, **kwargs):
                return subprocess.CompletedProcess(command, 1)

            result = run_library_update(project_root=root, run_command=fake_run)
            self.assertEqual(result["status"], "COMPLETED_WITH_FAILURES")
            self.assertEqual(result["ingestion_exit_code"], 1)
