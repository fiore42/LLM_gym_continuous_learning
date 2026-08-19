#!/usr/bin/env python3
"""Freeze the set of corpus items a digest run will assess.

Deterministic and free: no model call, no network. The digest assesses one item
per model call, so the item set must be decided and recorded before any spend
begins, and must not move underneath a resumed run.

Sizing measured against the current index (`--dry-run` reports it for any
window): 7 days of YouTube is around 50 items, 30 days around 330. A whole-corpus
window is dominated by X posts clustered inside the ingestion window rather than
by real activity, so scope the platform deliberately.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.corpus.window import (exclude_non_substantive_items, freeze_window,
                                   select_window)

INDEX_DEFAULT = "data/evidence.sqlite3"


def parse_instant(value: str) -> datetime:
    """Accept a date or a full timestamp, always resolved as UTC."""
    parsed = datetime.fromisoformat(value.strip())
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def snapshot_output_path(since: datetime, until: datetime, platforms: tuple[str, ...]) -> str:
    """Name the snapshot after the window it froze.

    Two windows sharing a path would leave the survivor reading as though it
    described the run that used it.
    """
    scope = "-".join(sorted(platforms)) if platforms else "all"
    slug = re.sub(r"[^a-z0-9]+", "-",
                  f"{since.date()}-to-{until.date()}-{scope}".lower()).strip("-")
    return f"data/digest-windows/{slug}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", help="Inclusive window start (date or ISO timestamp, UTC)")
    parser.add_argument("--until", help="Exclusive window end; defaults to now")
    parser.add_argument("--days", type=int,
                        help="Window length back from --until, instead of --since")
    parser.add_argument("--platform", action="append", default=[],
                        help="Restrict to a platform; repeatable. Omit for the whole corpus")
    parser.add_argument("--index", default=INDEX_DEFAULT)
    parser.add_argument("--output", default="",
                        help="Defaults to a path naming the window")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report the counts without writing a snapshot")
    args = parser.parse_args()

    if bool(args.since) == bool(args.days):
        parser.error("supply exactly one of --since or --days")
    until = parse_instant(args.until) if args.until else datetime.now(timezone.utc)
    since = parse_instant(args.since) if args.since else until - timedelta(days=args.days)

    selection = select_window(args.index, since=since, until=until,
                              platforms=tuple(args.platform))
    selection = exclude_non_substantive_items(args.index, selection)
    summary = {
        "since": selection.since, "until": selection.until,
        "platforms": list(selection.platforms),
        "considered": selection.considered, "selected": selection.selected,
        "unparseable_published_at": selection.unparseable_published_at,
        "excluded_non_substantive": selection.excluded_non_substantive,
        "index_signature": selection.index_signature,
    }
    if args.dry_run:
        print(json.dumps({**summary, "dry_run": True}, indent=2))
        return 0

    output = args.output or snapshot_output_path(since, until, selection.platforms)
    freeze_window(selection, output)
    print(json.dumps({**summary, "snapshot": output}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
