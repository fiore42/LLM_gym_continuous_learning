#!/usr/bin/env python3
"""Validate the configured YouTube source manifest."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.sources.manifest import load_sources_markdown
from llm_gym.shared.settings import load_parameters


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="config/SOURCES.md")
    parser.add_argument("--noout", action="store_true", help="Suppress normal output")
    args = parser.parse_args()
    try:
        load_parameters()
        manifest = load_sources_markdown(args.manifest)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Manifest validation failed: {exc}", file=sys.stderr)
        return 1
    if not args.noout:
        print(f"Manifest valid: {args.manifest}")
        print(f"Sources: {len(manifest['sources'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
