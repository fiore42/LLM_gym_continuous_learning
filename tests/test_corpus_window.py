import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from llm_gym.corpus.window import (attach_item_text, deoverlap_captions,
                                   exclude_non_substantive_items, freeze_window,
                                   item_text, load_snapshot, normalise_timestamp,
                                   select_window, source_text_is_substantive)

UNTIL = datetime(2026, 8, 7, tzinfo=timezone.utc)
SINCE = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _index(path: Path, rows: list[tuple[str, str, str | None]]) -> None:
    """Build a minimal evidence index: (evidence_id, platform, published_at)."""
    connection = sqlite3.connect(path)
    connection.execute("""
        CREATE TABLE evidence_items (
            evidence_id TEXT PRIMARY KEY, platform TEXT NOT NULL, source_key TEXT,
            canonical_url TEXT, published_at TEXT, title TEXT, author TEXT, kind TEXT)
    """)
    connection.executemany(
        "INSERT INTO evidence_items (evidence_id, platform, source_key, canonical_url,"
        " published_at, title, author, kind) VALUES (?,?,'s','https://e.test',?,'t','a','k')",
        rows)
    connection.commit()
    connection.close()


class TimestampNormalisationTests(unittest.TestCase):
    """The corpus stores one instant in two formats, so compare parsed values."""

    def test_both_stored_formats_resolve_to_the_same_instant(self):
        offset = normalise_timestamp("2026-08-06T15:30:00+00:00")
        zulu = normalise_timestamp("2026-08-06T15:30:00.000Z")
        self.assertEqual(offset, zulu)
        # String comparison would have ordered these two apart.
        self.assertNotEqual("2026-08-06T15:30:00+00:00", "2026-08-06T15:30:00.000Z")

    def test_a_naive_timestamp_is_read_as_utc(self):
        """Guessing a local zone would move items across the boundary."""
        self.assertEqual(normalise_timestamp("2026-08-06T15:30:00"),
                         datetime(2026, 8, 6, 15, 30, tzinfo=timezone.utc))

    def test_an_unusable_value_returns_none_rather_than_raising(self):
        for value in (None, "", "   ", "not-a-date"):
            with self.subTest(value=value):
                self.assertIsNone(normalise_timestamp(value))


class WindowSelectionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.index = Path(self._tmp.name) / "evidence.sqlite3"
        self.addCleanup(self._tmp.cleanup)

    def test_the_window_is_half_open_so_consecutive_windows_tile(self):
        """An item on the boundary belongs to exactly one of two windows."""
        _index(self.index, [
            ("at-since", "youtube", "2026-08-01T00:00:00+00:00"),
            ("inside", "youtube", "2026-08-03T12:00:00.000Z"),
            ("at-until", "youtube", "2026-08-07T00:00:00+00:00"),
            ("before", "youtube", "2026-07-31T23:59:59+00:00"),
        ])
        selection = select_window(self.index, since=SINCE, until=UNTIL)
        self.assertEqual([item["evidence_id"] for item in selection.items],
                         ["at-since", "inside"])

    def test_a_non_utc_offset_is_compared_by_instant_not_by_its_text(self):
        """The reason this module parses before comparing.

        16:30+01:00 is 15:30Z, which falls before a window starting at 16:00Z —
        but as text it sorts after "16:00:00+00:00" and a string comparison
        selects it. The two stored UTC spellings happen to sort correctly, so
        only a non-UTC offset exposes the difference.
        """
        _index(self.index, [("earlier-than-it-looks", "youtube", "2026-08-06T16:30:00+01:00")])
        selection = select_window(
            self.index, since=datetime(2026, 8, 6, 16, tzinfo=timezone.utc), until=UNTIL)
        self.assertEqual(selection.selected, 0)
        self.assertEqual(selection.considered, 1)

    def test_ties_are_broken_by_evidence_id_so_order_cannot_drift(self):
        """A resumed digest must continue at the same position."""
        same = "2026-08-03T12:00:00+00:00"
        _index(self.index, [("c", "youtube", same), ("a", "youtube", same),
                            ("b", "youtube", same)])
        first = select_window(self.index, since=SINCE, until=UNTIL)
        second = select_window(self.index, since=SINCE, until=UNTIL)
        self.assertEqual([item["evidence_id"] for item in first.items], ["a", "b", "c"])
        self.assertEqual([item["evidence_id"] for item in first.items],
                         [item["evidence_id"] for item in second.items])

    def test_platform_filter_narrows_what_was_considered_not_only_selected(self):
        """Considered is the denominator; filtering must move it too."""
        _index(self.index, [("v", "youtube", "2026-08-03T00:00:00+00:00"),
                            ("p", "x", "2026-08-03T00:00:00+00:00")])
        everything = select_window(self.index, since=SINCE, until=UNTIL)
        youtube = select_window(self.index, since=SINCE, until=UNTIL, platforms=("YouTube",))
        self.assertEqual((everything.considered, everything.selected), (2, 2))
        self.assertEqual((youtube.considered, youtube.selected), (1, 1))

    def test_an_unusable_timestamp_is_counted_rather_than_dropped_silently(self):
        _index(self.index, [("good", "youtube", "2026-08-03T00:00:00+00:00"),
                            ("bad", "youtube", "never"),
                            ("empty", "youtube", None)])
        selection = select_window(self.index, since=SINCE, until=UNTIL)
        self.assertEqual(selection.selected, 1)
        self.assertEqual(selection.considered, 3)
        self.assertEqual(selection.unparseable_published_at, 2)

    def test_an_inverted_window_is_rejected_before_any_query(self):
        _index(self.index, [("v", "youtube", "2026-08-03T00:00:00+00:00")])
        with self.assertRaisesRegex(ValueError, "until must be after since"):
            select_window(self.index, since=UNTIL, until=SINCE)

    def test_selection_records_the_index_it_was_taken_from(self):
        _index(self.index, [("v", "youtube", "2026-08-03T00:00:00+00:00")])
        selection = select_window(self.index, since=SINCE, until=UNTIL)
        self.assertTrue(selection.index_signature)
        self.assertNotEqual(selection.index_signature, "missing")

    def test_placeholder_only_transcripts_are_excluded_before_freezing(self):
        _index(self.index, [
            ("placeholder", "youtube", "2026-08-03T00:00:00+00:00"),
            ("substantive", "youtube", "2026-08-04T00:00:00+00:00"),
        ])
        connection = sqlite3.connect(self.index)
        connection.execute(
            "CREATE TABLE evidence_chunks (evidence_id TEXT, chunk_index INTEGER, text TEXT)")
        connection.executemany(
            "INSERT INTO evidence_chunks VALUES (?,?,?)",
            [("placeholder", 0, "[MUSIC PLAYING]"),
             ("substantive", 0, "Agents resume from checkpoints.")],
        )
        connection.commit()
        connection.close()

        selection = select_window(self.index, since=SINCE, until=UNTIL)
        filtered = exclude_non_substantive_items(self.index, selection)

        self.assertEqual([item["evidence_id"] for item in filtered.items], ["substantive"])
        self.assertEqual(filtered.excluded_non_substantive, 1)

    def test_short_substantive_text_is_not_removed_by_a_length_threshold(self):
        self.assertFalse(source_text_is_substantive("[MUSIC PLAYING]"))
        self.assertFalse(source_text_is_substantive("[Applause] [Music]"))
        self.assertTrue(source_text_is_substantive("AI works."))


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.index = self.root / "evidence.sqlite3"
        _index(self.index, [("v", "youtube", "2026-08-03T00:00:00+00:00"),
                            ("p", "x", "2026-08-04T00:00:00+00:00")])
        self.addCleanup(self._tmp.cleanup)

    def test_a_frozen_window_round_trips_with_its_provenance(self):
        selection = select_window(self.index, since=SINCE, until=UNTIL,
                                  platforms=("youtube",))
        path = self.root / "window.json"
        freeze_window(selection, path)
        snapshot = load_snapshot(path)
        self.assertEqual(snapshot["selected"], 1)
        self.assertEqual(snapshot["considered"], 1)
        self.assertEqual(snapshot["excluded_non_substantive"], 0)
        self.assertEqual(snapshot["platforms"], ["youtube"])
        self.assertEqual(snapshot["index_signature"], selection.index_signature)
        self.assertEqual(snapshot["since"], selection.since)
        self.assertEqual([item["evidence_id"] for item in snapshot["items"]], ["v"])

    def test_an_unversioned_snapshot_is_rejected(self):
        """A snapshot whose shape changed must not be read as if it had not."""
        path = self.root / "stale.json"
        path.write_text('{"items": [], "selected": 0}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported window snapshot"):
            load_snapshot(path)


if __name__ == "__main__":
    unittest.main()


class CaptionDeoverlapTests(unittest.TestCase):
    """Rolling captions restate each line as the next scrolls in.

    Measured on a real 30-minute item: 107,682 characters of stored text
    reduces to 22,047, so four fifths was duplication. Left in place it is paid
    for on every digest call, and a model asked to quote verbatim quotes the
    spoken sentence, which does not exist contiguously in the raw text — so
    every grounded-quote check would fail on formatting rather than honesty.
    """

    def test_a_rolling_caption_becomes_the_sentence_once(self):
        chunks = ["You and I both know", "You and I both know that the AI space",
                  "that the AI space is moving fast"]
        self.assertEqual(deoverlap_captions(chunks),
                         "You and I both know that the AI space is moving fast")

    def test_an_exact_repeat_adds_nothing(self):
        self.assertEqual(deoverlap_captions(["same line", "same line", "same line"]),
                         "same line")

    def test_unrelated_lines_are_both_kept(self):
        self.assertEqual(deoverlap_captions(["first thought.", "second thought."]),
                         "first thought. second thought.")

    def test_blank_and_whitespace_chunks_are_dropped(self):
        self.assertEqual(deoverlap_captions(["hello", "", "   ", None, "world"]),
                         "hello world")

    def test_the_result_is_quotable_as_contiguous_prose(self):
        """The property the grounded-quote check depends on."""
        chunks = ["The router cut", "The router cut p95 latency",
                  "p95 latency from 800ms to 120ms"]
        prose = deoverlap_captions(chunks)
        self.assertIn("The router cut p95 latency from 800ms to 120ms", prose)


class ItemTextTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.index = Path(self._tmp.name) / "evidence.sqlite3"
        connection = sqlite3.connect(self.index)
        connection.execute("CREATE TABLE evidence_chunks (chunk_id TEXT, evidence_id TEXT,"
                           " chunk_index INTEGER, locator TEXT, text TEXT)")
        connection.executemany(
            "INSERT INTO evidence_chunks VALUES (?,?,?,?,?)",
            # chunk_id deliberately sorts differently from chunk_index, so
            # ordering by the wrong column changes the assembled text.
            [("zeta", "v1", 2, "t", "batching raised throughput"),
             ("mid", "v1", 1, "t", "We tried batching"),
             ("alpha", "v1", 3, "t", "raised throughput by forty percent"),
             ("other-1", "other", 1, "t", "a different item entirely")])
        connection.commit()
        connection.close()
        self.addCleanup(self._tmp.cleanup)

    def test_chunks_are_assembled_in_index_order_not_insertion_order(self):
        self.assertEqual(item_text(self.index, "v1"),
                         "We tried batching raised throughput by forty percent")

    def test_only_the_requested_item_contributes(self):
        self.assertNotIn("different item", item_text(self.index, "v1"))

    def test_attaching_text_preserves_the_selection_metadata(self):
        items = [{"evidence_id": "v1", "title": "kept"}]
        attached = attach_item_text(self.index, items)
        self.assertEqual(attached[0]["title"], "kept")
        self.assertIn("batching", attached[0]["text"])
