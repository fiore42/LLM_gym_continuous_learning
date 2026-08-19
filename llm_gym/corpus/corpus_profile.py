"""Deterministic inventory of downloaded source content."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EXCLUDED_DIRS = {"audio", "video", "logs", "temporary-audio", ".git"}
EXCLUDED_SUFFIXES = {".mp3", ".m4a", ".aac", ".opus", ".wav", ".mp4", ".m4v", ".webm", ".mov", ".jsonl"}
TEXT_SUFFIXES = {".srt", ".vtt", ".ttml", ".ass", ".txt", ".md", ".json", ".csv"}


def _walk_artifacts(root: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for path in root.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue
        counts[path.suffix.lower() or "[no_extension]"] += 1
    return dict(sorted(counts.items()))


def profile_corpus(source_root: str | Path = "source") -> dict[str, Any]:
    """Return a machine-readable corpus inventory without reading media/logs."""
    root = Path(source_root)
    profile: dict[str, Any] = {
        "profile_version": 1,
        "source_root": str(root),
        "excluded": {"directories": sorted(EXCLUDED_DIRS), "suffixes": sorted(EXCLUDED_SUFFIXES)},
        "total_items": 0,
        "status_counts": {},
        "platform_counts": {},
        "sources": [],
        "artifact_extension_counts": _walk_artifacts(root) if root.is_dir() else {},
    }
    if not root.is_dir():
        return profile

    source_rows: defaultdict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"platform": "", "source": "", "items": 0, "status_counts": Counter(), "transcript_count": 0, "document_count": 0, "post_record_count": 0}
    )
    for state_path in root.rglob("ingestion-state.sqlite3"):
        if any(part in EXCLUDED_DIRS for part in state_path.parts):
            continue
        relative = state_path.relative_to(root)
        if len(relative.parts) < 3:
            continue
        platform, source = relative.parts[0], relative.parts[1]
        row = source_rows[(platform, source)]
        row["platform"] = platform
        row["source"] = source
        try:
            import sqlite3
            connection = sqlite3.connect(state_path)
            try:
                records = connection.execute("SELECT status, transcript_path FROM videos").fetchall()
            finally:
                connection.close()
        except Exception as exc:
            row["state_error"] = str(exc)
            continue
        row["items"] += len(records)
        row["status_counts"].update(str(status) for status, _ in records)
        row["transcript_count"] += sum(bool(transcript) for _, transcript in records)

    for post_path in root.glob("x/*/posts/*/post.json"):
        parts = post_path.relative_to(root).parts
        if len(parts) >= 4:
            row = source_rows[("x", parts[1])]
            row["platform"] = "x"
            row["source"] = parts[1]
            row["post_record_count"] += 1

    for source_dir in root.glob("*/**"):
        if not source_dir.is_dir() or source_dir.name in EXCLUDED_DIRS:
            continue
        parts = source_dir.relative_to(root).parts
        if len(parts) != 2 or parts[0] not in {"youtube", "x"}:
            continue
        row = source_rows[(parts[0], parts[1])]
        row["platform"] = parts[0]
        row["source"] = parts[1]
        row["document_count"] += sum(
            1 for path in source_dir.rglob("*")
            if path.is_file() and "documents" in path.parts and path.suffix.lower() not in EXCLUDED_SUFFIXES
        )

    normalized_sources = []
    status_counts: Counter[str] = Counter()
    platform_counts: Counter[str] = Counter()
    for key in sorted(source_rows):
        row = source_rows[key]
        row["status_counts"] = dict(sorted(row["status_counts"].items()))
        normalized_sources.append(row)
        profile["total_items"] += row["items"] or row["post_record_count"]
        status_counts.update(row["status_counts"])
        platform_counts[row["platform"]] += 1
    profile["sources"] = normalized_sources
    profile["status_counts"] = dict(sorted(status_counts.items()))
    profile["platform_counts"] = dict(sorted(platform_counts.items()))
    return profile


def write_profile(profile: dict[str, Any], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
