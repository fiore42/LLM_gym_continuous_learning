import tempfile
import unittest
from pathlib import Path

from llm_gym.sources.source_registry import SourceRegistry


class SourceRegistryTests(unittest.TestCase):
    def test_caches_x_user_ids_and_rejects_identity_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            with SourceRegistry(Path(directory) / "sources.sqlite3") as registry:
                self.assertIsNone(registry.x_user_id("@OpenAI"))
                registry.cache_x_user_id("@OpenAI", "123")
                self.assertEqual(registry.x_user_id("@openai"), "123")
                with self.assertRaises(ValueError):
                    registry.cache_x_user_id("@OPENAI", "456")

    def test_tracks_latest_successful_content_only(self):
        with tempfile.TemporaryDirectory() as directory:
            with SourceRegistry(Path(directory) / "sources.sqlite3") as registry:
                registry.ensure_source(
                    platform="youtube",
                    source_key="@example",
                    source_type="channel",
                    canonical_url="https://www.youtube.com/@example",
                )
                registry.record_content(
                    platform="youtube",
                    source_key="@example",
                    content_id="failed",
                    canonical_url="https://youtube.com/watch?v=failed",
                    published_at="2026-08-01T00:00:00+00:00",
                    status="FAILED_AUDIO",
                    error="403",
                )
                self.assertIsNone(
                    registry.latest_terminal_published_at(platform="youtube", source_key="@example")
                )
                registry.record_content(
                    platform="youtube",
                    source_key="@example",
                    content_id="ok",
                    canonical_url="https://youtube.com/watch?v=ok",
                    published_at="2026-08-02T00:00:00+00:00",
                    status="COMPLETED",
                    transcript_path="ok.srt",
                )
                self.assertEqual(
                    registry.latest_terminal_published_at(platform="youtube", source_key="@example"),
                    "2026-08-02T00:00:00+00:00",
                )
                self.assertTrue(
                    registry.has_successful_content(
                        platform="youtube", source_key="@example", content_id="ok"
                    )
                )
                registry.record_content(
                    platform="youtube",
                    source_key="@example",
                    content_id="music",
                    canonical_url="https://youtube.com/watch?v=music",
                    published_at="2026-08-03T00:00:00+00:00",
                    status="SKIPPED_SHORT_NO_SPEECH",
                    error="empty subtitles",
                )
                self.assertTrue(
                    registry.has_terminal_content(
                        platform="youtube", source_key="@example", content_id="music"
                    )
                )
                self.assertEqual(
                    registry.latest_successful_published_at(
                        platform="youtube", source_key="@example"
                    ),
                    "2026-08-03T00:00:00+00:00",
                )

    def test_rejects_source_identity_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            with SourceRegistry(Path(directory) / "sources.sqlite3") as registry:
                registry.ensure_source(
                    platform="youtube", source_key="@example", source_type="channel",
                    canonical_url="https://www.youtube.com/@example",
                )
                with self.assertRaises(ValueError):
                    registry.ensure_source(
                        platform="youtube", source_key="@example", source_type="channel",
                        canonical_url="https://www.youtube.com/@other",
                    )

    def test_rejects_content_identity_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            with SourceRegistry(Path(directory) / "sources.sqlite3") as registry:
                registry.ensure_source(
                    platform="youtube", source_key="@example", source_type="channel",
                    canonical_url="https://www.youtube.com/@example",
                )
                registry.record_content(
                    platform="youtube", source_key="@example", content_id="v1",
                    canonical_url="https://youtube.com/watch?v=v1",
                    published_at="2026-08-01T00:00:00+00:00", status="FAILED_AUDIO",
                )
                with self.assertRaises(ValueError):
                    registry.record_content(
                        platform="youtube", source_key="@example", content_id="v1",
                        canonical_url="https://youtube.com/watch?v=v1-new",
                        published_at="2026-08-01T00:00:00+00:00", status="FAILED_AUDIO",
                    )


if __name__ == "__main__":
    unittest.main()
