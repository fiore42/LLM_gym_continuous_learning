import tempfile
import unittest
from pathlib import Path

from llm_gym.sources.consistency import check_state_registry_consistency
from llm_gym.sources.source_registry import SourceRegistry
from llm_gym.sources.state import IngestionState
from llm_gym.sources.youtube import IngestionResult


class ConsistencyTests(unittest.TestCase):
    def _manifest(self, root: Path) -> Path:
        path = root / "SOURCES.md"
        path.write_text(
            "# Sources\n\n[Project rules](../PROJECT_RULES.md)\n\n"
            "| Platform | Name | Handle | Category | Subscribed | Since |\n"
            "|---|---|---|---|---|---|\n"
            "| youtube | Example | @example | test | Y | 2026-08-01T00:00:00+00:00 |\n",
            encoding="utf-8",
        )
        return path

    def test_local_and_central_records_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest(root)
            state_path = root / "source/youtube/example/ingestion-state.sqlite3"
            result = IngestionResult("v1", "https://youtube.com/watch?v=v1", "Example", "COMPLETED", "platform_subtitles", "v1.srt", None)
            with IngestionState(state_path) as state:
                state.record(video_id="v1", canonical_url=result.canonical_url, title=result.title, published_at="2026-08-02T00:00:00+00:00", result=result)
            with SourceRegistry(root / "registry.sqlite3") as registry:
                registry.ensure_source(platform="youtube", source_key="https://www.youtube.com/@example", source_type="channel", canonical_url="https://www.youtube.com/@example")
                registry.record_content(platform="youtube", source_key="https://www.youtube.com/@example", content_id="v1", canonical_url=result.canonical_url, published_at="2026-08-02T00:00:00+00:00", status="COMPLETED", transcript_path="v1.srt")
            report = check_state_registry_consistency(source_root=root, registry_path=root / "registry.sqlite3", manifest_path=manifest)
            self.assertEqual(report["status"], "COMPLETED")
            self.assertEqual(report["checked_items"], 1)

    def test_missing_central_record_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._manifest(root)
            with IngestionState(root / "source/youtube/example/ingestion-state.sqlite3") as state:
                state.record(video_id="v1", canonical_url="https://youtube.com/watch?v=v1", title="Example", published_at="2026-08-02T00:00:00+00:00", result=IngestionResult("v1", "https://youtube.com/watch?v=v1", "Example", "COMPLETED", "platform_subtitles", "v1.srt", None))
            with SourceRegistry(root / "registry.sqlite3"):
                pass
            report = check_state_registry_consistency(source_root=root, registry_path=root / "registry.sqlite3", manifest_path=manifest)
            self.assertEqual(report["status"], "FAILED_INCONSISTENT")
            self.assertEqual(report["mismatches"][0]["issue"], "missing_central_record")


if __name__ == "__main__":
    unittest.main()
