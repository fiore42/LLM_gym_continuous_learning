import tempfile
import threading
import time
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from llm_gym.sources.channel import ingest_channel
from llm_gym.sources.discovery import DiscoveredVideo, DiscoveryResult
from llm_gym.sources.youtube import IngestionResult


class ChannelIngestionTests(unittest.TestCase):
    def test_returned_discovery_failure_is_logged(self):
        discovery = DiscoveryResult(
            "channel", "cutoff", "as-of", 30, "oldest_first", "FAILED_DISCOVERY", (),
            error="API unavailable",
        )
        events = []

        class FakeLogger:
            def event(self, **kwargs):
                events.append(kwargs)

        with tempfile.TemporaryDirectory() as directory:
            result = ingest_channel(
                "channel", directory, whisper_script="whisper.sh",
                discover_fn=lambda *args, **kwargs: discovery,
                logger=FakeLogger(),
            )
        self.assertEqual(result.status, "FAILED_DISCOVERY")
        self.assertEqual(events[-1]["stage"], "summary")
        self.assertEqual(events[-1]["status"], "FAILED_DISCOVERY")

    def test_discovery_warning_status_is_not_converted_to_failure(self):
        discovery = DiscoveryResult(
            "channel", "cutoff", "as-of", 30, "oldest_first", "COMPLETED_WITH_WARNINGS", (),
            warnings=("SKIPPED_ITEM_WITHOUT_VIDEO_DATE",),
        )
        with tempfile.TemporaryDirectory() as directory:
            result = ingest_channel(
                "channel", directory, whisper_script="whisper.sh",
                discover_fn=lambda *args, **kwargs: discovery,
            )
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.failure_count, 0)
        self.assertIn("SKIPPED_ITEM_WITHOUT_VIDEO_DATE", result.warnings)

    def test_ingests_videos_and_counts_handled_fallbacks(self):
        videos = (
            DiscoveredVideo("a", "https://www.youtube.com/watch?v=a", "A", "2026-08-01T00:00:00+00:00", "channel"),
            DiscoveredVideo("b", "https://www.youtube.com/watch?v=b", "B", "2026-08-02T00:00:00+00:00", "channel"),
        )
        discovery = DiscoveryResult("channel", "cutoff", "as-of", 30, "oldest_first", "COMPLETED", videos)
        calls = []

        def discover_fn(*args, **kwargs):
            return discovery

        def ingest_fn(url, output_dir, **kwargs):
            calls.append((url, Path(output_dir)))
            method = "whispermlx" if url.endswith("=a") else "platform_subtitles"
            output_dir = Path(output_dir)
            output_dir.joinpath("transcripts").mkdir(parents=True, exist_ok=True)
            output_dir.joinpath("transcripts", f"{url.rsplit('=', 1)[1]}.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nspeech\n", encoding="utf-8"
            )
            transcript = output_dir / "transcripts" / f"{url.rsplit('=', 1)[1]}.srt"
            return IngestionResult(url.rsplit("=", 1)[1], url, "title", "COMPLETED", method, str(transcript), None)

        with tempfile.TemporaryDirectory() as directory:
            result = ingest_channel(
                "channel",
                directory,
                whisper_script="whisper.sh",
                discover_fn=discover_fn,
                ingest_fn=ingest_fn,
            )

            self.assertEqual(result.status, "COMPLETED")
            self.assertEqual(result.completed_count, 2)
            self.assertEqual(result.failure_count, 0)
            self.assertEqual(result.handled_fallback_count, 1)
            self.assertEqual(calls[0][1], Path(directory) / "videos" / "20260801_a")
            self.assertTrue(Path(result.report_path).exists())

            second = ingest_channel(
                "channel",
                directory,
                whisper_script="whisper.sh",
                discover_fn=discover_fn,
                ingest_fn=ingest_fn,
            )
            self.assertEqual(second.skipped_count, 2)
            self.assertEqual(len(calls), 2)

    def test_returns_completed_with_failures_and_records_failure(self):
        video = DiscoveredVideo("a", "https://www.youtube.com/watch?v=a", "A", "2026-08-01T00:00:00+00:00", "channel")
        discovery = DiscoveryResult("channel", "cutoff", "as-of", 30, "oldest_first", "COMPLETED", (video,))

        def discover_fn(*args, **kwargs):
            return discovery

        def ingest_fn(*args, **kwargs):
            return IngestionResult("a", video.canonical_url, "A", "FAILED_AUDIO", None, None, "403")

        with tempfile.TemporaryDirectory() as directory:
            result = ingest_channel(
                "channel",
                directory,
                whisper_script="whisper.sh",
                discover_fn=discover_fn,
                ingest_fn=ingest_fn,
            )

            self.assertEqual(result.status, "COMPLETED_WITH_FAILURES")
            self.assertEqual(result.failure_count, 1)
            self.assertEqual(result.failures[0]["status"], "FAILED_AUDIO")

    def test_worker_exception_becomes_structured_failure(self):
        video = DiscoveredVideo("a", "https://www.youtube.com/watch?v=a", "A", "2026-08-01T00:00:00+00:00", "channel")
        discovery = DiscoveryResult("channel", "cutoff", "as-of", 30, "oldest_first", "COMPLETED", (video,))

        def ingest_fn(*args, **kwargs):
            raise RuntimeError("worker exploded")

        with tempfile.TemporaryDirectory() as directory:
            result = ingest_channel(
                "channel", directory, whisper_script="whisper.sh",
                discover_fn=lambda *args, **kwargs: discovery,
                ingest_fn=ingest_fn,
            )
        self.assertEqual(result.status, "COMPLETED_WITH_FAILURES")
        self.assertEqual(result.failures[0]["status"], "FAILED_INGESTION")
        self.assertIn("worker exploded", result.failures[0]["error"])

    def test_uses_latest_successful_timestamp_for_incremental_discovery(self):
        video = DiscoveredVideo("a", "https://www.youtube.com/watch?v=a", "A", "2026-08-01T00:00:00+00:00", "channel")
        discovery = DiscoveryResult("channel", "cutoff", "as-of", 30, "oldest_first", "COMPLETED", (video,))
        received = []

        def discover_fn(*args, **kwargs):
            received.append(kwargs)
            return discovery

        def ingest_fn(*args, **kwargs):
            return IngestionResult("a", video.canonical_url, "A", "COMPLETED", "platform_subtitles", "a.srt", None)

        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "registry.sqlite3"
            ingest_channel(
                "channel",
                directory,
                whisper_script="whisper.sh",
                discover_fn=discover_fn,
                ingest_fn=ingest_fn,
                source_registry_path=registry,
            )
            ingest_channel(
                "channel",
                directory,
                whisper_script="whisper.sh",
                discover_fn=discover_fn,
                ingest_fn=ingest_fn,
                source_registry_path=registry,
            )

        self.assertIsNone(received[0]["since"])
        self.assertEqual(received[1]["since"], datetime(2026, 8, 1, tzinfo=timezone.utc))
        self.assertIsNone(received[1]["window_days"])

    def test_processes_videos_in_parallel_when_configured(self):
        videos = tuple(
            DiscoveredVideo(str(index), f"https://www.youtube.com/watch?v={index}", f"Video {index}", f"2026-08-{index + 1:02d}T00:00:00+00:00", "channel")
            for index in range(3)
        )
        discovery = DiscoveryResult("channel", "cutoff", "as-of", 30, "oldest_first", "COMPLETED", videos)
        active = 0
        peak = 0
        lock = threading.Lock()

        def discover_fn(*args, **kwargs):
            return discovery

        def ingest_fn(url, output_dir, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            video_id = url.rsplit("=", 1)[1]
            return IngestionResult(video_id, url, video_id, "COMPLETED", "platform_subtitles", f"{video_id}.srt", None)

        with tempfile.TemporaryDirectory() as directory:
            ingest_channel(
                "channel",
                directory,
                whisper_script="whisper.sh",
                discover_fn=discover_fn,
                ingest_fn=ingest_fn,
                video_workers=2,
            )

        self.assertGreaterEqual(peak, 2)


if __name__ == "__main__":
    unittest.main()
