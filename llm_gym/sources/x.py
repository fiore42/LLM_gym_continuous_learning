"""X post ingestion using the official X API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from ..shared.atomic import atomic_write_text
from ..shared.run_log import RunLogger
from .source_registry import SourceRegistry
from .storage import content_folder_name
from ..shared.settings import estimate_x_api_cost
from .x_api import XApiError, discover_user_posts_with_includes, resolve_user_id
from .x_media import persist_post_assets
from .x_transcription import transcribe_post_videos


@dataclass(frozen=True)
class XIngestionResult:
    channel_url: str
    status: str
    discovered_count: int
    completed_count: int
    failure_count: int
    warning_count: int
    handled_fallback_count: int
    skipped_count: int
    videos: tuple[dict[str, object], ...]
    warnings: tuple[str, ...]
    failures: tuple[dict[str, object], ...]
    report_path: str
    error: str | None = None
    api_post_reads: int = 0
    api_user_lookups: int = 0
    estimated_api_cost_usd: float = 0.0
    media_download_count: int = 0
    document_download_count: int = 0
    transcript_download_count: int = 0

    def to_dict(self):
        return asdict(self)


def ingest_x_source(
    source_url: str,
    output_dir: str | Path,
    *,
    handle: str,
    source_registry_path: str | Path,
    since: datetime | None = None,
    until: datetime | None = None,
    force: bool = False,
    logger: RunLogger | None = None,
) -> XIngestionResult:
    root = Path(output_dir)
    report_path = root / "channel-ingestion-report.json"
    registry = SourceRegistry(source_registry_path)
    registry.ensure_source(platform="x", source_key=source_url, source_type="account", canonical_url=source_url)
    api_user_lookups = 0
    api_post_reads = 0
    used_user_context = False
    try:
        effective_since = since
        since_exclusive = False
        if not force:
            latest = registry.latest_terminal_published_at(platform="x", source_key=source_url)
            if latest:
                latest_dt = datetime.fromisoformat(latest)
                if effective_since is None or latest_dt > effective_since:
                    effective_since = latest_dt
                since_exclusive = True
        user_id = registry.x_user_id(handle)
        if user_id is None:
            user_id = resolve_user_id(handle)
            api_user_lookups = 1
            registry.cache_x_user_id(handle, user_id)
        try:
            posts, includes = discover_user_posts_with_includes(
                handle, since=effective_since, until=until,
                user_id=user_id, since_exclusive=since_exclusive,
            )
        except XApiError as exc:
            user_token = os.environ.get("X_API_USER_ACCESS_TOKEN")
            if exc.problem_type != "https://api.x.com/2/problems/not-authorized-for-resource" or not user_token:
                raise
            posts, includes = discover_user_posts_with_includes(
                handle, since=effective_since, until=until,
                user_id=user_id, since_exclusive=since_exclusive,
                access_token=user_token,
            )
            used_user_context = True
        api_post_reads = len(posts)
        completed = skipped = failed = 0
        asset_warnings: list[str] = []
        failures: list[dict[str, object]] = []
        media_downloads = document_downloads = 0
        transcript_downloads = 0
        items = []
        for post in posts:
            post_id = str(post["id"])
            published_at = str(post.get("created_at"))
            canonical_url = f"https://x.com/{handle.lstrip('@')}/status/{post_id}"
            if registry.has_terminal_content(platform="x", source_key=source_url, content_id=post_id):
                skipped += 1
                continue
            folder = root / "posts" / content_folder_name(published_at, post_id)
            folder.mkdir(parents=True, exist_ok=True)
            atomic_write_text(folder / "post.json", json.dumps(post, indent=2, ensure_ascii=False) + "\n")
            media_count, document_count, warnings = persist_post_assets(folder, post, includes)
            media_downloads += media_count
            document_downloads += document_count
            asset_warnings.extend(f"{post_id}:{warning}" for warning in warnings)
            transcript_count, transcript_failures, transcript_warnings = transcribe_post_videos(
                folder, post, includes
            )
            transcript_downloads += transcript_count
            asset_warnings.extend(f"{post_id}:{warning}" for warning in transcript_warnings)
            if transcript_failures:
                failed += 1
                for failure in transcript_failures:
                    failures.append({
                        "stage": "x_video_transcription",
                        "video_id": post_id,
                        "status": "FAILED_TRANSCRIPTION",
                        "error": failure,
                    })
                items.append({"channel_url": source_url, "post_id": post_id,
                              "canonical_url": canonical_url, "published_at": published_at,
                              "text": post.get("text"), "status": "FAILED_TRANSCRIPTION"})
                continue
            atomic_write_text(folder / ".complete", "completed\n")
            registry.record_content(platform="x", source_key=source_url, content_id=post_id,
                                    canonical_url=canonical_url, published_at=published_at,
                                    status="COMPLETED")
            completed += 1
            items.append({"channel_url": source_url, "post_id": post_id,
                          "canonical_url": canonical_url, "published_at": published_at,
                          "text": post.get("text"), "status": "COMPLETED"})
        auth_warnings = ("USED_USER_CONTEXT_AUTH",) if used_user_context else ()
        asset_warning_values = tuple(asset_warnings)
        all_warnings = auth_warnings + asset_warning_values
        result_status = "COMPLETED_WITH_FAILURES" if failed else "COMPLETED"
        result = XIngestionResult(source_url, result_status, len(posts), completed, failed,
                                  len(all_warnings),
                                  1 if used_user_context else 0,
                                  skipped, tuple(items), all_warnings, tuple(failures), str(report_path), None,
                                  api_post_reads, api_user_lookups,
                                  estimate_x_api_cost(post_reads=api_post_reads,
                                                      user_lookups=api_user_lookups),
                                  media_downloads, document_downloads, transcript_downloads)
    except Exception as exc:
        result = XIngestionResult(source_url, "FAILED_DISCOVERY", 0, 0, 1, 0, 0, 0,
                                  (), (), ({"stage": "x_ingestion", "error": str(exc)},),
                                  str(report_path), str(exc), api_post_reads,
                                  api_user_lookups,
                                  estimate_x_api_cost(post_reads=api_post_reads,
                                                      user_lookups=api_user_lookups))
    finally:
        registry.close()
    atomic_write_text(report_path, json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n")
    if logger:
        logger.event(operation="ingest_x_source", stage="summary",
                     category="FAILURE" if result.failure_count else "INFO",
                     status=result.status, output={"source": source_url,
                     "discovered": result.discovered_count, "completed": result.completed_count,
                     "failed": result.failure_count}, artifact_paths=[str(report_path)])
    return result
