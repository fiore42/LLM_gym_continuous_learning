import json
import unittest
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

from llm_gym.sources.youtube_api import discover_channel_videos_api


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class YoutubeApiTests(unittest.TestCase):
    def test_retries_transient_transport_failure(self):
        attempts = []

        def opener(request, timeout):
            attempts.append(1)
            if len(attempts) == 1:
                from urllib.error import URLError
                raise URLError("temporary failure")
            return FakeResponse({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU123"}}}]})

        result = discover_channel_videos_api(
            "https://www.youtube.com/@example", api_key="test-key", opener=opener
        )
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(len(attempts), 3)
    def test_resolves_handle_and_filters_uploads_without_flat_playlist(self):
        requests = []

        def opener(request, timeout):
            requests.append(urlparse(request.full_url))
            query = parse_qs(request.full_url.split("?", 1)[1])
            if query.get("part") == ["contentDetails,snippet"]:
                return FakeResponse({
                    "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU123"}}}]
                })
            return FakeResponse({
                "items": [
                    {"snippet": {"title": "Recent", "resourceId": {"videoId": "new"}}, "contentDetails": {"videoId": "new", "videoPublishedAt": "2026-08-05T00:00:00Z"}},
                    {"snippet": {"title": "Old", "resourceId": {"videoId": "old"}}, "contentDetails": {"videoId": "old", "videoPublishedAt": "2026-08-01T00:00:00Z"}},
                ]
            })

        result = discover_channel_videos_api(
            "https://www.youtube.com/@example",
            api_key="test-key",
            as_of=date(2026, 8, 6),
            opener=opener,
        )

        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual([video.video_id for video in result.videos], ["new"])
        self.assertEqual(parse_qs(requests[0].query)["forHandle"], ["@example"])
        self.assertEqual(parse_qs(requests[1].query)["playlistId"], ["UU123"])

    def test_until_filters_by_timestamp_not_only_date(self):
        def opener(request, timeout):
            query = parse_qs(request.full_url.split("?", 1)[1])
            if query.get("part") == ["contentDetails,snippet"]:
                return FakeResponse({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU123"}}}]})
            return FakeResponse({"items": [
                {"snippet": {"title": "Late", "resourceId": {"videoId": "late"}},
                 "contentDetails": {"videoId": "late", "videoPublishedAt": "2026-08-06T13:00:00Z"}},
                {"snippet": {"title": "Early", "resourceId": {"videoId": "early"}},
                 "contentDetails": {"videoId": "early", "videoPublishedAt": "2026-08-06T11:00:00Z"}},
            ]})
        result = discover_channel_videos_api(
            "https://www.youtube.com/@example",
            api_key="test-key",
            until=datetime(2026, 8, 6, 12, tzinfo=timezone.utc),
            since=datetime(2026, 8, 5, tzinfo=timezone.utc),
            opener=opener,
        )
        self.assertEqual([video.video_id for video in result.videos], ["early"])

    def test_explicit_all_history_includes_old_uploads(self):
        def opener(request, timeout):
            query = parse_qs(request.full_url.split("?", 1)[1])
            if query.get("part") == ["contentDetails,snippet"]:
                return FakeResponse({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU123"}}}]})
            return FakeResponse({"items": [
                {"snippet": {"resourceId": {"videoId": "old"}}, "contentDetails": {"videoId": "old", "videoPublishedAt": "2020-01-01T00:00:00Z"}},
                {"snippet": {"resourceId": {"videoId": "recent"}}, "contentDetails": {"videoId": "recent", "videoPublishedAt": "2026-08-05T00:00:00Z"}},
            ]})

        result = discover_channel_videos_api(
            "https://www.youtube.com/@example", api_key="test-key",
            all_history=True, as_of=date(2026, 8, 6), opener=opener,
        )
        self.assertEqual([video.video_id for video in result.videos], ["old", "recent"])
        self.assertEqual(result.window_days, 0)

    def test_exclusive_cursor_omits_boundary_video(self):
        def opener(request, timeout):
            query = parse_qs(request.full_url.split("?", 1)[1])
            if query.get("part") == ["contentDetails,snippet"]:
                return FakeResponse({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU123"}}}]})
            return FakeResponse({"items": [
                {"snippet": {"resourceId": {"videoId": "new"}},
                 "contentDetails": {"videoId": "new", "videoPublishedAt": "2026-08-01T00:00:01Z"}},
                {"snippet": {"resourceId": {"videoId": "boundary"}},
                 "contentDetails": {"videoId": "boundary", "videoPublishedAt": "2026-08-01T00:00:00Z"}},
            ]})
        result = discover_channel_videos_api(
            "https://www.youtube.com/@example", api_key="test-key",
            since=datetime(2026, 8, 1, tzinfo=timezone.utc),
            until=datetime(2026, 8, 2, tzinfo=timezone.utc),
            since_exclusive=True, opener=opener,
        )
        self.assertEqual([video.video_id for video in result.videos], ["new"])

    def test_rejects_invalid_or_timezone_less_bounds(self):
        with self.assertRaises(ValueError):
            discover_channel_videos_api(
                "https://www.youtube.com/@example",
                api_key="test-key",
                since=datetime(2026, 8, 7, tzinfo=timezone.utc),
                until=datetime(2026, 8, 6, tzinfo=timezone.utc),
            )
        with self.assertRaises(ValueError):
            discover_channel_videos_api(
                "https://www.youtube.com/@example",
                api_key="test-key",
                since=datetime(2026, 8, 1),
            )


if __name__ == "__main__":
    unittest.main()
