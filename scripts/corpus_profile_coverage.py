#!/usr/bin/env python3
"""Profile downloaded source coverage without reading media or logs."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.corpus.corpus_profile import profile_corpus, write_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default="source")
    parser.add_argument("--output", default="data/corpus-profile.json")
    parser.add_argument("--noout", action="store_true")
    args = parser.parse_args()
    profile = profile_corpus(args.source_root)
    write_profile(profile, args.output)
    if not args.noout:
        print(json.dumps({
            "status": "COMPLETED",
            "total_items": profile["total_items"],
            "platforms": profile["platform_counts"],
            "status_counts": profile["status_counts"],
            "output": args.output,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
