#!/usr/bin/env python3
"""Reprocess previously skipped short YouTube videos with the visual fallback."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.shared.config import load_dotenv
from llm_gym.sources.source_registry import SourceRegistry
from llm_gym.sources.state import IngestionState
from llm_gym.sources.storage import content_folder_name
from llm_gym.shared.settings import tool_parameters
from llm_gym.sources.youtube import ingest_one_video


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default="source/youtube")
    parser.add_argument("--source-registry", default="data/source-registry.sqlite3")
    parser.add_argument("--browser", help="Browser whose cookies yt-dlp should use")
    parser.add_argument("--whisper-script", help="Whisper executable path override")
    args = parser.parse_args()
    tools = tool_parameters()
    whisper_script = args.whisper_script or tools["whisper_script"]
    auth_args = ["--cookies-from-browser", args.browser] if args.browser else []
    registry = SourceRegistry(args.source_registry)
    repaired = 0
    failures = 0
    try:
        for state_path in sorted(Path(args.source_root).glob("*/ingestion-state.sqlite3")):
            channel_dir = state_path.parent
            with sqlite3.connect(state_path) as connection:
                rows = connection.execute(
                    "SELECT video_id, canonical_url, title, published_at FROM videos "
                    "WHERE status = 'SKIPPED_SHORT_NO_SPEECH' ORDER BY published_at, video_id"
                ).fetchall()
            if not rows:
                continue
            with IngestionState(state_path) as state:
                for video_id, url, title, published_at in rows:
                    folder = channel_dir / "videos" / content_folder_name(published_at, video_id)
                    print(f"Reprocessing {channel_dir.name}/{video_id}: {url}")
                    result = ingest_one_video(
                        url, folder,
                        whisper_script=whisper_script,
                        yt_dlp=tools["yt_dlp"],
                        auth_args=auth_args,
                    )
                    state.record(video_id=video_id, canonical_url=url, title=title,
                                 published_at=published_at, result=result)
                    with sqlite3.connect(args.source_registry) as registry_reader:
                        source_row = registry_reader.execute(
                            "SELECT source_key FROM source_content WHERE platform='youtube' AND content_id=?",
                            (video_id,),
                        ).fetchone()
                    if source_row:
                        registry.record_content(
                            platform="youtube", source_key=source_row[0], content_id=video_id,
                            canonical_url=url, published_at=published_at, status=result.status,
                            transcript_path=result.transcript_path, error=result.error,
                        )
                    if result.status in {"SKIPPED_SHORT_NO_SPEECH", "COMPLETED"}:
                        repaired += 1
                    else:
                        failures += 1
                    print(f"  {result.status}: {result.error or 'ok'}")
    finally:
        registry.close()
    print(f"Complete: repaired={repaired}, unresolved_failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
