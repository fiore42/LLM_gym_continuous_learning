#!/usr/bin/env python3
"""Run the bounded retrieval-and-citation research loop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.agent.research import run_research


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--index", default="data/evidence.sqlite3")
    parser.add_argument("--checkpoint", default="data/research-checkpoint.json")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run_research(args.question, index_path=args.index, checkpoint_path=args.checkpoint, limit=args.limit, force=args.force)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
