import unittest
from datetime import datetime, timezone

from scripts.corpus_freeze_digest_window import parse_instant, snapshot_output_path


class InstantParsingTests(unittest.TestCase):
    def test_a_bare_date_is_read_as_utc_midnight(self):
        """A naive value must not pick up the machine's local zone."""
        self.assertEqual(parse_instant("2026-08-07"),
                         datetime(2026, 8, 7, tzinfo=timezone.utc))

    def test_an_explicit_offset_is_preserved(self):
        self.assertEqual(parse_instant("2026-08-06T16:30:00+01:00"),
                         datetime(2026, 8, 6, 15, 30, tzinfo=timezone.utc))


class SnapshotPathTests(unittest.TestCase):
    def test_each_window_gets_its_own_snapshot_path(self):
        a = snapshot_output_path(datetime(2026, 7, 31, tzinfo=timezone.utc),
                                 datetime(2026, 8, 7, tzinfo=timezone.utc), ("youtube",))
        b = snapshot_output_path(datetime(2026, 7, 8, tzinfo=timezone.utc),
                                 datetime(2026, 8, 7, tzinfo=timezone.utc), ("youtube",))
        c = snapshot_output_path(datetime(2026, 7, 31, tzinfo=timezone.utc),
                                 datetime(2026, 8, 7, tzinfo=timezone.utc), ())
        self.assertEqual(len({a, b, c}), 3)
        self.assertIn("youtube", a)
        # An unscoped window is labelled, not left blank.
        self.assertIn("all", c)

    def test_a_path_is_a_usable_fragment(self):
        path = snapshot_output_path(datetime(2026, 7, 31, tzinfo=timezone.utc),
                                    datetime(2026, 8, 7, tzinfo=timezone.utc), ("youtube",))
        self.assertTrue(path.startswith("data/digest-windows/"))
        self.assertNotIn("/", path[len("data/digest-windows/"):])


if __name__ == "__main__":
    unittest.main()
