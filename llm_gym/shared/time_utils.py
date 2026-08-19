"""Shared timezone-aware timestamp validation and UTC normalization."""

from __future__ import annotations

from datetime import date, datetime, timezone


def normalize_datetime(value: datetime, *, field: str) -> datetime:
    """Require a timezone-aware datetime and return it in UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return value.astimezone(timezone.utc)


def parse_datetime(value: str, *, field: str) -> datetime:
    """Parse an ISO timestamp, requiring an explicit timezone."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    return normalize_datetime(parsed, field=field)


def normalize_until(value: datetime | date, *, field: str = "until") -> datetime:
    """Normalize a timestamp or date upper bound to UTC."""
    if isinstance(value, datetime):
        return normalize_datetime(value, field=field)
    return datetime.combine(value, datetime.max.time(), tzinfo=timezone.utc)
