import unittest

from llm_gym.sources.storage import canonical_source_url, content_folder_name


class StorageTests(unittest.TestCase):
    def test_canonical_source_url_collapses_youtube_videos_alias(self):
        self.assertEqual(
            canonical_source_url("youtube", "https://www.youtube.com/@claude/videos"),
            "https://www.youtube.com/@claude",
        )
        self.assertEqual(
            canonical_source_url("youtube", "https://www.youtube.com/@claude/"),
            "https://www.youtube.com/@claude",
        )

    def test_uses_publication_date_not_download_date(self):
        self.assertEqual(
            content_folder_name("2026-08-01T13:42:00+00:00", "abc123"),
            "20260801_abc123",
        )

    def test_rejects_unsafe_content_id(self):
        with self.assertRaises(ValueError):
            content_folder_name("2026-08-01", "../abc123")

    def test_rejects_timezone_less_publication_timestamp(self):
        with self.assertRaises(ValueError):
            content_folder_name("2026-08-01T13:42:00", "abc123")


if __name__ == "__main__":
    unittest.main()
