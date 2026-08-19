#!/usr/bin/env python3
"""Run the incremental daily ingestion-and-library-update loop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.corpus.library_update import run_library_update


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser")
    parser.add_argument("--max-downloads", type=int, default=3)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--noout", action="store_true")
    args = parser.parse_args()
    ingest_args = ["--max-downloads", str(args.max_downloads)]
    if args.browser:
        ingest_args += ["--browser", args.browser]
    if args.verbose:
        ingest_args.append("--verbose")
    if args.force:
        ingest_args.append("--force")
    if args.noout:
        ingest_args.append("--noout")
    result = run_library_update(ingest_args=ingest_args)
    if not args.noout:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
