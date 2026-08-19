"""Durable state for idempotent ingestion runs."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .youtube import IngestionResult


SCHEMA_VERSION = 1


class IngestionState:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=30000")
        current_version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"ingestion state schema {current_version} is newer than supported {SCHEMA_VERSION}"
            )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                canonical_url TEXT NOT NULL,
                title TEXT,
                published_at TEXT,
                status TEXT NOT NULL,
                subtitle_method TEXT,
                transcript_path TEXT,
                last_error TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()
        self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.connection.commit()

    def status(self, video_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT status FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        return row[0] if row else None

    def record_for(self, video_id: str) -> dict[str, object] | None:
        row = self.connection.execute(
            "SELECT status, transcript_path FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        return {"status": row[0], "transcript_path": row[1]} if row else None

    def record(
        self,
        *,
        video_id: str,
        canonical_url: str,
        title: str | None,
        published_at: str,
        result: IngestionResult,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """
            INSERT INTO videos (
                video_id, canonical_url, title, published_at, status,
                subtitle_method, transcript_path, last_error, attempts, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                canonical_url = excluded.canonical_url,
                title = excluded.title,
                published_at = excluded.published_at,
                status = excluded.status,
                subtitle_method = excluded.subtitle_method,
                transcript_path = excluded.transcript_path,
                last_error = excluded.last_error,
                attempts = videos.attempts + 1,
                updated_at = excluded.updated_at
            """,
            (
                video_id,
                canonical_url,
                title,
                published_at,
                result.status,
                result.subtitle_method,
                result.transcript_path,
                result.error,
                now,
            ),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "IngestionState":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
