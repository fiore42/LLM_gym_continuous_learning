#!/usr/bin/env python3
"""Create/update the unified searchable evidence index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.corpus.evidence import build_index, collect_records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default="source")
    parser.add_argument("--index", default="data/evidence.sqlite3")
    args = parser.parse_args()
    records, warnings = collect_records(args.source_root)
    summary = build_index(records, args.index)
    print(json.dumps({"status": "COMPLETED", **summary, "warnings": len(warnings), "warning_samples": warnings[:20]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
