"""Concurrent, bounded ingestion of recent videos from one YouTube channel."""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, ContextManager, Sequence

from .discovery import DiscoveryResult, discover_channel_videos
from ..shared.atomic import atomic_write_text
from ..shared.run_log import RunLogger
from .state import IngestionState
from .source_registry import SourceRegistry
from .storage import canonical_source_url, content_folder_name
from .youtube import CommandRunner, IngestionResult, ingest_one_video, is_valid_transcript_path
from ..shared.status import is_failure_status, status_category
from ..shared.settings import ingestion_parameters


DiscoveryFn = Callable[..., DiscoveryResult]
IngestionFn = Callable[..., IngestionResult]
VideoEventFn = Callable[[str, str, str, str | None, IngestionResult | None], None]


@contextmanager
def _registry_scope(registry: SourceRegistry):
    try:
        yield registry
    finally:
        registry.close()


@dataclass(frozen=True)
class ChannelIngestionResult:
    channel_url: str
    status: str
    discovered_count: int
    completed_count: int
    failure_count: int
    warning_count: int
    handled_fallback_count: int
    skipped_count: int
    videos: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]
    failures: tuple[dict[str, object], ...]
    report_path: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _write_report(path: Path, result: ChannelIngestionResult) -> None:
    atomic_write_text(path, json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n")


def ingest_channel(
    channel_url: str,
    output_dir: str | Path,
    *,
    whisper_script: str | Path,
    window_days: int | None = None,
    as_of=None,
    since: datetime | None = None,
    until: datetime | date | None = None,
    all_history: bool = False,
    force: bool = False,
    order: str = "oldest_first",
    yt_dlp: str = "yt-dlp",
    auth_args: Sequence[str] = (),
    model: str = "small",
    language: str = "en",
    runner: CommandRunner = subprocess.run,
    progress: Callable[[str], None] | None = None,
    discover_fn: DiscoveryFn = discover_channel_videos,
    ingest_fn: IngestionFn = ingest_one_video,
    source_registry_path: str | Path | None = None,
    platform: str = "youtube",
    source_key: str | None = None,
    logger: RunLogger | None = None,
    download_limiter: ContextManager[object] | None = None,
    transcription_limiter: ContextManager[object] | None = None,
    video_workers: int = 1,
    video_event: VideoEventFn | None = None,
) -> ChannelIngestionResult:
    """Discover and ingest one channel with bounded worker concurrency.

    A handled subtitle fallback is counted as successful completion with
    provenance, not as a failure. Only unresolved video operations count as
    failures.
    """

    root = Path(output_dir)
    if video_workers < 1:
        raise ValueError("video_workers must be positive")
    report_path = root / "channel-ingestion-report.json"
    state_path = root / "ingestion-state.sqlite3"
    if logger:
        logger.event(
            operation="ingest_channel",
            stage="start",
            parameters={
                "channel_url": channel_url,
                "output_dir": str(root),
                "window_days": window_days,
                "since": since.isoformat() if since else None,
                "until": until.isoformat() if hasattr(until, "isoformat") else until,
                "all_history": all_history,
                "order": order,
                "platform": platform,
            },
        )

    def report(message: str) -> None:
        if progress:
            progress(message)

    registry = SourceRegistry(source_registry_path or (root / "source-registry.sqlite3"))
    registry_source_key = canonical_source_url(platform, source_key or channel_url)
    registry_canonical_url = canonical_source_url(platform, channel_url)
    registry.ensure_source(
        platform=platform,
        source_key=registry_source_key,
        source_type="channel",
        canonical_url=registry_canonical_url,
    )

    effective_since = since
    since_exclusive = False
    effective_window_days = window_days
    if not force:
        latest = registry.latest_terminal_published_at(
            platform=platform,
            source_key=registry_source_key,
        )
        if latest:
            latest_dt = datetime.fromisoformat(latest)
            if effective_since is None or latest_dt > effective_since:
                effective_since = latest_dt
            since_exclusive = True
            report(f"Incremental run: checking content since {latest}")
    if effective_since is None and effective_window_days is None:
        if force:
            report("Force run: checking the configured ingestion window")
        else:
            effective_window_days = ingestion_parameters()["default_window_days"]
            report(
                f"New source: checking the previous "
                f"{effective_window_days} days"
            )

    try:
        discovery = discover_fn(
            channel_url,
            window_days=effective_window_days,
            as_of=as_of,
            since=effective_since,
            since_exclusive=since_exclusive,
            until=until,
            all_history=all_history,
            order=order,
            yt_dlp=yt_dlp,
            auth_args=auth_args,
            runner=runner,
            progress=progress,
        )
    except Exception as exc:
        result = ChannelIngestionResult(
            channel_url, "FAILED_DISCOVERY", 0, 0, 1, 0, 0, 0, (), (),
            ({"stage": "discovery", "error": str(exc)},), str(report_path), str(exc)
        )
        _write_report(report_path, result)
        registry.close()
        if logger:
            logger.event(
                operation="ingest_channel", stage="summary", category="FAILURE",
                status=result.status, parameters={"channel_url": channel_url},
                output={"channel_url": channel_url, "status": result.status, "failed": 1},
                error=str(exc), artifact_paths=[str(report_path)],
            )
        return result
    if is_failure_status(discovery.status):
        report(
            f"Failure recorded for {channel_url}: discovery failed: "
            f"{discovery.error or 'no error details provided'}"
        )
        result = ChannelIngestionResult(
            channel_url,
            "FAILED_DISCOVERY",
            0,
            0,
            1,
            len(discovery.warnings),
            0,
            0,
            (),
            tuple(discovery.warnings),
            ({"stage": "discovery", "error": discovery.error},),
            str(report_path),
            discovery.error,
        )
        _write_report(report_path, result)
        registry.close()
        if logger:
            logger.event(
                operation="ingest_channel", stage="summary", category="FAILURE",
                status=result.status, parameters={"channel_url": channel_url},
                output={"channel_url": channel_url, "status": result.status, "failed": 1},
                error=result.error, artifact_paths=[str(report_path)],
            )
        return result

    warnings = list(discovery.warnings)
    report(f"{channel_url}: {len(discovery.videos)} videos discovered")
    videos: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    completed_count = 0
    handled_fallback_count = 0

    candidate_videos = discovery.videos
    if not candidate_videos:
        warnings.append("NO_NEW_VIDEOS")
    warnings = list(dict.fromkeys(warnings))

    if video_event:
        for video in candidate_videos:
            video_event("planned", channel_url, video.video_id, video.title, None)

    skipped_count = 0
    pending_videos = []
    for video in candidate_videos:
        record = registry.content_record(
            platform=platform,
            source_key=registry_source_key,
            content_id=video.video_id,
        )
        terminal = bool(record and record["status"] == "SKIPPED_SHORT_NO_SPEECH")
        terminal = terminal or bool(
            record and record["status"] == "COMPLETED"
            and is_valid_transcript_path(record.get("transcript_path"))
        )
        if terminal:
            skipped_count += 1
            if video_event:
                video_event("finished", channel_url, video.video_id, video.title, IngestionResult(
                    video.video_id, video.canonical_url, video.title, "COMPLETED", None, None, None
                ))
            report(f"{channel_url}: already downloaded {video.video_id}; skipping")
        else:
            pending_videos.append(video)

    with IngestionState(state_path) as state, _registry_scope(registry):
        to_process = []
        for index, video in enumerate(pending_videos, start=1):
            state_record = state.record_for(video.video_id)
            if state_record and state_record["status"] == "COMPLETED" and is_valid_transcript_path(state_record.get("transcript_path")):
                skipped_count += 1
                if video_event:
                    video_event("finished", channel_url, video.video_id, video.title, IngestionResult(
                        video.video_id, video.canonical_url, video.title, "COMPLETED", None, None, None
                    ))
                report(f"[{index}/{len(candidate_videos)}] Skipping completed {video.video_id}")
            else:
                to_process.append(video)

        def process_video(video):
            if video_event:
                video_event("started", channel_url, video.video_id, video.title, None)
            report(f"{channel_url}: ingesting {video.video_id}: {video.title or video.canonical_url}")
            video_output = root / "videos" / content_folder_name(
                video.published_at, video.video_id
            )
            video_report = (lambda message, video_id=video.video_id: progress(f"[{video_id}] {message}")) if progress else None
            return video, ingest_fn(
                video.canonical_url,
                video_output,
                whisper_script=whisper_script,
                yt_dlp=yt_dlp,
                auth_args=auth_args,
                model=model,
                language=language,
                runner=runner,
                logger=logger,
                download_limiter=download_limiter,
                transcription_limiter=transcription_limiter,
                progress=video_report,
            )

        processed = {}
        with ThreadPoolExecutor(max_workers=video_workers) as executor:
            future_videos = {
                executor.submit(process_video, video): video for video in to_process
            }
            for future in as_completed(future_videos):
                video = future_videos[future]
                try:
                    _, result = future.result()
                except Exception as exc:
                    result = IngestionResult(
                        video.video_id, video.canonical_url, video.title,
                        "FAILED_INGESTION", None, None, str(exc)
                    )
                processed[video.video_id] = result
                if video_event:
                    video_event("finished", channel_url, video.video_id, video.title, result)

        for video in to_process:
            result = processed[video.video_id]
            state.record(
                video_id=video.video_id,
                canonical_url=video.canonical_url,
                title=video.title,
                published_at=video.published_at,
                result=result,
            )
            registry.record_content(
                platform=platform,
                source_key=registry_source_key,
                content_id=video.video_id,
                canonical_url=video.canonical_url,
                published_at=video.published_at,
                status=result.status,
                transcript_path=result.transcript_path,
                error=result.error,
            )
            item = {
                "channel_url": channel_url,
                "video_id": video.video_id,
                "canonical_url": video.canonical_url,
                "published_at": video.published_at,
                "title": video.title,
                **result.to_dict(),
            }
            videos.append(item)
            if result.status == "COMPLETED":
                completed_count += 1
                if result.subtitle_method == "whispermlx":
                    handled_fallback_count += 1
            elif result.status == "SKIPPED_SHORT_NO_SPEECH":
                warnings.append(
                    f"SHORT_VIDEO_NO_SPEECH:{video.video_id}: {result.error or 'empty subtitles'}"
                )
                report(
                    f"Warning recorded for {channel_url} / {video.video_id}: "
                    f"{result.error or 'short video has no speech'}"
                )
            else:
                failure = {
                    "stage": "video_ingestion",
                    "video_id": video.video_id,
                    "canonical_url": video.canonical_url,
                    "status": result.status,
                    "error": result.error,
                }
                failures.append(failure)
                report(
                    f"Failure recorded for {channel_url} / {video.video_id}: "
                    f"{result.status}: {result.error or 'no error details provided'}"
                )

        report(
            f"{channel_url}: {skipped_count} already downloaded, "
            f"{len(to_process)} pending ingestion"
        )

    status = "COMPLETED" if not failures else "COMPLETED_WITH_FAILURES"
    result = ChannelIngestionResult(
        channel_url,
        status,
        len(candidate_videos),
        completed_count,
        len(failures),
        len(dict.fromkeys(warnings)),
        handled_fallback_count,
        skipped_count,
        tuple(videos),
        tuple(warnings),
        tuple(failures),
        str(report_path),
    )
    try:
        _write_report(report_path, result)
    finally:
        registry.close()
    if logger:
        logger.event(
            operation="ingest_channel",
            stage="summary",
            category=status_category(result.status),
            status=result.status,
            output={"channel_url": result.channel_url, "status": result.status,
                    "discovered": result.discovered_count, "completed": result.completed_count,
                    "failed": result.failure_count, "warnings": result.warning_count,
                    "already_downloaded": result.skipped_count,
                    "failure_video_ids": [item["video_id"] for item in result.failures]},
            artifact_paths=[str(report_path)],
        )
    report(
        f"Channel ingestion complete: discovered={len(candidate_videos)}, "
        f"new={len(candidate_videos) - skipped_count}, already_downloaded={skipped_count}, "
        f"completed={completed_count}, failed={len(failures)}"
    )
    return result
