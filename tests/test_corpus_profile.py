import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from llm_gym.corpus.corpus_profile import profile_corpus, write_profile


class CorpusProfileTests(unittest.TestCase):
    def test_profiles_state_and_excludes_media_and_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            state_path = root / "youtube/example/ingestion-state.sqlite3"
            state_path.parent.mkdir(parents=True)
            with closing(sqlite3.connect(state_path)) as connection:
                connection.execute("CREATE TABLE videos(status TEXT, transcript_path TEXT)")
                connection.executemany("INSERT INTO videos VALUES (?, ?)", [("COMPLETED", "x.srt"), ("FAILED_TRANSCRIPTION", None)])
                connection.commit()
            (root / "youtube/example/transcripts").mkdir(parents=True)
            (root / "youtube/example/transcripts/x.srt").write_text("speech", encoding="utf-8")
            (root / "youtube/example/audio").mkdir(parents=True)
            (root / "youtube/example/audio/x.m4a").write_bytes(b"audio")
            (root / "youtube/example/logs").mkdir(parents=True)
            (root / "youtube/example/logs/run.jsonl").write_text("{}", encoding="utf-8")

            profile = profile_corpus(root)
            self.assertEqual(profile["total_items"], 2)
            self.assertEqual(profile["status_counts"], {"COMPLETED": 1, "FAILED_TRANSCRIPTION": 1})
            self.assertNotIn(".m4a", profile["artifact_extension_counts"])
            self.assertNotIn(".jsonl", profile["artifact_extension_counts"])
            output = Path(directory) / "profile.json"
            write_profile(profile, output)
            self.assertEqual(json.loads(output.read_text())["profile_version"], 1)


if __name__ == "__main__":
    unittest.main()
