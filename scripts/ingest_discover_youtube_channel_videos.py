#!/usr/bin/env python3
"""Discover recent videos from one YouTube channel without downloading media."""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.sources.discovery import discover_channel_videos
from llm_gym.shared.atomic import atomic_write_text
from llm_gym.shared.config import load_dotenv
from llm_gym.sources.source_registry import SourceRegistry
from llm_gym.shared.run_log import RunLogger
from llm_gym.sources.youtube_api import discover_channel_videos_api
from llm_gym.shared.settings import ingestion_parameters, tool_parameters
from llm_gym.shared.status import exit_code, status_category


def main() -> int:
    load_dotenv()
    global_ingestion = ingestion_parameters()
    global_tools = tool_parameters()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel_url", help="YouTube channel URL")
    parser.add_argument("--days", type=int, default=None, help="Explicit ingestion window")
    parser.add_argument("--since", help="Explicit ISO-8601 lower timestamp")
    parser.add_argument("--until", help="Explicit ISO-8601 upper timestamp")
    parser.add_argument("--force", action="store_true", help="Ignore the local cursor and recheck the configured window")
    parser.add_argument(
        "--order",
        choices=("oldest_first", "newest_first"),
        default="oldest_first",
    )
    parser.add_argument("--as-of", help="Testing date in YYYY-MM-DD format")
    parser.add_argument("--browser", help="Browser for yt-dlp cookies")
    parser.add_argument("--report", help="Optional JSON report path")
    parser.add_argument("--source-registry", default="data/source-registry.sqlite3")
    parser.add_argument("--run-log", default="data/run-log.jsonl", help="Shared chronological run log")
    parser.add_argument("--yt-dlp", default=global_tools["yt_dlp"])
    parser.add_argument(
        "--noout",
        action="store_true",
        help="Suppress normal output; preserve exit code and report files",
    )
    args = parser.parse_args()
    if args.days is not None and not 1 <= args.days <= global_ingestion["max_window_days"]:
        parser.error(f"--days must be between 1 and {global_ingestion['max_window_days']}")

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    since = datetime.fromisoformat(args.since) if args.since else None
    until = datetime.fromisoformat(args.until) if args.until else None
    if args.days is not None and since is not None:
        parser.error("--days and --since cannot be used together")
    auth_args = ("--cookies-from-browser", args.browser) if args.browser else ()
    logger = RunLogger(args.run_log)
    logger.event(
        operation="discover_youtube_channel",
        stage="start",
        parameters={"channel_url": args.channel_url, "argv_days": args.days, "argv_since": args.since},
    )

    def report(message: str) -> None:
        if not args.noout:
            print(message, flush=True)

    registry = SourceRegistry(args.source_registry)
    registry.ensure_source(
        platform="youtube",
        source_key=args.channel_url,
        source_type="channel",
        canonical_url=args.channel_url,
    )
    effective_since = since
    effective_days = args.days
    if not args.force and effective_since is None and effective_days is None:
        latest = registry.latest_terminal_published_at(
            platform="youtube", source_key=args.channel_url
        )
        if latest:
            effective_since = datetime.fromisoformat(latest)
            report(f"Incremental discovery: checking content since {latest}")
        else:
            effective_days = global_ingestion["default_window_days"]
            report(f"New source: checking the previous {effective_days} days")
    since_exclusive = bool(not args.force and effective_since is not None)

    discover_fn = discover_channel_videos_api if os.environ.get("YOUTUBE_API_KEY") else discover_channel_videos
    result = None
    try:
        result = discover_fn(
            args.channel_url,
            window_days=effective_days,
            as_of=as_of,
            since=effective_since,
            since_exclusive=since_exclusive,
            until=until,
            order=args.order,
            yt_dlp=args.yt_dlp,
            auth_args=auth_args,
            progress=report,
        )
    except Exception as exc:
        logger.event(operation="discover_youtube_channel", stage="exception", category="FAILURE",
                     status="FAILED_DISCOVERY", parameters={"channel_url": args.channel_url}, error=str(exc))
        if not args.noout:
            print(f"Discovery failed: {exc}", file=sys.stderr)
        return 1
    finally:
        registry.close()
    payload = result.to_dict()
    logger.event(
        operation="discover_youtube_channel",
        stage="summary",
        category=status_category(result.status),
        status=result.status,
        parameters={
            "channel_url": args.channel_url,
            "days": args.days,
            "since": args.since,
            "until": args.until,
            "browser": args.browser,
        },
        output={"channel_url": args.channel_url, "status": result.status,
                "discovered": result.discovered_count, "warnings": result.warning_count,
                "failed": result.failure_count},
        artifact_paths=[args.report] if args.report else [],
    )

    if args.report:
        report_path = Path(args.report)
        atomic_write_text(report_path, json.dumps(payload, indent=2) + "\n")
    if not args.noout:
        print(json.dumps(payload, indent=2))
    return exit_code(result.status)


if __name__ == "__main__":
    raise SystemExit(main())
