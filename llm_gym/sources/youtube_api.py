"""Fast YouTube channel discovery using YouTube Data API v3."""

from __future__ import annotations

import json
import os
import time as time_module
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable
from urllib.parse import parse_qs, quote, urlsplit
from urllib.error import URLError
from urllib.request import Request, urlopen

from ..shared.config import load_dotenv
from .discovery import DiscoveredVideo, DiscoveryResult
from ..shared.settings import ingestion_parameters
from ..shared.time_utils import normalize_datetime, normalize_until


JsonOpener = Callable[..., object]


def _channel_selector(channel_url: str) -> tuple[str, str]:
    parts = urlsplit(channel_url)
    path = parts.path.strip("/")
    segments = path.split("/") if path else []

    if segments and segments[0].startswith("@"):
        return "forHandle", segments[0]
    if len(segments) >= 2 and segments[0] == "channel":
        return "id", segments[1]
    if len(segments) >= 2 and segments[0] == "user":
        return "forUsername", segments[1]
    if channel_url.startswith("UC"):
        return "id", channel_url
    raise ValueError("channel URL must contain an @handle, /channel/ID, /user/name, or channel ID")


def _request_json(
    endpoint: str,
    params: dict[str, str],
    api_key: str,
    opener: JsonOpener,
) -> dict[str, object]:
    query = "&".join(f"{quote(key)}={quote(value)}" for key, value in {**params, "key": api_key}.items())
    request = Request(f"https://www.googleapis.com/youtube/v3/{endpoint}?{query}")
    last_error = None
    for attempt in range(3):
        try:
            with opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == 2:
                raise RuntimeError(f"YouTube API transport failed after 3 attempts: {exc}") from exc
            time_module.sleep(0.25 * (2**attempt))
    else:
        raise RuntimeError(f"YouTube API transport failed: {last_error}")
    if not isinstance(payload, dict):
        raise RuntimeError("YouTube API returned a non-object response")
    if "error" in payload:
        error = payload["error"]
        raise RuntimeError(f"YouTube API error: {error}")
    return payload


def discover_channel_videos_api(
    channel_url: str,
    *,
    window_days: int | None = None,
    as_of: date | None = None,
    since: datetime | None = None,
    since_exclusive: bool = False,
    until: datetime | date | None = None,
    order: str = "oldest_first",
    all_history: bool = False,
    api_key: str | None = None,
    opener: JsonOpener = urlopen,
    progress: Callable[[str], None] | None = None,
    **_ignored,
) -> DiscoveryResult:
    """Discover recent uploads using the official YouTube Data API."""

    configured = ingestion_parameters()
    max_window = configured["max_window_days"]
    default_window = configured["default_window_days"]
    if not all_history and window_days is not None and not 1 <= window_days <= max_window:
        raise ValueError(f"window_days must be between 1 and {max_window}")
    if order not in {"oldest_first", "newest_first"}:
        raise ValueError("order must be oldest_first or newest_first")

    load_dotenv()
    key = api_key or os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise ValueError("YOUTUBE_API_KEY is not configured")

    effective_as_of = as_of or datetime.now(timezone.utc).date()
    if until is None:
        effective_until = datetime.combine(effective_as_of, time.max, tzinfo=timezone.utc)
    else:
        effective_until = normalize_until(until)
    requested_cutoff = normalize_datetime(since, field="since") if since else effective_until - timedelta(days=window_days or default_window)
    if requested_cutoff > effective_until:
        raise ValueError("since must be earlier than until")
    cutoff = datetime.min.replace(tzinfo=timezone.utc) if all_history else max(requested_cutoff, effective_until - timedelta(days=max_window))
    cutoff_date = cutoff.date()
    effective_window_days = 0 if all_history else max(1, (effective_until.date() - cutoff.date()).days)
    warnings: list[str] = []
    if not all_history and cutoff != requested_cutoff:
        warnings.append("SINCE_CLAMPED_TO_MAX_WINDOW")

    if progress:
        progress(f"Discovering channel with YouTube Data API: {channel_url}")

    selector, value = _channel_selector(channel_url)
    channel_payload = _request_json(
        "channels",
        {"part": "contentDetails,snippet", selector: value},
        key,
        opener,
    )
    channels = channel_payload.get("items") or []
    if not channels:
        result = DiscoveryResult(
            channel_url,
            cutoff.isoformat(),
            effective_as_of.isoformat(),
            effective_window_days,
            order,
            "FAILED_DISCOVERY",
            (),
            warnings=(),
            error="YouTube API returned no matching channel",
        )
        return result

    channel = channels[0]
    uploads_id = (
        channel.get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads")
    )
    if not uploads_id:
        return DiscoveryResult(
            channel_url,
            cutoff.isoformat(),
            effective_as_of.isoformat(),
            effective_window_days,
            order,
            "FAILED_DISCOVERY",
            (),
            warnings=(),
            error="YouTube API channel did not expose an uploads playlist",
        )

    videos: list[DiscoveredVideo] = []
    page_token: str | None = None
    pages = 0
    while True:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": str(uploads_id),
            "maxResults": "50",
        }
        if page_token:
            params["pageToken"] = page_token
        playlist_payload = _request_json("playlistItems", params, key, opener)
        pages += 1
        items = playlist_payload.get("items") or []
        if progress:
            progress(f"API page {pages}: received {len(items)} upload entries")

        reached_cutoff = False
        for item in items:
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            video_id = content.get("videoId") or snippet.get("resourceId", {}).get("videoId")
            published_value = content.get("videoPublishedAt")
            if not video_id or not published_value:
                warnings.append("SKIPPED_ITEM_WITHOUT_VIDEO_DATE")
                continue
            try:
                published = datetime.fromisoformat(str(published_value).replace("Z", "+00:00"))
            except ValueError:
                warnings.append(f"SKIPPED_INVALID_DATE:{video_id}")
                continue
            if published.tzinfo is None:
                warnings.append(f"SKIPPED_TIMEZONELESS_DATE:{video_id}")
                continue
            published = published.astimezone(timezone.utc)
            if not all_history and (published < cutoff or (since_exclusive and published == cutoff)):
                reached_cutoff = True
                break
            if published > effective_until:
                continue
            videos.append(
                DiscoveredVideo(
                    video_id=str(video_id),
                    canonical_url=f"https://www.youtube.com/watch?v={video_id}",
                    title=snippet.get("title") if isinstance(snippet.get("title"), str) else None,
                    published_at=published.isoformat(),
                    channel_url=channel_url,
                )
            )

        if reached_cutoff:
            break
        page_token = playlist_payload.get("nextPageToken")
        if not page_token:
            break

    videos.sort(key=lambda video: (video.published_at, video.video_id), reverse=order == "newest_first")
    if not videos:
        warnings.append("NO_NEW_VIDEOS")
    return DiscoveryResult(
        channel_url,
        cutoff.isoformat(),
        effective_as_of.isoformat(),
        effective_window_days,
        order,
        "COMPLETED",
        tuple(videos),
        warnings=tuple(dict.fromkeys(warnings)),
    )
