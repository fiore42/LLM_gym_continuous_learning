#!/usr/bin/env python3
"""Run a live smoke test for single-video YouTube ingestion."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.sources.youtube import ingest_one_video
from llm_gym.shared.config import load_dotenv
from llm_gym.shared.run_log import RunLogger
from llm_gym.shared.settings import tool_parameters
from llm_gym.shared.status import exit_code, status_category


def main() -> int:
    load_dotenv()
    global_tools = tool_parameters()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--browser",
        help="Browser whose logged-in cookies yt-dlp should use, e.g. firefox or chrome",
    )
    parser.add_argument(
        "--output",
        default="data/smoke-test",
        help="Output directory (default: data/smoke-test)",
    )
    parser.add_argument(
        "--yt-dlp",
        default=global_tools["yt_dlp"],
        help="Path to yt-dlp",
    )
    parser.add_argument(
        "--whisper-script",
        default=global_tools["whisper_script"],
        help="Path to the WhisperX subtitle script",
    )
    parser.add_argument(
        "--noout",
        action="store_true",
        help="Suppress normal result output; preserve the exit code and log files",
    )
    parser.add_argument("--run-log", default="data/run-log.jsonl", help="Shared chronological run log")
    args = parser.parse_args()

    auth_args = ("--cookies-from-browser", args.browser) if args.browser else ()
    logger = RunLogger(args.run_log)
    result = ingest_one_video(
        args.url,
        Path(args.output),
        yt_dlp=args.yt_dlp,
        whisper_script=args.whisper_script,
        auth_args=auth_args,
        logger=logger,
    )
    logger.event(
        operation="smoke_test_youtube",
        stage="summary",
        category=status_category(result.status),
        status=result.status,
        parameters={"url": args.url, "browser": args.browser, "output": args.output},
        output={"url": args.url, "status": result.status,
                "has_transcript": bool(result.transcript_path)},
        artifact_paths=[result.transcript_path] if result.transcript_path else [],
    )

    if not args.noout:
        print(json.dumps(result.to_dict(), indent=2))
    return exit_code(result.status)


if __name__ == "__main__":
    raise SystemExit(main())
