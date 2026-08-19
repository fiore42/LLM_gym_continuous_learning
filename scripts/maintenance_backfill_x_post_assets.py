#!/usr/bin/env python3
"""Backfill X media, linked documents, and article metadata for saved posts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.shared.atomic import atomic_write_text
from llm_gym.shared.config import load_dotenv
from llm_gym.sources.x_api import XApiError, lookup_posts_with_includes
from llm_gym.sources.x_media import persist_post_assets
from llm_gym.sources.x_transcription import transcribe_post_videos


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default="source/x")
    parser.add_argument("--handle", help="Only backfill one handle, without @")
    parser.add_argument("--limit", type=int, help="Limit the number of post records")
    args = parser.parse_args()
    root = Path(args.source_root)
    pattern = f"{args.handle.lstrip('@')}/posts/*/post.json" if args.handle else "*/posts/*/post.json"
    files = sorted(root.glob(pattern))
    if args.limit is not None:
        files = files[:args.limit]
    bearer = os.environ.get("X_API_BEARER_TOKEN")
    user_token = os.environ.get("X_API_USER_ACCESS_TOKEN")
    if not bearer:
        raise SystemExit("X_API_BEARER_TOKEN is required")
    updated = media = documents = transcripts = warnings = failures = 0
    grouped: dict[str, list[Path]] = {}
    for path in files:
        # Keep one handle per API batch. A protected post from one handle must
        # not force unrelated public posts into the user-context retry path.
        handle = path.parents[2].name
        grouped.setdefault(handle, []).append(path)
    processed = 0
    for handle, handle_files in grouped.items():
        for start in range(0, len(handle_files), 100):
            batch = handle_files[start:start + 100]
            records = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in batch]
            ids = [str(post["id"]) for _, post in records]
            try:
                posts, includes = lookup_posts_with_includes(ids, access_token=bearer)
            except XApiError as exc:
                if not user_token or exc.problem_type != "https://api.x.com/2/problems/not-authorized-for-resource":
                    raise
                posts, includes = lookup_posts_with_includes(ids, access_token=user_token)
            by_id = {str(post["id"]): post for post in posts}
            for path, old_post in records:
                post = by_id.get(str(old_post["id"]))
                if not post:
                    warnings += 1
                    continue
                atomic_write_text(path, json.dumps(post, indent=2, ensure_ascii=False) + "\n")
                media_count, document_count, asset_warnings = persist_post_assets(path.parent, post, includes)
                transcript_count, transcript_failures, transcript_warnings = transcribe_post_videos(
                    path.parent, post, includes
                )
                updated += 1
                media += media_count
                documents += document_count
                transcripts += transcript_count
                warnings += len(asset_warnings) + len(transcript_warnings)
                failures += len(transcript_failures)
                for failure in transcript_failures:
                    print(f"Transcription failure for {path.parent.name}/{post['id']}: {failure}")
                for warning in (*asset_warnings, *transcript_warnings):
                    print(f"Asset warning for {path.parent.name}/{post['id']}: {warning}")
            processed += len(batch)
            print(f"Backfilled {processed}/{len(files)} posts ({handle})")
    print(f"Complete: updated={updated}, media={media}, documents={documents}, transcripts={transcripts}, warnings={warnings}, failures={failures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
