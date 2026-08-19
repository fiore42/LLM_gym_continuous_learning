"""Deterministic, metadata-only discovery of recent YouTube channel videos."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Sequence
from urllib.parse import urlsplit, urlunsplit

from .youtube import CommandRunner
from ..shared.settings import ingestion_parameters
from ..shared.time_utils import normalize_datetime, normalize_until


@dataclass(frozen=True)
class DiscoveredVideo:
    video_id: str
    canonical_url: str
    title: str | None
    published_at: str
    channel_url: str

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveryResult:
    channel_url: str
    cutoff: str
    as_of: str
    window_days: int
    order: str
    status: str
    videos: tuple[DiscoveredVideo, ...]
    skipped_without_date: int = 0
    warnings: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["videos"] = [video.to_dict() for video in self.videos]
        return data


def _run(command: Sequence[str], runner: CommandRunner) -> subprocess.CompletedProcess[str]:
    return runner(list(command), check=False, capture_output=True, text=True)


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _published_at(entry: dict[str, object]) -> datetime | None:
    for key in ("timestamp", "release_timestamp"):
        value = entry.get(key)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)

    for key in ("upload_date", "release_date"):
        value = entry.get(key)
        if isinstance(value, str):
            parsed = _parse_date(value)
            if parsed:
                return parsed
    return None


def _entry_url(entry: dict[str, object], video_id: str) -> str:
    for key in ("webpage_url", "original_url"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return f"https://www.youtube.com/watch?v={video_id}"


def _videos_tab_url(channel_url: str) -> str:
    """Normalize a channel URL to its actual video-upload tab."""

    parts = urlsplit(channel_url)
    path = parts.path.rstrip("/")
    if not path.endswith("/videos"):
        path = f"{path}/videos"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def _enrich_entry(
    entry: dict[str, object],
    yt_dlp: str,
    auth_args: Sequence[str],
    runner: CommandRunner,
) -> tuple[dict[str, object], str | None]:
    """Fetch full metadata for a flat-playlist entry when needed."""

    video_id = entry.get("id")
    if not isinstance(video_id, str) or not video_id:
        return entry, "entry did not contain a video ID"
    url = _entry_url(entry, video_id)
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
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return entry, detail[-500:] or "video metadata lookup failed"
    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError:
        return entry, "video metadata lookup returned invalid JSON"
    if not isinstance(metadata, dict):
        return entry, "video metadata lookup returned no object"
    merged = dict(entry)
    merged.update(metadata)
    return merged, None


def discover_channel_videos(
    channel_url: str,
    *,
    window_days: int | None = None,
    as_of: date | None = None,
    since: datetime | None = None,
    since_exclusive: bool = False,
    until: datetime | date | None = None,
    all_history: bool = False,
    order: str = "oldest_first",
    yt_dlp: str = "yt-dlp",
    auth_args: Sequence[str] = (),
    runner: CommandRunner = subprocess.run,
    progress: Callable[[str], None] | None = None,
) -> DiscoveryResult:
    """Return dated videos from a channel without downloading media.

    The configured maximum window is enforced unless the caller explicitly
    selects ``all_history`` for a deliberate one-off backfill. Videos without
    a verifiable upload date are skipped explicitly.
    """

    if order not in {"oldest_first", "newest_first"}:
        raise ValueError("order must be oldest_first or newest_first")

    configured = ingestion_parameters()
    max_window = configured["max_window_days"]
    default_window = configured["default_window_days"]
    effective_as_of = as_of or datetime.now(timezone.utc).date()
    if until is None:
        effective_until = datetime.combine(
            effective_as_of, datetime.max.time(), tzinfo=timezone.utc
        )
    else:
        effective_until = normalize_until(until)
    requested_cutoff = normalize_datetime(since, field="since") if since is not None else None
    window_warnings: list[str] = []
    if all_history:
        cutoff = datetime.min.replace(tzinfo=timezone.utc)
        effective_window_days = 0
    elif since is not None:
        cutoff = requested_cutoff
        cutoff = max(cutoff, effective_until - timedelta(days=max_window))
        if cutoff != requested_cutoff:
            window_warnings.append("SINCE_CLAMPED_TO_MAX_WINDOW")
        effective_window_days = max(1, (effective_until.date() - cutoff.date()).days)
    else:
        effective_window_days = window_days if window_days is not None else default_window
        if not 1 <= effective_window_days <= max_window:
            raise ValueError(f"window_days must be between 1 and {max_window}")
        cutoff = datetime.combine(
            effective_as_of - timedelta(days=effective_window_days),
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
    if cutoff > effective_until:
        raise ValueError("since must be earlier than until")
    cutoff_date = cutoff.date()

    videos_url = _videos_tab_url(channel_url)
    if progress:
        progress(f"Discovering channel videos: {videos_url}")

    command = [
            yt_dlp,
            *auth_args,
            "--no-warnings",
            "--extractor-args",
            "youtubetab:skip=authcheck",
            "--flat-playlist",
            "--dump-single-json",
            "--skip-download",
            videos_url,
        ]
    if not all_history:
        command[-1:-1] = ["--dateafter", cutoff_date.strftime("%Y%m%d")]
    result = _run(command, runner)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return DiscoveryResult(
            channel_url,
            cutoff.isoformat(),
            effective_as_of.isoformat(),
            effective_window_days,
            order,
            "FAILED_DISCOVERY",
            (),
            warnings=(),
            error=detail[-1000:] or "yt-dlp channel discovery failed",
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return DiscoveryResult(
            channel_url,
            cutoff.isoformat(),
            effective_as_of.isoformat(),
            effective_window_days,
            order,
            "FAILED_DISCOVERY",
            (),
            warnings=(),
            error="yt-dlp returned invalid JSON",
        )

    if not isinstance(payload, dict):
        return DiscoveryResult(
            channel_url,
            cutoff.isoformat(),
            effective_as_of.isoformat(),
            effective_window_days,
            order,
            "FAILED_DISCOVERY",
            (),
            warnings=(),
            error="yt-dlp returned no playlist object",
        )

    videos: list[DiscoveredVideo] = []
    skipped_without_date = 0
    warnings: list[str] = list(window_warnings)
    entries = payload.get("entries", []) or []
    if progress:
        progress(
            f"Found {len(entries)} total channel entries; "
            "checking the complete channel history" if all_history
            else "checking newest entries until the cutoff"
        )

    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        video_id = entry.get("id")
        if not isinstance(video_id, str) or not video_id:
            continue
        published = _published_at(entry)
        if published is None:
            if progress:
                progress(f"[{index}/{len(entries)}] Enriching metadata for {video_id}")
            entry, enrichment_error = _enrich_entry(entry, yt_dlp, auth_args, runner)
            published = _published_at(entry)
            if enrichment_error:
                warnings.append(f"metadata lookup failed for {video_id}: {enrichment_error}")
        if published is None:
            skipped_without_date += 1
            continue
        # The /videos tab is returned newest-first. Once a dated entry is
        # older than the cutoff, later entries are also outside the window.
        if not all_history and (published < cutoff or (since_exclusive and published == cutoff)):
            if progress:
                progress(f"Reached cutoff after checking {index} entries")
            break
        if published > effective_until:
            continue
        videos.append(
            DiscoveredVideo(
                video_id=video_id,
                canonical_url=_entry_url(entry, video_id),
                title=entry.get("title") if isinstance(entry.get("title"), str) else None,
                published_at=published.isoformat(),
                channel_url=channel_url,
            )
        )

    videos.sort(key=lambda item: (item.published_at, item.video_id), reverse=order == "newest_first")
    if not videos:
        warnings.append("NO_NEW_VIDEOS")
    if skipped_without_date:
        warnings.append(f"SKIPPED_WITHOUT_DATE:{skipped_without_date}")
    if progress:
        progress(
            f"Discovery complete: {len(videos)} videos in "
            + ("the complete channel history" if all_history else "the requested window")
        )
    return DiscoveryResult(
        channel_url,
        cutoff.isoformat(),
        effective_as_of.isoformat(),
        effective_window_days,
        order,
        "COMPLETED",
        tuple(videos),
        skipped_without_date=skipped_without_date,
        warnings=tuple(warnings),
    )
