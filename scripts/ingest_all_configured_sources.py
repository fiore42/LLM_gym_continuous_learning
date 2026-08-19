#!/usr/bin/env python3
"""Ingest configured YouTube sources with bounded download concurrency."""

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Semaphore

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.sources.channel import ChannelIngestionResult, ingest_channel
from llm_gym.shared.atomic import atomic_write_text
from llm_gym.shared.config import load_dotenv
from llm_gym.sources.manifest import load_sources_markdown, unsupported_platforms
from llm_gym.shared.progress import ProgressDashboard
from llm_gym.shared.run_log import RunLogger
from llm_gym.shared.settings import ingestion_parameters, tool_parameters
from llm_gym.sources.youtube_api import discover_channel_videos_api
from llm_gym.sources.x import ingest_x_source
from llm_gym.shared.status import exit_code, status_category
from llm_gym.shared.loops import LoopType


def main() -> int:
    load_dotenv()
    global_ingestion = ingestion_parameters()
    global_tools = tool_parameters()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="config/SOURCES.md")
    parser.add_argument("--days", type=int, default=None, help="Explicit ingestion window")
    parser.add_argument("--since", help="Explicit ISO-8601 lower timestamp")
    parser.add_argument("--until", help="Explicit ISO-8601 upper timestamp")
    parser.add_argument("--force", action="store_true", help="Recheck the configured window, ignoring local cursors")
    parser.add_argument("--as-of", help="Testing date in YYYY-MM-DD format")
    parser.add_argument("--browser", help="Browser for yt-dlp cookies")
    parser.add_argument("--max-downloads", type=int, default=3, help="Maximum parallel source download jobs")
    parser.add_argument("--max-transcriptions", type=int, default=1, help="Must remain 1")
    parser.add_argument("--output-root", default=".", help="Project root for derived source folders")
    parser.add_argument("--source-registry", default="data/source-registry.sqlite3")
    parser.add_argument("--run-log", default="data/run-log.jsonl")
    parser.add_argument("--report", default="data/multi-source-report.json")
    parser.add_argument("--full-report", action="store_true", help="Print the complete JSON report")
    parser.add_argument("--yt-dlp", default=global_tools["yt_dlp"])
    parser.add_argument("--whisper-script", default=global_tools["whisper_script"])
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="en")
    parser.add_argument("--noout", action="store_true", help="Suppress normal output")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed per-stage output instead of the single-line dashboard",
    )
    args = parser.parse_args()
    if args.max_downloads < 1:
        parser.error("--max-downloads must be positive")
    if args.max_transcriptions != 1:
        parser.error("--max-transcriptions must be 1")
    if args.days is not None and args.since:
        parser.error("--days and --since cannot be used together")
    if args.days is not None and not 1 <= args.days <= global_ingestion["max_window_days"]:
        parser.error(f"--days must be between 1 and {global_ingestion['max_window_days']}")

    manifest = load_sources_markdown(args.manifest)
    sources = list(manifest["sources"])
    logger = RunLogger(args.run_log, loop_type=LoopType.SOURCE_INGESTION)
    output_lock = threading.Lock()
    logger.event(
        operation="ingest_sources",
        stage="start",
        parameters={
            "manifest": args.manifest,
            "source_count": len(sources),
            "days": args.days,
            "since": args.since,
            "until": args.until,
            "force": args.force,
            "max_downloads": args.max_downloads,
            "max_transcriptions": args.max_transcriptions,
            "browser": args.browser,
            "yt_dlp": args.yt_dlp,
            "whisper_script": args.whisper_script,
            "model": args.model,
            "language": args.language,
            "output_root": args.output_root,
        },
    )
    unsupported = unsupported_platforms(manifest["sources"], {"youtube", "x"})
    if unsupported:
        failures = [
            {
                "stage": "source_validation",
                "source": item.get("url"),
                "handle": item.get("handle"),
                "status": "FAILED_UNSUPPORTED_PLATFORM",
                "retryable": False,
                "error": f"No adapter is registered for platform {item.get('platform')}",
            }
            for item in unsupported
        ]
        payload = {
            "loop_type": LoopType.SOURCE_INGESTION.value,
            "status": "COMPLETED_WITH_FAILURES",
            "source_count": len(sources),
            "completed_sources": 0,
            "failure_count": len(failures),
            "discovered_video_count": 0,
            "new_video_count": 0,
            "already_downloaded_count": 0,
            "completed_video_count": 0,
            "source_failures": failures,
            "results": [],
        }
        report_path = Path(args.report)
        atomic_write_text(report_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        logger.event(
            operation="ingest_sources", stage="source_validation", category="FAILURE",
            status="COMPLETED_WITH_FAILURES", output=payload,
            artifact_paths=[str(report_path)],
        )
        if not args.noout:
            print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    download_limiter = Semaphore(args.max_downloads)
    transcription_limiter = Semaphore(1)
    auth_args = ("--cookies-from-browser", args.browser) if args.browser else ()
    as_of = datetime.fromisoformat(args.as_of).date() if args.as_of else None
    since = datetime.fromisoformat(args.since) if args.since else None
    until = datetime.fromisoformat(args.until) if args.until else None
    discover_fn = discover_channel_videos_api if os.environ.get("YOUTUBE_API_KEY") else None
    dashboard = ProgressDashboard(
        enabled=not args.noout and not args.verbose and sys.stdout.isatty()
    )

    def report(message: str) -> None:
        with output_lock:
            if args.verbose and not args.noout:
                print(message, flush=True)
            elif not args.noout:
                dashboard.stage(message)

    def video_event(
        event: str,
        channel_url: str,
        video_id: str,
        title: str | None,
        result,
    ) -> None:
        if event == "planned":
            dashboard.planned(video_id, title)
        elif event == "started":
            dashboard.started(video_id, title)
        elif event == "finished" and result is not None:
            dashboard.finished(video_id, result.status)

    def process(source: dict[str, object]):
        handle = str(source["handle"])
        source_since = since
        if source_since is None and source.get("since"):
            source_since = datetime.fromisoformat(str(source["since"]))
        if source["platform"] == "x":
            if args.verbose:
                report(f"Starting {source['name']} ({handle}) → {source['source_folder']}")
            return ingest_x_source(
                str(source["url"]), Path(args.output_root) / str(source["source_folder"]),
                handle=handle, source_registry_path=args.source_registry,
                since=source_since, until=until, logger=logger,
                force=args.force,
            )
        kwargs = {"discover_fn": discover_fn} if discover_fn else {}
        if args.verbose:
            report(f"Starting {source['name']} ({handle}) → {source['source_folder']}")
        return ingest_channel(
            str(source["url"]),
            Path(args.output_root) / str(source["source_folder"]),
            whisper_script=args.whisper_script,
            window_days=args.days,
            as_of=as_of,
            since=source_since,
            until=until,
            force=args.force,
            yt_dlp=args.yt_dlp,
            auth_args=auth_args,
            model=args.model,
            language=args.language,
            progress=report,
            source_registry_path=args.source_registry,
            source_key=str(source["url"]),
            logger=logger,
            download_limiter=download_limiter,
            transcription_limiter=transcription_limiter,
            video_workers=args.max_downloads,
            video_event=video_event,
            **kwargs,
        )

    results: list[ChannelIngestionResult] = []
    source_failures = []
    totals = {
        "discovered": 0, "already_downloaded": 0, "completed": 0, "failed": 0,
        "x_media_downloads": 0, "x_document_downloads": 0,
        "x_transcript_downloads": 0,
        "x_api_post_reads": 0, "x_api_user_lookups": 0, "x_api_cost_usd": 0.0,
    }
    totals_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=args.max_downloads) as executor:
        future_sources = {executor.submit(process, source): source for source in sources}
        for future in as_completed(future_sources):
            source = future_sources[future]
            try:
                result = future.result()
                results.append(result)
                with totals_lock:
                    totals["discovered"] += result.discovered_count
                    totals["already_downloaded"] += result.skipped_count
                    totals["completed"] += result.completed_count
                    totals["failed"] += result.failure_count
                    totals["x_media_downloads"] += getattr(result, "media_download_count", 0)
                    totals["x_document_downloads"] += getattr(result, "document_download_count", 0)
                    totals["x_transcript_downloads"] += getattr(result, "transcript_download_count", 0)
                    totals["x_api_post_reads"] += getattr(result, "api_post_reads", 0)
                    totals["x_api_user_lookups"] += getattr(result, "api_user_lookups", 0)
                    totals["x_api_cost_usd"] += getattr(result, "estimated_api_cost_usd", 0.0)
                    report(
                        f"Completed {result.channel_url}: discovered={result.discovered_count}, "
                        f"new={result.discovered_count - result.skipped_count}, "
                        f"already_downloaded={result.skipped_count}, completed={result.completed_count}, "
                        f"failed={result.failure_count} | cumulative discovered={totals['discovered']}, "
                        f"already_downloaded={totals['already_downloaded']}, completed={totals['completed']}, "
                        f"failed={totals['failed']}"
                    )
            except Exception as exc:
                error = {
                    "stage": "source_ingestion",
                    "source": source["url"],
                    "handle": source["handle"],
                    "status": "FAILED_SOURCE",
                    "error": str(exc),
                }
                source_failures.append(error)
                logger.event(
                    operation="ingest_sources",
                    stage="source_ingestion",
                    category="FAILURE",
                    status="FAILED_SOURCE",
                    parameters={"source": source["url"], "handle": source["handle"]},
                    error=str(exc),
                )
                report(f"Failure recorded for {source['handle']}: {exc}")
    results.sort(key=lambda result: result.channel_url)
    payload = {
        "loop_type": LoopType.SOURCE_INGESTION.value,
        "status": "COMPLETED" if not source_failures and all(result.status == "COMPLETED" for result in results) else "COMPLETED_WITH_FAILURES",
        "source_count": len(sources),
        "completed_sources": sum(result.status == "COMPLETED" for result in results),
        "failure_count": sum(result.failure_count for result in results) + len(source_failures),
        "discovered_video_count": totals["discovered"],
        "new_video_count": totals["discovered"] - totals["already_downloaded"],
        "already_downloaded_count": totals["already_downloaded"],
        "completed_video_count": totals["completed"],
        "x_media_downloads": totals["x_media_downloads"],
        "x_document_downloads": totals["x_document_downloads"],
        "x_transcript_downloads": totals["x_transcript_downloads"],
        "x_api_post_reads": totals["x_api_post_reads"],
        "x_api_user_lookups": totals["x_api_user_lookups"],
        "estimated_x_api_cost_usd": round(totals["x_api_cost_usd"], 6),
        "source_failures": source_failures,
        "results": [result.to_dict() for result in results],
    }
    report_path = Path(args.report)
    atomic_write_text(report_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    dashboard.finish()
    logger.event(
        operation="ingest_sources",
        stage="summary",
        category=status_category(str(payload["status"])),
        status=payload["status"],
        output={key: payload[key] for key in (
            "status", "source_count", "completed_sources", "failure_count",
            "discovered_video_count", "new_video_count", "already_downloaded_count",
            "completed_video_count", "source_failures",
            "x_media_downloads", "x_document_downloads", "x_transcript_downloads",
            "x_api_post_reads", "x_api_user_lookups", "estimated_x_api_cost_usd",
        )},
        artifact_paths=[str(report_path)],
    )
    if not args.noout:
        if args.full_report:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(
                f"Run complete: status={payload['status']}, sources={payload['source_count']}, "
                f"discovered={payload['discovered_video_count']}, "
                f"already_downloaded={payload['already_downloaded_count']}, "
                f"completed={payload['completed_video_count']}, "
                f"failed={payload['failure_count']}"
            )
            print(f"Full report: {report_path}")
            print(
                f"X assets: {payload['x_media_downloads']} media, "
                f"{payload['x_document_downloads']} documents, "
                f"{payload['x_transcript_downloads']} transcripts"
            )
            print(
                f"Estimated X API cost: ${payload['estimated_x_api_cost_usd']:.4f} "
                f"({payload['x_api_post_reads']} post reads, "
                f"{payload['x_api_user_lookups']} uncached user lookups)"
            )
    return exit_code(str(payload["status"]))


if __name__ == "__main__":
    raise SystemExit(main())
