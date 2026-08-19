"""Central registry of monitored sources and terminal content decisions."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


_WRITE_LOCK = threading.Lock()
SCHEMA_VERSION = 2


class SourceRegistry:
    """Small SQLite registry shared by YouTube, X, and future adapters."""

    def __init__(self, path: str | Path = "data/source-registry.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30)
        with _WRITE_LOCK:
            current_version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if current_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"source registry schema {current_version} is newer than supported {SCHEMA_VERSION}"
                )
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA busy_timeout=30000")
            self.connection.executescript(
                """
            CREATE TABLE IF NOT EXISTS sources (
                platform TEXT NOT NULL,
                source_key TEXT NOT NULL,
                source_type TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                latest_successful_published_at TEXT,
                -- Legacy column name; stores the latest terminal content timestamp.
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (platform, source_key)
            );

            CREATE TABLE IF NOT EXISTS source_content (
                platform TEXT NOT NULL,
                source_key TEXT NOT NULL,
                content_id TEXT NOT NULL,
                canonical_url TEXT NOT NULL,
                published_at TEXT,
                status TEXT NOT NULL,
                transcript_path TEXT,
                error TEXT,
                downloaded_at TEXT NOT NULL,
                PRIMARY KEY (platform, source_key, content_id),
                FOREIGN KEY (platform, source_key)
                    REFERENCES sources(platform, source_key)
            );

            CREATE INDEX IF NOT EXISTS idx_source_content_published
            ON source_content(platform, source_key, published_at);

            CREATE TABLE IF NOT EXISTS x_users (
                handle TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
                """
            )
            self.connection.commit()
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.connection.commit()

    def ensure_source(
        self,
        *,
        platform: str,
        source_key: str,
        source_type: str,
        canonical_url: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with _WRITE_LOCK:
            existing = self.connection.execute(
                "SELECT canonical_url FROM sources WHERE platform = ? AND source_key = ?",
                (platform, source_key),
            ).fetchone()
            if existing and existing[0] != canonical_url:
                raise ValueError(
                    f"source identity conflict for {platform}:{source_key}: "
                    f"canonical URL changed from {existing[0]} to {canonical_url}"
                )
            self.connection.execute(
                """
                INSERT INTO sources (
                    platform, source_key, source_type, canonical_url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, source_key) DO UPDATE SET
                    canonical_url = excluded.canonical_url,
                    updated_at = excluded.updated_at
                """,
                (platform, source_key, source_type, canonical_url, now, now),
            )
            self.connection.commit()

    def latest_terminal_published_at(self, *, platform: str, source_key: str) -> str | None:
        """Return the newest completed or intentionally skipped publication."""
        row = self.connection.execute(
            """
            SELECT latest_successful_published_at
            FROM sources
            WHERE platform = ? AND source_key = ?
            """,
            (platform, source_key),
        ).fetchone()
        return row[0] if row else None

    def x_user_id(self, handle: str) -> str | None:
        """Return the cached stable X user ID for a handle, if known."""
        row = self.connection.execute(
            "SELECT user_id FROM x_users WHERE handle = ?",
            (handle.lstrip("@").lower(),),
        ).fetchone()
        return row[0] if row else None

    def cache_x_user_id(self, handle: str, user_id: str) -> None:
        """Cache a handle-to-ID mapping and reject identity changes."""
        key = handle.lstrip("@").lower()
        now = datetime.now(timezone.utc).isoformat()
        with _WRITE_LOCK:
            existing = self.connection.execute(
                "SELECT user_id FROM x_users WHERE handle = ?", (key,)
            ).fetchone()
            if existing and existing[0] != user_id:
                raise ValueError(f"X user identity conflict for @{key}")
            self.connection.execute(
                """INSERT INTO x_users(handle, user_id, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(handle) DO UPDATE SET user_id = excluded.user_id,
                   updated_at = excluded.updated_at""",
                (key, user_id, now),
            )
            self.connection.commit()

    def latest_successful_published_at(self, *, platform: str, source_key: str) -> str | None:
        """Compatibility alias for the legacy database column name."""
        return self.latest_terminal_published_at(platform=platform, source_key=source_key)

    def has_terminal_content(self, *, platform: str, source_key: str, content_id: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1 FROM source_content
            WHERE platform = ? AND source_key = ? AND content_id = ?
              AND status IN ('COMPLETED', 'SKIPPED_SHORT_NO_SPEECH')
            """,
            (platform, source_key, content_id),
        ).fetchone()
        return row is not None

    def content_record(self, *, platform: str, source_key: str, content_id: str) -> dict[str, object] | None:
        row = self.connection.execute(
            """SELECT status, transcript_path FROM source_content
               WHERE platform = ? AND source_key = ? AND content_id = ?""",
            (platform, source_key, content_id),
        ).fetchone()
        return {"status": row[0], "transcript_path": row[1]} if row else None

    def has_successful_content(self, *, platform: str, source_key: str, content_id: str) -> bool:
        """Backward-compatible alias for callers using the old name."""
        return self.has_terminal_content(
            platform=platform, source_key=source_key, content_id=content_id
        )

    def record_content(
        self,
        *,
        platform: str,
        source_key: str,
        content_id: str,
        canonical_url: str,
        published_at: str | None,
        status: str,
        transcript_path: str | None = None,
        error: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with _WRITE_LOCK:
            existing = self.connection.execute(
                """SELECT canonical_url, published_at FROM source_content
                   WHERE platform = ? AND source_key = ? AND content_id = ?""",
                (platform, source_key, content_id),
            ).fetchone()
            if existing and (existing[0] != canonical_url or existing[1] != published_at):
                raise ValueError(
                    f"content identity conflict for {platform}:{source_key}:{content_id}"
                )
            self.connection.execute(
                """
                INSERT INTO source_content (
                    platform, source_key, content_id, canonical_url, published_at,
                    status, transcript_path, error, downloaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, source_key, content_id) DO UPDATE SET
                    canonical_url = excluded.canonical_url,
                    published_at = excluded.published_at,
                    status = excluded.status,
                    transcript_path = excluded.transcript_path,
                    error = excluded.error,
                    downloaded_at = excluded.downloaded_at
                """,
                (
                    platform,
                    source_key,
                    content_id,
                    canonical_url,
                    published_at,
                    status,
                    transcript_path,
                    error,
                    now,
                ),
            )
            if status in {"COMPLETED", "SKIPPED_SHORT_NO_SPEECH"} and published_at:
                self.connection.execute(
                    """
                    UPDATE sources
                    SET latest_successful_published_at = CASE
                        WHEN latest_successful_published_at IS NULL
                          OR latest_successful_published_at < ? THEN ?
                        ELSE latest_successful_published_at
                    END,
                        updated_at = ?
                    WHERE platform = ? AND source_key = ?
                    """,
                    (published_at, published_at, now, platform, source_key),
                )
            self.connection.commit()

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self) -> "SourceRegistry":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
