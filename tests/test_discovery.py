import json
import unittest
from datetime import date, datetime, timezone
from subprocess import CompletedProcess

from llm_gym.sources.discovery import discover_channel_videos


class DiscoveryTests(unittest.TestCase):
    def test_filters_sorts_and_preserves_urls(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            if "--no-playlist" in command:
                return CompletedProcess(
                    command,
                    0,
                    json.dumps({"id": "unknown", "title": "Unknown", "upload_date": "20260804"}),
                    "",
                )
            payload = {
                "entries": [
                    {"id": "new", "title": "New", "upload_date": "20260805"},
                    {"id": "unknown", "title": "Unknown"},
                    {"id": "old", "title": "Old", "upload_date": "20260803"},
                    {"id": "outside", "title": "Outside", "upload_date": "20260801"},
                ]
            }
            return CompletedProcess(command, 0, json.dumps(payload), "")

        result = discover_channel_videos(
            "https://www.youtube.com/@example",
            window_days=3,
            as_of=date(2026, 8, 6),
            runner=runner,
        )

        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual([video.video_id for video in result.videos], ["old", "unknown", "new"])
        self.assertEqual(result.skipped_without_date, 0)
        self.assertEqual(
            result.videos[0].canonical_url,
            "https://www.youtube.com/watch?v=old",
        )
        self.assertIn("--flat-playlist", calls[0])
        self.assertIn("--skip-download", calls[0])
        self.assertIn("--dateafter", calls[0])
        self.assertIn("/videos", calls[0][-1])
        self.assertTrue(any("--no-playlist" in call for call in calls[1:]))

    def test_newest_first(self):
        def runner(command, **kwargs):
            payload = {
                "entries": [
                    {"id": "a", "upload_date": "20260804"},
                    {"id": "b", "upload_date": "20260805"},
                ]
            }
            return CompletedProcess(command, 0, json.dumps(payload), "")

        result = discover_channel_videos(
            "https://www.youtube.com/@example",
            as_of=date(2026, 8, 6),
            order="newest_first",
            runner=runner,
        )

        self.assertEqual([video.video_id for video in result.videos], ["b", "a"])

    def test_window_is_hard_limited_to_3_days(self):
        with self.assertRaises(ValueError):
            discover_channel_videos("https://www.youtube.com/@example", window_days=8)

    def test_explicit_all_history_bypasses_cutoff_without_changing_defaults(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return CompletedProcess(command, 0, json.dumps({"entries": [
                {"id": "old", "upload_date": "20200101"},
                {"id": "recent", "upload_date": "20260805"},
            ]}), "")

        result = discover_channel_videos(
            "https://www.youtube.com/@example",
            all_history=True,
            as_of=date(2026, 8, 6),
            runner=runner,
        )

        self.assertEqual([video.video_id for video in result.videos], ["old", "recent"])
        self.assertEqual(result.window_days, 0)
        self.assertNotIn("--dateafter", calls[0])

    def test_since_and_until_define_incremental_window(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return CompletedProcess(
                command,
                0,
                json.dumps({
                    "entries": [
                        {"id": "after", "upload_date": "20260807"},
                        {"id": "inside", "upload_date": "20260804"},
                        {"id": "before", "upload_date": "20260802"},
                    ]
                }),
                "",
            )

        result = discover_channel_videos(
            "https://www.youtube.com/@example",
            since=datetime(2026, 8, 1, tzinfo=timezone.utc),
            until=datetime(2026, 8, 6, tzinfo=timezone.utc),
            runner=runner,
        )

        self.assertEqual([video.video_id for video in result.videos], ["inside"])
        self.assertEqual(result.cutoff, "2026-08-03T00:00:00+00:00")
        self.assertEqual(result.window_days, 3)
        self.assertIn("20260803", calls[0])

    def test_rejects_timezone_less_bounds(self):
        with self.assertRaises(ValueError):
            discover_channel_videos(
                "https://www.youtube.com/@example",
                since=datetime(2026, 8, 1),
            )

        with self.assertRaises(ValueError):
            discover_channel_videos(
                "https://www.youtube.com/@example",
                until=datetime(2026, 8, 6),
            )


if __name__ == "__main__":
    unittest.main()
