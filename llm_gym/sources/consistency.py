"""Checks that local YouTube state and the central registry agree."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .manifest import load_sources_markdown


TERMINAL_STATUSES = {"COMPLETED", "SKIPPED_SHORT_NO_SPEECH"}


def check_state_registry_consistency(
    *,
    source_root: str | Path = ".",
    registry_path: str | Path = "data/source-registry.sqlite3",
    manifest_path: str | Path = "config/SOURCES.md",
) -> dict[str, Any]:
    """Return a structured consistency report without reading media artifacts."""
    source_root = Path(source_root)
    registry_path = Path(registry_path)
    manifest = load_sources_markdown(manifest_path)
    youtube_sources = [s for s in manifest["sources"] if s["platform"] == "youtube"]
    report: dict[str, Any] = {
        "status": "COMPLETED",
        "checked_sources": len(youtube_sources),
        "checked_items": 0,
        "warnings": [],
        "mismatches": [],
    }
    if not registry_path.is_file():
        report["warnings"].append(f"central registry does not exist: {registry_path}")
        return report

    with closing(sqlite3.connect(registry_path)) as registry:
        local_records: dict[str, dict[str, tuple[object, ...]]] = {}
        for source in youtube_sources:
            state_path = Path(source_root) / str(source["source_folder"]) / "ingestion-state.sqlite3"
            if not state_path.is_file():
                report["warnings"].append(f"no local state database: {state_path}")
                continue
            source_key = str(source["url"])
            state = sqlite3.connect(state_path)
            try:
                local_rows = state.execute(
                    "SELECT video_id, canonical_url, published_at, status FROM videos"
                ).fetchall()
            finally:
                state.close()
            local_records[source_key] = {str(row[0]): row for row in local_rows}
            for video_id, canonical_url, published_at, status in local_rows:
                report["checked_items"] += 1
                central = registry.execute(
                    """SELECT canonical_url, published_at, status
                       FROM source_content
                       WHERE platform='youtube' AND source_key=? AND content_id=?""",
                    (source_key, video_id),
                ).fetchone()
                if central is None:
                    report["mismatches"].append({
                        "source": source_key, "content_id": video_id,
                        "issue": "missing_central_record", "local_status": status,
                    })
                    continue
                central_url, central_published_at, central_status = central
                if (canonical_url, published_at, status) != (
                    central_url, central_published_at, central_status
                ):
                    report["mismatches"].append({
                        "source": source_key, "content_id": video_id,
                        "issue": "field_mismatch",
                        "local": {"canonical_url": canonical_url, "published_at": published_at, "status": status},
                        "central": {"canonical_url": central_url, "published_at": central_published_at, "status": central_status},
                    })

        # Reverse-check registry rows for configured YouTube sources. This
        # catches records that were written centrally but never cached locally.
        source_keys = {str(s["url"]) for s in youtube_sources}
        for source_key, content_id, canonical_url, published_at, status in registry.execute(
            """SELECT source_key, content_id, canonical_url, published_at, status
               FROM source_content WHERE platform='youtube'"""
        ):
            if source_key not in source_keys:
                continue
            if source_key not in local_records:
                continue
            if content_id not in local_records[source_key]:
                report["mismatches"].append({
                    "source": source_key, "content_id": content_id,
                    "issue": "missing_local_record", "central_status": status,
                })

    if report["mismatches"]:
        report["status"] = "FAILED_INCONSISTENT"
    return report
