import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from llm_gym.sources.x_transcription import transcribe_post_videos
from llm_gym.sources.screenshots import capture_video_screenshots


class XTranscriptionTests(unittest.TestCase):
    def test_screenshot_capture_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.write_bytes(b"video")
            calls = []

            def runner(command, **kwargs):
                calls.append(command)
                output = Path(command[-1].replace("%05d", "00001"))
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"jpg")
                return subprocess.CompletedProcess(command, 0, "", "")

            self.assertEqual(capture_video_screenshots(video, root / "screenshots", runner=runner), 1)
            self.assertEqual(capture_video_screenshots(video, root / "screenshots", runner=runner), 1)
            self.assertEqual(len(calls), 1)

    def test_extracts_audio_and_transcribes_video_attachment(self):
        old_values = {key: os.environ.get(key) for key in ("FFMPEG_PATH", "FFPROBE_PATH", "WHISPER_SCRIPT")}
        try:
            os.environ["FFMPEG_PATH"] = "fake-ffmpeg"
            os.environ["FFPROBE_PATH"] = "fake-ffprobe"
            os.environ["WHISPER_SCRIPT"] = "fake-whisper"
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "media").mkdir()
                (root / "media" / "7_1.mp4").write_bytes(b"video")

                def runner(command, **kwargs):
                    if command[0] == "fake-ffmpeg":
                        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                        Path(command[-1]).write_bytes(b"audio")
                    elif command[0] == "fake-whisper":
                        audio = Path(command[1])
                        output = audio.parent / "subtitles" / f"{audio.stem}.srt"
                        output.parent.mkdir(parents=True, exist_ok=True)
                        output.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, "", "")

                completed, failures, warnings = transcribe_post_videos(
                    root,
                    {"attachments": {"media_keys": ["7_1"]}},
                    {"media": [{"media_key": "7_1", "type": "video"}]},
                    runner=runner,
                )
                self.assertEqual((completed, failures, warnings), (1, (), ()))
                self.assertTrue((root / "transcripts" / "7_1.srt").exists())
                self.assertFalse((root / "temporary-audio" / "7_1.m4a").exists())
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_short_video_without_audio_is_a_warning_not_a_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "media").mkdir()
            (root / "media" / "7_1.mp4").write_bytes(b"video")

            def runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 1, "", "no audio stream")

            completed, failures, warnings = transcribe_post_videos(
                root,
                {"attachments": {"media_keys": ["7_1"]}},
                {"media": [{"media_key": "7_1", "type": "video", "duration_ms": 24_000}]},
                runner=runner,
            )
            self.assertEqual(completed, 0)
            self.assertEqual(failures, ())
            self.assertTrue(any(warning.startswith("SHORT_VIDEO_NO_AUDIO:7_1:24.0s") for warning in warnings))


if __name__ == "__main__":
    unittest.main()
