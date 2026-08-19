"""Shared content-storage conventions for all source adapters."""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit

from ..shared.time_utils import parse_datetime


def canonical_source_url(platform: str, url: str) -> str:
    """Normalize equivalent account/channel URLs for registry identity."""
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return url.strip().rstrip("/")
    path = parts.path.rstrip("/")
    if platform.lower() == "youtube" and path.endswith("/videos"):
        path = path[: -len("/videos")].rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def content_folder_name(published_at: str | date | datetime, content_id: str) -> str:
    """Return the stable date-prefixed directory name for one content item."""
    if isinstance(published_at, datetime):
        published_date = published_at.date()
    elif isinstance(published_at, date):
        published_date = published_at
    else:
        if len(published_at) == 10:
            published_date = date.fromisoformat(published_at)
        else:
            published_date = parse_datetime(published_at, field="published_at").date()
    if not content_id or "/" in content_id or "\\" in content_id:
        raise ValueError("content_id must be a non-empty path-safe identifier")
    return f"{published_date:%Y%m%d}_{content_id}"
