"""Transcribe video attachments downloaded from X."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .youtube import is_valid_transcript_path
from ..shared.settings import runtime_parameters, tool_parameters
from .screenshots import capture_video_screenshots
from ..shared.settings import ingestion_parameters


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _run(command: list[str], runner: CommandRunner) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            command, check=False, capture_output=True, text=True,
            timeout=runtime_parameters()["subprocess_timeout_seconds"],
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(command, 124, exc.stdout or "", exc.stderr or "command timed out")
    except OSError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))


def _duration(path: Path, runner: CommandRunner) -> float | None:
    try:
        result = runner(
            [tool_parameters()["ffprobe"], "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=False, capture_output=True, text=True,
            timeout=runtime_parameters()["subprocess_timeout_seconds"],
        )
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def transcribe_post_videos(
    post_dir: str | Path,
    post: dict[str, object],
    includes: dict[str, list[dict[str, object]]],
    *,
    runner: CommandRunner = subprocess.run,
    whisper_script: str | Path | None = None,
    model: str = "small",
    language: str = "en",
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    """Return completed transcript count, unresolved failures, and warnings.

    X currently exposes media URLs/variants but no standard caption-download
    field. If a future response supplies a valid subtitle file, it can be
    placed in ``transcripts`` and will be reused; downloaded video attachments
    otherwise go through ffmpeg plus the configured Whisper script.
    """
    root = Path(post_dir)
    media_by_key = {str(item.get("media_key")): item for item in includes.get("media", [])}
    transcripts = root / "transcripts"
    temporary = root / "temporary-audio"
    completed = 0
    failures: list[str] = []
    warnings: list[str] = []
    keys = (post.get("attachments") or {}).get("media_keys", [])
    for key in keys:
        media = media_by_key.get(str(key), {})
        if media.get("type") != "video":
            continue
        media_files = sorted(
            path for path in (root / "media").glob(f"{key}.*")
            if path.suffix.lower() in {".mp4", ".m4v", ".webm", ".mov"} and path.is_file()
        )
        if not media_files:
            failures.append(f"VIDEO_MEDIA_MISSING:{key}")
            continue
        transcript = transcripts / f"{key}.srt"
        if is_valid_transcript_path(transcript):
            completed += 1
            continue
        audio = temporary / f"{key}.m4a"
        audio.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_result = _run(
            [tool_parameters()["ffmpeg"], "-y", "-i", str(media_files[0]), "-vn", "-acodec", "aac", str(audio)],
            runner,
        )
        if ffmpeg_result.returncode != 0 or not audio.is_file() or audio.stat().st_size == 0:
            duration_ms = media.get("duration_ms")
            if isinstance(duration_ms, (int, float)) and duration_ms < ingestion_parameters()["short_video_max_seconds"] * 1000:
                try:
                    count = capture_video_screenshots(root / "media" / media_files[0].name, root / "screenshots", runner=runner)
                    detail = f":{count}_screenshots"
                except Exception as exc:
                    detail = f":screenshot_warning={exc}"
                warnings.append(f"SHORT_VIDEO_NO_AUDIO:{key}:{duration_ms / 1000:.1f}s{detail}")
                audio.unlink(missing_ok=True)
                continue
            detail = (ffmpeg_result.stderr or ffmpeg_result.stdout or "audio was not produced").strip()
            failures.append(f"VIDEO_AUDIO_FAILED:{key}:{detail[-500:]}")
            continue
        subtitle_dir = temporary / "subtitles"
        for stale in subtitle_dir.glob(f"{key}*"):
            if stale.is_file():
                stale.unlink()
        whisper_result = _run(
            [str(whisper_script or tool_parameters()["whisper_script"]), str(audio), "1", model, language],
            runner,
        )
        candidates = sorted(
            path for path in subtitle_dir.glob(f"{key}*")
            if path.suffix.lower() in {".srt", ".vtt", ".ttml", ".ass"} and path.is_file()
        )
        valid = next((path for path in candidates if is_valid_transcript_path(path)), None)
        if whisper_result.returncode == 0 and valid:
            transcripts.mkdir(parents=True, exist_ok=True)
            shutil.copy2(valid, transcript)
            audio.unlink(missing_ok=True)
            completed += 1
            continue
        duration = _duration(audio, runner)
        empty = any(path.stat().st_size == 0 for path in candidates)
        if duration is not None and duration < ingestion_parameters()["short_video_max_seconds"] and empty:
            try:
                count = capture_video_screenshots(media_files[0], root / "screenshots", runner=runner)
                detail = f":{count}_screenshots"
            except Exception as exc:
                detail = f":screenshot_warning={exc}"
            warnings.append(f"SHORT_VIDEO_NO_SPEECH:{key}:{duration:.1f}s{detail}")
            audio.unlink(missing_ok=True)
            for path in candidates:
                path.unlink(missing_ok=True)
            continue
        detail = (whisper_result.stderr or whisper_result.stdout or "no transcript was produced").strip()
        failures.append(f"VIDEO_TRANSCRIPTION_FAILED:{key}:{detail[-500:]}")
    return completed, tuple(failures), tuple(warnings)
