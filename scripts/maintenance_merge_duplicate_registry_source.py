#!/usr/bin/env python3
"""Merge one equivalent source-registry key into its canonical key."""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="data/source-registry.sqlite3")
    parser.add_argument("--platform", default="youtube")
    parser.add_argument("--alias", required=True)
    parser.add_argument("--canonical", required=True)
    parser.add_argument("--noout", action="store_true")
    args = parser.parse_args()
    path = Path(args.registry)
    if not path.is_file():
        print(f"Registry not found: {path}", file=sys.stderr)
        return 1
    backup = path.with_name(path.name + ".pre-alias-merge")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        backup_connection = sqlite3.connect(backup)
        try:
            connection.backup(backup_connection)
        finally:
            backup_connection.close()
        try:
            connection.execute("BEGIN")
            alias_source = connection.execute(
                "SELECT source_type, canonical_url, latest_successful_published_at, created_at, updated_at "
                "FROM sources WHERE platform=? AND source_key=?",
                (args.platform, args.alias),
            ).fetchone()
            if alias_source is None:
                raise ValueError(f"alias source not found: {args.platform}:{args.alias}")
            canonical_source = connection.execute(
                "SELECT 1 FROM sources WHERE platform=? AND source_key=?",
                (args.platform, args.canonical),
            ).fetchone()
            if canonical_source is None:
                connection.execute(
                    """INSERT INTO sources(platform, source_key, source_type, canonical_url,
                       latest_successful_published_at, created_at, updated_at)
                       SELECT platform, ?, source_type, ?, latest_successful_published_at,
                              created_at, updated_at FROM sources
                       WHERE platform=? AND source_key=?""",
                    (args.canonical, args.canonical, args.platform, args.alias),
                )
            overlap = connection.execute(
                """SELECT content_id FROM source_content WHERE platform=? AND source_key=?
                   AND content_id IN (SELECT content_id FROM source_content WHERE platform=? AND source_key=?)""",
                (args.platform, args.alias, args.platform, args.canonical),
            ).fetchall()
            if overlap:
                raise ValueError(f"refusing to merge {len(overlap)} overlapping content IDs")
            moved = connection.execute(
                "UPDATE source_content SET source_key=? WHERE platform=? AND source_key=?",
                (args.canonical, args.platform, args.alias),
            ).rowcount
            connection.execute(
                """UPDATE sources SET latest_successful_published_at = CASE
                   WHEN latest_successful_published_at IS NULL THEN
                     (SELECT latest_successful_published_at FROM sources WHERE platform=? AND source_key=?)
                   WHEN (SELECT latest_successful_published_at FROM sources WHERE platform=? AND source_key=?) > latest_successful_published_at
                     THEN (SELECT latest_successful_published_at FROM sources WHERE platform=? AND source_key=?)
                   ELSE latest_successful_published_at END
                   WHERE platform=? AND source_key=?""",
                (args.platform, args.alias, args.platform, args.alias, args.platform, args.alias, args.platform, args.canonical),
            )
            connection.execute("DELETE FROM sources WHERE platform=? AND source_key=?", (args.platform, args.alias))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    if not args.noout:
        print(f"Merged {moved} records: {args.platform}:{args.alias} → {args.platform}:{args.canonical}")
        print(f"Backup: {backup}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"Alias merge failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
