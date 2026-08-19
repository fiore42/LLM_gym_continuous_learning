import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from llm_gym.corpus.evidence import build_index, collect_records, index_signature, search_index, search_index_with_metadata


class EvidenceIndexTests(unittest.TestCase):
    def test_index_signature_changes_when_index_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "evidence.sqlite3"
            index.write_bytes(b"initial")
            first = index_signature(index)
            index.write_bytes(b"changed")
            second = index_signature(index)
            self.assertNotEqual(first, second)

    def test_collects_youtube_transcript_and_x_post(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            yt = root / "youtube" / "demo"
            yt.mkdir(parents=True)
            transcript = root / "youtube" / "demo" / "transcript.srt"
            transcript.write_text("00:00:00,000 --> 00:00:01,000\nagent memory\n", encoding="utf-8")
            with closing(sqlite3.connect(yt / "ingestion-state.sqlite3")) as db:
                db.execute("CREATE TABLE videos (video_id TEXT, canonical_url TEXT, title TEXT, published_at TEXT, status TEXT, transcript_path TEXT)")
                db.execute("INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?)", ("vid1", "https://youtube.com/watch?v=vid1", "Demo", "2026-08-01T00:00:00+00:00", "COMPLETED", str(transcript)))
                db.commit()
            post = root / "x" / "alice" / "posts" / "20260801_post1"
            post.mkdir(parents=True)
            (post / "post.json").write_text(json.dumps({"id": "post1", "created_at": "2026-08-01T00:00:00Z", "text": "agent memory on X"}), encoding="utf-8")
            records, warnings = collect_records(root)
            self.assertEqual(len(records), 2)
            self.assertFalse(warnings)
            index = root / "evidence.sqlite3"
            self.assertEqual(build_index(records, index)["inserted"], 2)
            self.assertGreater(build_index(records, index)["chunks"], 0)
            self.assertEqual(build_index(records, index)["reused"], 2)
            hits = search_index("How do agents use memory?", index)
            self.assertEqual(len(hits), 2)
            self.assertTrue(all(item["canonical_url"] for item in hits))
            metadata = search_index_with_metadata("How do agents use memory?", index, limit=1)
            self.assertEqual(metadata["returned_count"], 1)
            self.assertEqual(metadata["matched_evidence_count"], 2)
            self.assertTrue(metadata["truncated"])

    def test_srt_search_returns_timestamp_locator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "youtube" / "demo" / "t.srt"
            transcript.parent.mkdir(parents=True)
            transcript.write_text("1\n00:01:02,000 --> 00:01:03,000\nMemory is persisted.\n", encoding="utf-8")
            with closing(sqlite3.connect(root / "youtube" / "demo" / "ingestion-state.sqlite3")) as db:
                db.execute("CREATE TABLE videos (video_id TEXT, canonical_url TEXT, title TEXT, published_at TEXT, status TEXT, transcript_path TEXT)")
                db.execute("INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?)", ("v", "https://youtube.com/watch?v=v", "Demo", "2026-08-01", "COMPLETED", str(transcript)))
                db.commit()
            index = root / "evidence.sqlite3"
            build_index(collect_records(root)[0], index)
            self.assertEqual(search_index("persisted", index)[0]["locator"], "00:01:02.000–00:01:03.000")

    def test_transcript_search_returns_bounded_context_preserving_negation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "youtube" / "demo" / "t.srt"
            transcript.parent.mkdir(parents=True)
            transcript_text = (
                "1\n"
                "00:00:00,000 --> 00:00:01,000\n"
                "And so, the interesting work is no longer making the model more reliable.\n"
                "\n"
                "2\n"
                "00:00:01,000 --> 00:00:02,000\n"
                "The interesting work is what you put on the other side of your agent front door.\n"
            )
            transcript.write_text(transcript_text, encoding="utf-8")
            with closing(sqlite3.connect(root / "youtube" / "demo" / "ingestion-state.sqlite3")) as db:
                db.execute("CREATE TABLE videos (video_id TEXT, canonical_url TEXT, title TEXT, published_at TEXT, status TEXT, transcript_path TEXT)")
                db.execute("INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?)", ("v", "https://youtube.com/watch?v=v", "Demo", "2026-08-01", "COMPLETED", str(transcript)))
                db.commit()
            index = root / "evidence.sqlite3"
            build_index(collect_records(root)[0], index)
            hit = search_index("front door", index)[0]
            self.assertNotIn("00:00:00,000", hit["snippet"])
            self.assertLess(len(hit["snippet"]), 2400)
            self.assertIn("no longer making the model more reliable", hit["snippet"])

    def test_transcript_search_reconstructs_sentence_across_subtitle_cues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "youtube" / "demo" / "t.srt"
            transcript.parent.mkdir(parents=True)
            transcript.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n"
                "Reliable workflows need\n\n"
                "2\n00:00:01,000 --> 00:00:02,000\n"
                "explicit stopping rules and\n\n"
                "3\n00:00:02,000 --> 00:00:03,000\n"
                "human escalation.\n\n"
                "4\n00:00:03,000 --> 00:00:04,000\n"
                "Unrelated later material.\n", encoding="utf-8")
            with closing(sqlite3.connect(root / "youtube" / "demo" / "ingestion-state.sqlite3")) as db:
                db.execute("CREATE TABLE videos (video_id TEXT, canonical_url TEXT, title TEXT, published_at TEXT, status TEXT, transcript_path TEXT)")
                db.execute("INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?)", ("v", "https://youtube.com/watch?v=v", "Demo", "2026-08-01", "COMPLETED", str(transcript)))
                db.commit()
            index = root / "evidence.sqlite3"
            build_index(collect_records(root)[0], index)
            hit = search_index("stopping rules", index)[0]
            self.assertIn("Reliable workflows need explicit stopping rules and human escalation.", hit["snippet"])
            self.assertNotIn("Unrelated later material", hit["snippet"])

    def test_fts_uses_deterministic_stemming_and_ignores_stopwords(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            post = root / "x" / "alice" / "posts" / "20260801_post1"
            post.mkdir(parents=True)
            (post / "post.json").write_text(json.dumps({
                "id": "post1", "text": "Reliable evaluation makes systems easier to inspect."
            }), encoding="utf-8")
            index = root / "evidence.sqlite3"
            build_index(collect_records(root)[0], index)
            self.assertTrue(search_index("reliability", index))
            self.assertTrue(search_index("evaluate", index))
            self.assertEqual(search_index("the and an", index), [])

    def test_context_joins_distant_keyword_matches_with_ellipsis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "youtube" / "demo" / "t.srt"
            transcript.parent.mkdir(parents=True)
            transcript.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nReliability matters.\n\n"
                "2\n00:00:01,000 --> 00:00:02,000\nUnrelated words here.\n\n"
                "3\n00:00:02,000 --> 00:00:03,000\nMore unrelated words.\n\n"
                "4\n00:00:03,000 --> 00:00:04,000\nStill unrelated words.\n\n"
                "5\n00:00:04,000 --> 00:00:05,000\nEvaluation exposes failures.\n", encoding="utf-8")
            with closing(sqlite3.connect(root / "youtube" / "demo" / "ingestion-state.sqlite3")) as db:
                db.execute("CREATE TABLE videos (video_id TEXT, canonical_url TEXT, title TEXT, published_at TEXT, status TEXT, transcript_path TEXT)")
                db.execute("INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?)", ("v", "https://youtube.com/watch?v=v", "Demo", "2026-08-01", "COMPLETED", str(transcript)))
                db.commit()
            index = root / "evidence.sqlite3"
            build_index(collect_records(root)[0], index)
            hit = search_index("reliability evaluation", index)[0]
            self.assertIn("Reliability matters.", hit["snippet"])
            self.assertIn("Evaluation exposes failures.", hit["snippet"])
            self.assertIn("[…]", hit["snippet"])

    def test_binary_documents_are_reported_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            post = Path(directory) / "x" / "alice" / "posts" / "20260801_post1"
            (post / "documents").mkdir(parents=True)
            (post / "post.json").write_text(json.dumps({"id": "post1", "text": "hello"}), encoding="utf-8")
            (post / "documents" / "brief.pdf").write_bytes(b"not parsed")
            records, warnings = collect_records(Path(directory))
            self.assertEqual(len(records), 1)
            self.assertTrue(any("UNEXTRACTED_DOCUMENT" in warning for warning in warnings))
