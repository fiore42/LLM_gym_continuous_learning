"""Subtitle-first ingestion for one YouTube video.

The module deliberately keeps the subprocess boundary injectable so the workflow
can be tested without network access, credentials, yt-dlp, or WhisperX.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import threading
import tempfile
import re
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, ContextManager, Sequence

from ..shared.run_log import RunLogger
from ..shared.atomic import atomic_write_text
from ..shared.status import status_category
from ..shared.settings import runtime_parameters, tool_parameters
from .screenshots import capture_video_screenshots
from ..shared.settings import ingestion_parameters


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
_TIMESTAMP_LINE = re.compile(
    r"^(?:\d+\s*$|WEBVTT\s*$|\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->).*", re.I
)
_CUE_TIMESTAMP = re.compile(r"\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}")


@dataclass(frozen=True)
class IngestionResult:
    video_id: str | None
    canonical_url: str
    title: str | None
    status: str
    subtitle_method: str | None
    transcript_path: str | None
    error: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _run(
    command: Sequence[str],
    runner: CommandRunner,
    limiter: ContextManager[object] | None = None,
    logger: RunLogger | None = None,
    stage: str = "subprocess",
    progress: Callable[[str], None] | None = None,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    started_at = datetime.now(timezone.utc).isoformat()
    started_clock = time.monotonic()
    finished = threading.Event()

    with limiter or nullcontext():
        if progress:
            progress(f"Starting {stage}")

            def heartbeat() -> None:
                while not finished.wait(15):
                    elapsed = round(time.monotonic() - started_clock)
                    progress(f"Still running {stage} ({elapsed}s elapsed)")

            threading.Thread(target=heartbeat, daemon=True).start()
        try:
            result = runner(
                list(command), check=False, capture_output=True, text=True,
                timeout=timeout_seconds or runtime_parameters()["subprocess_timeout_seconds"],
            )
        except subprocess.TimeoutExpired as exc:
            result = subprocess.CompletedProcess(
                list(command), 124, exc.stdout or "", exc.stderr or "command timed out"
            )
        except OSError as exc:
            result = subprocess.CompletedProcess(list(command), 127, "", str(exc))
    finished.set()
    ended_at = datetime.now(timezone.utc).isoformat()
    elapsed_ms = round((time.monotonic() - started_clock) * 1000, 2)
    if progress:
        progress(f"Completed {stage}: returncode={result.returncode}, duration={elapsed_ms / 1000:.1f}s")
    if logger:
        logger.event(
            operation="ingest_one_video",
            stage=stage,
            category="INFO" if result.returncode == 0 else "FAILURE",
            status=f"RETURN_CODE_{result.returncode}",
            parameters={"command": list(command)},
            output={
                "returncode": result.returncode,
                "stdout": (result.stdout or "")[-2000:] if result.returncode else "[suppressed on success]",
                "stderr": (result.stderr or "")[-2000:] if result.returncode else "[suppressed on success]",
            },
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=elapsed_ms,
        )
    return result


def _metadata(
    url: str,
    yt_dlp: str,
    auth_args: Sequence[str],
    runner: CommandRunner,
    download_limiter: ContextManager[object] | None = None,
    logger: RunLogger | None = None,
    progress: Callable[[str], None] | None = None,
) -> tuple[str, str | None, float | None]:
    result = _run(
        [
            yt_dlp,
            *auth_args,
            "--no-warnings",
            "--no-playlist",
            "--dump-single-json",
            "--skip-download",
            url,
        ],
        runner,
        download_limiter,
        logger,
        "yt_dlp_metadata",
        progress,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"metadata discovery failed: {detail[-1000:]}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("metadata discovery returned invalid JSON") from exc

    video_id = data.get("id")
    if not video_id:
        raise RuntimeError("metadata did not contain a video ID")
    duration = data.get("duration")
    return str(video_id), data.get("title"), float(duration) if duration is not None else None


def _find_transcript(directory: Path, video_id: str) -> Path | None:
    candidates = sorted(
        path
        for path in directory.glob(f"{video_id}*")
        if path.suffix.lower() in {".srt", ".vtt", ".ttml", ".ass"}
        and path.is_file()
        and _has_transcript_text(path)
    )
    return candidates[0] if candidates else None


def _has_transcript_text(path: Path) -> bool:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, UnicodeError):
        return False
    meaningful = any(line.strip() and not _TIMESTAMP_LINE.match(line.strip()) for line in lines)
    if not meaningful:
        return False
    if path.suffix.lower() in {".srt", ".vtt"}:
        return bool(_CUE_TIMESTAMP.search("\n".join(lines)))
    return True


def is_valid_transcript_path(path: str | Path | None) -> bool:
    return bool(path and (candidate := Path(path)).is_file() and _has_transcript_text(candidate))


def _find_media(directory: Path, video_id: str) -> Path | None:
    extensions = {".m4a", ".mp3", ".aac", ".opus", ".webm", ".wav", ".mp4"}
    candidates = sorted(
        path
        for path in directory.glob(f"{video_id}.*")
        if path.suffix.lower() in extensions and path.is_file() and path.stat().st_size > 0
    )
    return candidates[0] if candidates else None


def _find_video(directory: Path, video_id: str) -> Path | None:
    candidates = sorted(
        path for path in directory.glob(f"{video_id}.*")
        if path.suffix.lower() in {".mp4", ".m4v", ".webm", ".mov"}
        and path.is_file() and path.stat().st_size > 0
    )
    return candidates[0] if candidates else None


def _media_duration(path: Path, ffprobe: str | None = None) -> float | None:
    """Return media duration in seconds when ffprobe can read it."""
    try:
        result = subprocess.run(
            [
                ffprobe or tool_parameters()["ffprobe"], "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, ValueError):
        return None


def _copy_final_transcript(source: Path, output_dir: Path, video_id: str) -> Path:
    final_dir = output_dir / "transcripts"
    final_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    destination = final_dir / f"{video_id}{suffix}"
    shutil.copy2(source, destination)
    return destination


def _mark_complete(output_dir: Path, video_id: str, transcript: Path) -> None:
    marker = output_dir / ".ingestion-complete"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=output_dir, prefix=".ingestion-complete.", suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump({"video_id": video_id, "transcript": str(transcript)}, handle, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, marker)


def _completion_marker_matches(output_dir: Path, video_id: str, transcript: Path) -> bool:
    try:
        marker = json.loads((output_dir / ".ingestion-complete").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return marker.get("video_id") == video_id and Path(marker.get("transcript", "")) == transcript


def _write_log(output_dir: Path, result: IngestionResult) -> None:
    """Write only the latest compact item result; history lives in run-log.jsonl."""
    log_path = output_dir / "ingestion-events.jsonl"
    entry = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        **result.to_dict(),
    }
    atomic_write_text(log_path, json.dumps(entry, ensure_ascii=False) + "\n")


def _record_result(logger: RunLogger | None, output_dir: Path, result: IngestionResult) -> None:
    _write_log(output_dir, result)
    if logger is None:
        return
    category = status_category(result.status)
    if result.subtitle_method == "whispermlx":
        logger.event(
            operation="ingest_one_video",
            stage="subtitle_fallback",
            category="HANDLED_FALLBACK",
            status="RECOVERED",
            output={"subtitle_method": result.subtitle_method},
            artifact_paths=[result.transcript_path] if result.transcript_path else [],
        )
    logger.event(
        operation="ingest_one_video",
        stage="video_ingestion",
        category=category,
        status=result.status,
        parameters={"url": result.canonical_url, "video_id": result.video_id},
        output={"video_id": result.video_id, "status": result.status,
                "subtitle_method": result.subtitle_method,
                "has_transcript": bool(result.transcript_path)},
        error=result.error,
        artifact_paths=[result.transcript_path] if result.transcript_path else [],
    )


def ingest_one_video(
    url: str,
    output_dir: str | Path,
    *,
    whisper_script: str | Path,
    yt_dlp: str = "yt-dlp",
    auth_args: Sequence[str] = (),
    model: str = "small",
    language: str = "en",
    runner: CommandRunner = subprocess.run,
    logger: RunLogger | None = None,
    download_limiter: ContextManager[object] | None = None,
    transcription_limiter: ContextManager[object] | None = None,
    progress: Callable[[str], None] | None = None,
) -> IngestionResult:
    """Ingest one video using subtitles first and WhisperX as fallback.

    `auth_args` is intentionally an argument list, not a username/password
    parameter. Callers should use a browser-cookie option or a protected
    credential mechanism and must not put plaintext secrets in logs.
    """

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    if logger:
        logger.event(
            operation="ingest_one_video",
            stage="start",
            parameters={
                "url": url,
                "output_dir": str(output_path),
                "yt_dlp": yt_dlp,
                "whisper_script": str(whisper_script),
                "model": model,
                "language": language,
            },
        )
    video_id: str | None = None
    title: str | None = None
    video_duration: float | None = None

    try:
        video_id, title, video_duration = _metadata(url, yt_dlp, auth_args, runner, download_limiter, logger, progress)
    except Exception as exc:
        result = IngestionResult(None, url, None, "FAILED_METADATA", None, None, str(exc))
        _record_result(logger, output_path, result)
        return result

    existing_transcript = _find_transcript(output_path / "transcripts", video_id)
    if existing_transcript and _completion_marker_matches(output_path, video_id, existing_transcript):
        result = IngestionResult(
            video_id,
            url,
            title,
            "COMPLETED",
            "existing_transcript",
            str(existing_transcript),
            None,
        )
        _record_result(logger, output_path, result)
        return result

    subtitle_dir = output_path / "platform-subtitles"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    for stale_subtitle in subtitle_dir.glob(f"{video_id}*"):
        if stale_subtitle.is_file():
            stale_subtitle.unlink()
    subtitle_result = _run(
        [
            yt_dlp,
            *auth_args,
            "--no-warnings",
            "--no-playlist",
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            f"{language}.*",
            "--convert-subs",
            "srt",
            "-o",
            str(subtitle_dir / "%(id)s.%(ext)s"),
            url,
        ],
        runner,
        download_limiter,
        logger,
        "yt_dlp_subtitles",
        progress,
    )
    transcript = _find_transcript(subtitle_dir, video_id)
    if subtitle_result.returncode == 0 and transcript:
        final_transcript = _copy_final_transcript(transcript, output_path, video_id)
        _mark_complete(output_path, video_id, final_transcript)
        result = IngestionResult(
            video_id, url, title, "COMPLETED", "platform_subtitles", str(final_transcript), None
        )
        _record_result(logger, output_path, result)
        return result

    audio_dir = output_path / "temporary-audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_file = _find_media(audio_dir, video_id)
    audio_result = subprocess.CompletedProcess([], 0, "", "") if audio_file else None
    audio_files = [audio_file] if audio_file else []

    if not audio_file:
        audio_result = _run(
            [
                yt_dlp,
                *auth_args,
                "--no-warnings",
                "--no-playlist",
                "-f",
                "bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio",
                "-o",
                str(audio_dir / "%(id)s.%(ext)s"),
                url,
            ],
            runner,
            download_limiter,
            logger,
            "yt_dlp_audio",
            progress,
        )
        audio_file = _find_media(audio_dir, video_id)
        audio_files = [audio_file] if audio_file else []

    # Some YouTube videos expose an audio-only format that can be listed but
    # returns 403 when downloaded because of delivery-token restrictions. In
    # that case use a low-resolution muxed stream, extract audio with ffmpeg,
    # and let yt-dlp remove the temporary video after post-processing.
    if audio_result.returncode != 0 or not audio_files:
        muxed_result = _run(
            [
                yt_dlp,
                *auth_args,
                "--no-warnings",
                "--no-playlist",
                "-f",
                "worst[ext=mp4][vcodec!=none][acodec!=none]/worst[vcodec!=none][acodec!=none]",
                "--extract-audio",
                "--audio-format",
                "m4a",
                "-o",
                str(audio_dir / "%(id)s.%(ext)s"),
                url,
            ],
            runner,
            download_limiter,
            logger,
            "yt_dlp_muxed_audio",
            progress,
        )
        audio_file = _find_media(audio_dir, video_id)
        audio_files = [audio_file] if audio_file else []
        if muxed_result.returncode == 0 and audio_files:
            audio_result = muxed_result

    if audio_result.returncode != 0 or not audio_files:
        max_short_seconds = ingestion_parameters()["short_video_max_seconds"]
        if video_duration is not None and video_duration < max_short_seconds:
            video_dir = output_path / "video"
            video_dir.mkdir(parents=True, exist_ok=True)
            video_file = _find_video(video_dir, video_id)
            if not video_file:
                video_result = _run(
                    [
                        yt_dlp, *auth_args, "--no-warnings", "--no-playlist",
                        "-f", "worst[ext=mp4][vcodec!=none]/worst[vcodec!=none]",
                        "--merge-output-format", "mp4",
                        "-o", str(video_dir / f"{video_id}.%(ext)s"), url,
                    ], runner, download_limiter, logger, "yt_dlp_short_video", progress,
                )
                video_file = _find_video(video_dir, video_id)
            if video_file:
                try:
                    count = capture_video_screenshots(
                        video_file, output_path / "screenshots", runner=runner,
                    )
                    reason = (
                        f"short video ({video_duration:.1f}s) has no usable audio; "
                        f"video retained with {count} screenshots at the configured interval"
                    )
                except Exception as exc:
                    reason = f"short video ({video_duration:.1f}s) has no usable audio; screenshot warning: {exc}"
            else:
                reason = f"short video ({video_duration:.1f}s) has no usable audio; video download warning"
            result = IngestionResult(video_id, url, title, "SKIPPED_SHORT_NO_SPEECH", None, None, reason)
            _record_result(logger, output_path, result)
            return result
        detail = (audio_result.stderr or audio_result.stdout).strip()
        result = IngestionResult(
            video_id,
            url,
            title,
            "FAILED_AUDIO",
            None,
            None,
            detail[-1000:] or "audio file was not produced",
        )
        _record_result(logger, output_path, result)
        return result

    audio_file = audio_files[0]
    audio_duration = _media_duration(audio_file)
    if progress:
        duration_text = f"{audio_duration:.1f}" if audio_duration is not None else "unknown"
        progress(f"Transcription queued for {video_id}: duration={duration_text}s")
    subtitle_work_dir = audio_dir / "subtitles"
    for stale_subtitle in subtitle_work_dir.glob(f"{video_id}*"):
        if stale_subtitle.is_file():
            stale_subtitle.unlink()
    whisper_result = _run(
        [str(whisper_script), str(audio_file), "1", model, language],
        runner,
        transcription_limiter,
        logger,
        "whisper_transcription",
        progress,
    )
    whisper_transcript = _find_transcript(audio_dir / "subtitles", video_id)
    # A transcript is complete only when the process exits successfully and
    # leaves a non-empty subtitle artifact. A stale/partial artifact from an
    # interrupted attempt must never make a retry look complete.
    if whisper_result.returncode == 0 and whisper_transcript:
        final_transcript = _copy_final_transcript(whisper_transcript, output_path, video_id)
        _mark_complete(output_path, video_id, final_transcript)
        audio_file.unlink(missing_ok=True)
        result = IngestionResult(
            video_id, url, title, "COMPLETED", "whispermlx", str(final_transcript), None
        )
        _record_result(logger, output_path, result)
        return result

    empty_subtitle = any(
        path.is_file() and path.stat().st_size == 0
        for path in subtitle_work_dir.glob(f"{video_id}*")
    )
    if audio_duration is not None and audio_duration < ingestion_parameters()["short_video_max_seconds"] and empty_subtitle:
        reason = (
            f"short video ({audio_duration:.1f}s) produced an empty subtitle file; "
            "treated as no speech/music-only"
        )
        video_dir = output_path / "video"
        video_dir.mkdir(parents=True, exist_ok=True)
        video_file = _find_video(video_dir, video_id)
        if not video_file:
            _run(
                [
                    yt_dlp, *auth_args, "--no-warnings", "--no-playlist",
                    "-f", "worst[ext=mp4][vcodec!=none]/worst[vcodec!=none]",
                    "--merge-output-format", "mp4",
                    "-o", str(video_dir / f"{video_id}.%(ext)s"), url,
                ], runner, download_limiter, logger, "yt_dlp_short_video", progress,
            )
            video_file = _find_video(video_dir, video_id)
        if video_file:
            try:
                count = capture_video_screenshots(video_file, output_path / "screenshots", runner=runner)
                reason += f"; video retained with {count} screenshots at the configured interval"
            except Exception as exc:
                reason += f"; screenshot warning: {exc}"
        else:
            reason += "; video download warning"
        audio_file.unlink(missing_ok=True)
        for path in subtitle_work_dir.glob(f"{video_id}*"):
            if path.is_file():
                path.unlink()
        result = IngestionResult(
            video_id, url, title, "SKIPPED_SHORT_NO_SPEECH", None, None, reason
        )
        _record_result(logger, output_path, result)
        return result

    detail = (whisper_result.stderr or whisper_result.stdout).strip()
    result = IngestionResult(
        video_id,
        url,
        title,
        "FAILED_TRANSCRIPTION",
        None,
        None,
        detail[-1000:] or (
            f"WhisperX returned code {whisper_result.returncode} and did not "
            "complete with a non-empty subtitle file"
        ),
    )
    _record_result(logger, output_path, result)
    return result
