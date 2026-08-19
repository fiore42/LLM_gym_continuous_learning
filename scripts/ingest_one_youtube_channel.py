#!/usr/bin/env python3
"""Discover and ingest recent videos from one YouTube channel."""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.sources.channel import ingest_channel
from llm_gym.shared.atomic import atomic_write_text
from llm_gym.shared.config import load_dotenv
from llm_gym.sources.youtube_api import discover_channel_videos_api
from llm_gym.shared.run_log import RunLogger
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
    parser.add_argument("--force", action="store_true", help="Recheck the configured window, ignoring the local cursor")
    parser.add_argument("--all-history", action="store_true", help="One-off full channel backfill; bypasses the global date cutoff")
    parser.add_argument("--order", choices=("oldest_first", "newest_first"), default="oldest_first")
    parser.add_argument("--as-of", help="Testing date in YYYY-MM-DD format")
    parser.add_argument("--browser", help="Browser for yt-dlp cookies")
    parser.add_argument("--output", default="data/channel-ingestion")
    parser.add_argument("--source-registry", default="data/source-registry.sqlite3")
    parser.add_argument("--run-log", default="data/run-log.jsonl", help="Shared chronological run log")
    parser.add_argument("--yt-dlp", default=global_tools["yt_dlp"])
    parser.add_argument(
        "--whisper-script",
        default=global_tools["whisper_script"],
    )
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="en")
    parser.add_argument("--noout", action="store_true", help="Suppress normal output")
    args = parser.parse_args()
    if args.days is not None and not args.all_history and not 1 <= args.days <= global_ingestion["max_window_days"]:
        parser.error(f"--days must be between 1 and {global_ingestion['max_window_days']}")

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    since = datetime.fromisoformat(args.since) if args.since else None
    until = datetime.fromisoformat(args.until) if args.until else None
    auth_args = ("--cookies-from-browser", args.browser) if args.browser else ()
    logger = RunLogger(args.run_log)
    logger.event(
        operation="ingest_youtube_channel_script",
        stage="start",
        parameters={
            "channel_url": args.channel_url,
            "argv_days": args.days,
            "argv_since": args.since,
            "until": args.until,
            "browser": args.browser,
            "yt_dlp": args.yt_dlp,
            "whisper_script": args.whisper_script,
            "model": args.model,
            "language": args.language,
            "output": args.output,
        },
    )

    def report(message: str) -> None:
        if not args.noout:
            print(message, flush=True)

    discover_fn = discover_channel_videos_api if os.environ.get("YOUTUBE_API_KEY") else None
    kwargs = {"discover_fn": discover_fn} if discover_fn else {}
    try:
        result = ingest_channel(
            args.channel_url, args.output, whisper_script=args.whisper_script,
            window_days=args.days, as_of=as_of, since=since, until=until,
            force=args.force or args.all_history,
            all_history=args.all_history,
            order=args.order, yt_dlp=args.yt_dlp, auth_args=auth_args,
            model=args.model, language=args.language, progress=report,
            source_registry_path=args.source_registry, logger=logger, **kwargs,
        )
    except Exception as exc:
        failure = {
            "status": "FAILED_SOURCE",
            "channel_url": args.channel_url,
            "stage": "source_ingestion",
            "retryable": True,
            "error": str(exc),
            "report_path": str(Path(args.output) / "channel-ingestion-report.json"),
        }
        logger.event(
            operation="ingest_youtube_channel_script",
            stage="source_ingestion",
            category="FAILURE",
            status="FAILED_SOURCE",
            parameters={"channel_url": args.channel_url},
            output=failure,
            error=str(exc),
            artifact_paths=[failure["report_path"]],
        )
        report_path = Path(failure["report_path"])
        atomic_write_text(report_path, json.dumps(failure, indent=2) + "\n")
        if not args.noout:
            print(json.dumps(failure, indent=2), file=sys.stderr)
        return 1
    logger.event(
        operation="ingest_youtube_channel_script",
        stage="summary",
        category=status_category(result.status),
        status=result.status,
        parameters={
            "channel_url": args.channel_url,
            "days": args.days,
            "since": args.since,
            "until": args.until,
            "browser": args.browser,
            "output": args.output,
        },
        output={"channel_url": args.channel_url, "status": result.status,
                "discovered": result.discovered_count, "completed": result.completed_count,
                "failed": result.failure_count, "warnings": result.warning_count},
        artifact_paths=[result.report_path],
    )
    if not args.noout:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return exit_code(result.status)


if __name__ == "__main__":
    raise SystemExit(main())
