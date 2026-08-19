#!/usr/bin/env python3
"""Check per-source YouTube state against the central source registry."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.sources.consistency import check_state_registry_consistency


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root containing source/")
    parser.add_argument("--registry", default="data/source-registry.sqlite3")
    parser.add_argument("--manifest", default="config/SOURCES.md")
    parser.add_argument("--noout", action="store_true")
    args = parser.parse_args()
    try:
        report = check_state_registry_consistency(
            source_root=args.project_root,
            registry_path=args.registry,
            manifest_path=args.manifest,
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"Consistency check failed: {exc}", file=sys.stderr)
        return 1
    if not args.noout:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
