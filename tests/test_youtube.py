import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from llm_gym.sources.youtube import ingest_one_video


def fake_runner_factory(tmp_path: Path, *, platform_subtitles: bool, whisper_success: bool):
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if "--dump-single-json" in command:
            return CompletedProcess(command, 0, json.dumps({"id": "abc123", "title": "Demo"}), "")
        if "--skip-download" in command:
            if platform_subtitles:
                destination = tmp_path / "platform-subtitles" / "abc123.en.srt"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            return CompletedProcess(command, 0, "", "")
        if any("bestaudio" in argument for argument in command):
            destination = tmp_path / "temporary-audio" / "abc123.m4a"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"audio")
            return CompletedProcess(command, 0, "", "")
        if whisper_success:
            destination = tmp_path / "temporary-audio" / "subtitles" / "abc123.srt"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        return CompletedProcess(command, 0 if whisper_success else 1, "", "whisper failed")

    return runner, calls


class YoutubeIngestionTests(unittest.TestCase):
    def test_uses_platform_subtitles_without_downloading_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            runner, calls = fake_runner_factory(
                tmp_path, platform_subtitles=True, whisper_success=False
            )

            result = ingest_one_video(
                "https://www.youtube.com/watch?v=abc123",
                tmp_path,
                whisper_script="whispermlx-subtitles.sh",
                runner=runner,
            )

            self.assertEqual(result.status, "COMPLETED")
            self.assertEqual(result.subtitle_method, "platform_subtitles")
            self.assertFalse(any("bestaudio" in call for call in calls))
            self.assertTrue(any("%(id)s.%(ext)s" in argument for call in calls for argument in call))
            self.assertTrue(Path(result.transcript_path).read_text(encoding="utf-8").strip())


    def test_falls_back_to_whispermlx(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            runner, calls = fake_runner_factory(
                tmp_path, platform_subtitles=False, whisper_success=True
            )

            result = ingest_one_video(
                "https://www.youtube.com/watch?v=abc123",
                tmp_path,
                whisper_script="whispermlx-subtitles.sh",
                runner=runner,
            )

            self.assertEqual(result.status, "COMPLETED")
            self.assertEqual(result.subtitle_method, "whispermlx")
            self.assertTrue(
                any(any("bestaudio" in argument for argument in call) for call in calls)
            )
            self.assertFalse((tmp_path / "temporary-audio" / "abc123.m4a").exists())

    def test_reuses_existing_transcript_without_subtitle_or_audio_download(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            final_dir = tmp_path / "transcripts"
            final_dir.mkdir(parents=True)
            existing = final_dir / "abc123.srt"
            existing.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nexisting transcript\n", encoding="utf-8"
            )
            (tmp_path / ".ingestion-complete").write_text(
                json.dumps({"video_id": "abc123", "transcript": str(existing)}) + "\n",
                encoding="utf-8",
            )
            calls = []

            def runner(command, **kwargs):
                calls.append(command)
                return CompletedProcess(command, 0, json.dumps({"id": "abc123", "title": "Demo"}), "")

            result = ingest_one_video(
                "https://www.youtube.com/watch?v=abc123",
                tmp_path,
                whisper_script="whispermlx-subtitles.sh",
                runner=runner,
            )

            self.assertEqual(result.status, "COMPLETED")
            self.assertEqual(result.subtitle_method, "existing_transcript")
            self.assertEqual(len(calls), 1)

    def test_platform_subtitle_language_uses_requested_language(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            runner, calls = fake_runner_factory(
                tmp_path, platform_subtitles=True, whisper_success=False
            )
            result = ingest_one_video(
                "https://www.youtube.com/watch?v=abc123",
                tmp_path,
                whisper_script="whispermlx-subtitles.sh",
                language="es",
                runner=runner,
            )
            self.assertEqual(result.status, "COMPLETED")
            subtitle_call = next(call for call in calls if "--write-subs" in call)
            self.assertIn("es.*", subtitle_call)

    def test_existing_transcript_without_completion_marker_is_reprocessed(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            final_dir = tmp_path / "transcripts"
            final_dir.mkdir(parents=True)
            (final_dir / "abc123.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nold transcript\n", encoding="utf-8"
            )
            runner, calls = fake_runner_factory(
                tmp_path, platform_subtitles=True, whisper_success=False
            )
            result = ingest_one_video(
                "https://www.youtube.com/watch?v=abc123",
                tmp_path,
                whisper_script="whispermlx-subtitles.sh",
                runner=runner,
            )
            self.assertEqual(result.status, "COMPLETED")
            self.assertGreater(len(calls), 1)

    def test_whitespace_or_caption_metadata_only_is_not_a_valid_transcript(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            subtitle_dir = tmp_path / "platform-subtitles"
            subtitle_dir.mkdir()
            (subtitle_dir / "abc123.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n   \n", encoding="utf-8"
            )
            runner, calls = fake_runner_factory(
                tmp_path, platform_subtitles=False, whisper_success=False
            )
            result = ingest_one_video(
                "https://www.youtube.com/watch?v=abc123",
                tmp_path,
                whisper_script="whispermlx-subtitles.sh",
                runner=runner,
            )
            self.assertEqual(result.status, "FAILED_TRANSCRIPTION")


    def test_reports_transcription_failure_and_keeps_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            runner, _ = fake_runner_factory(
                tmp_path, platform_subtitles=False, whisper_success=False
            )

            result = ingest_one_video(
                "https://www.youtube.com/watch?v=abc123",
                tmp_path,
                whisper_script="whispermlx-subtitles.sh",
                runner=runner,
            )

            self.assertEqual(result.status, "FAILED_TRANSCRIPTION")
            self.assertIn("whisper failed", result.error)
            self.assertTrue((tmp_path / "temporary-audio" / "abc123.m4a").exists())

    def test_rejects_nonempty_transcript_when_wrapper_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)

            def runner(command, **kwargs):
                if "--dump-single-json" in command:
                    return CompletedProcess(command, 0, json.dumps({"id": "abc123", "title": "Demo"}), "")
                if "--skip-download" in command:
                    return CompletedProcess(command, 0, "", "")
                if any("bestaudio" in argument for argument in command):
                    audio = tmp_path / "temporary-audio" / "abc123.m4a"
                    audio.parent.mkdir(parents=True, exist_ok=True)
                    audio.write_bytes(b"audio")
                    return CompletedProcess(command, 0, "", "")
                transcript = tmp_path / "temporary-audio" / "subtitles" / "abc123.srt"
                transcript.parent.mkdir(parents=True, exist_ok=True)
                transcript.write_text("usable transcript\n", encoding="utf-8")
                return CompletedProcess(command, 1, "optional JSON unavailable", "")

            result = ingest_one_video(
                "https://www.youtube.com/watch?v=abc123",
                tmp_path,
                whisper_script="whispermlx-subtitles.sh",
                runner=runner,
            )

            self.assertEqual(result.status, "FAILED_TRANSCRIPTION")
            self.assertIsNone(result.subtitle_method)
            self.assertIsNone(result.transcript_path)

    def test_short_empty_subtitle_is_skipped_as_no_speech(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)

            def runner(command, **kwargs):
                if "--dump-single-json" in command:
                    return CompletedProcess(command, 0, json.dumps({"id": "abc123", "title": "Demo"}), "")
                if "--skip-download" in command:
                    return CompletedProcess(command, 0, "", "")
                if any("bestaudio" in argument for argument in command):
                    audio = tmp_path / "temporary-audio" / "abc123.m4a"
                    audio.parent.mkdir(parents=True, exist_ok=True)
                    audio.write_bytes(b"audio")
                    return CompletedProcess(command, 0, "", "")
                subtitle = tmp_path / "temporary-audio" / "subtitles" / "abc123.srt"
                subtitle.parent.mkdir(parents=True, exist_ok=True)
                subtitle.write_bytes(b"")
                return CompletedProcess(command, 0, "", "")

            with patch("llm_gym.sources.youtube._media_duration", return_value=90.0):
                result = ingest_one_video(
                    "https://www.youtube.com/watch?v=abc123",
                    tmp_path,
                    whisper_script="whispermlx-subtitles.sh",
                    runner=runner,
                )

            self.assertEqual(result.status, "SKIPPED_SHORT_NO_SPEECH")
            self.assertIsNone(result.transcript_path)
            self.assertFalse((tmp_path / "temporary-audio" / "abc123.m4a").exists())

    def test_short_no_audio_retains_video_and_screenshots(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)

            def runner(command, **kwargs):
                if "--dump-single-json" in command:
                    return CompletedProcess(command, 0, json.dumps({
                        "id": "abc123", "title": "Demo", "duration": 90,
                    }), "")
                if "--write-subs" in command:
                    return CompletedProcess(command, 0, "", "")
                if any("bestaudio" in argument for argument in command):
                    return CompletedProcess(command, 1, "", "no audio")
                if "--extract-audio" in command:
                    return CompletedProcess(command, 1, "", "no audio")
                if "--merge-output-format" in command:
                    video = tmp_path / "video" / "abc123.mp4"
                    video.parent.mkdir(parents=True, exist_ok=True)
                    video.write_bytes(b"video")
                    return CompletedProcess(command, 0, "", "")
                if "-vf" in command:
                    screenshot = tmp_path / "screenshots" / "screenshot_00001.jpg"
                    screenshot.parent.mkdir(parents=True, exist_ok=True)
                    screenshot.write_bytes(b"jpg")
                    return CompletedProcess(command, 0, "", "")
                return CompletedProcess(command, 1, "", "unexpected")

            result = ingest_one_video(
                "https://www.youtube.com/watch?v=abc123", tmp_path,
                whisper_script="whispermlx-subtitles.sh", runner=runner,
            )
            self.assertEqual(result.status, "SKIPPED_SHORT_NO_SPEECH")
            self.assertTrue((tmp_path / "video" / "abc123.mp4").exists())
            self.assertTrue((tmp_path / "screenshots" / "screenshot_00001.jpg").exists())
