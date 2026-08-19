#!/usr/bin/env python3
"""Assess every item in a frozen corpus window as one long, resumable task.

Costs money: one bounded model call per item, plus bounded validation/provider
retries (one by default).
Run `--estimate` first — it reports item count and projected input tokens from
the real texts without calling a provider, so a window can be sized before it
is paid for.

Kill it at any point and run the same command again: completed items are not
reassessed, spend is carried rather than restarted, and refused items return to
the queue.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.agent.agent_task import TaskSpec
from llm_gym.agent.digest import run_digest
from llm_gym.agent.model_client import model_client_from_environment
from llm_gym.agent.significance import SIGNIFICANCE_PROMPT_VERSION
from llm_gym.corpus.window import attach_item_text, load_snapshot
from llm_gym.shared.config import load_dotenv
from llm_gym.shared.settings import digest_parameters
from llm_gym.shared.status import completion_exit_code


MAX_ITEM_RETRIES = 1
MAX_CONFIGURABLE_ITEM_RETRIES = 5


def bounded_item_retries(value: str) -> int:
    """Parse a deliberately small retry cap for one digest invocation."""
    retries = int(value)
    if not 0 <= retries <= MAX_CONFIGURABLE_ITEM_RETRIES:
        raise argparse.ArgumentTypeError(
            f"must be between 0 and {MAX_CONFIGURABLE_ITEM_RETRIES}")
    return retries


def provider_request_budget_units(
    item_count: int, max_item_retries: int = MAX_ITEM_RETRIES,
) -> int:
    """Reserve the initial request and configured retries for every item."""
    return item_count * (1 + max_item_retries)


def digest_artifact_prefix(snapshot_path: str | Path, model: str, provider_prefix: str,
                           prompt_version: str = SIGNIFICANCE_PROMPT_VERSION) -> str:
    """Per-window, per-model, per-prompt artifact prefix prevents collisions."""
    stem = Path(snapshot_path).stem
    slug = re.sub(
        r"[^a-z0-9.]+", "-",
        f"{stem}-{model}-{provider_prefix}-{prompt_version}".lower()).strip("-")
    return f"data/digests/{slug}"


def window_days(snapshot: dict) -> float:
    """Length of the frozen window, as the denominator the cost budget uses.

    Per day of content is a far steadier denominator than per item: measured
    across one window, item cost spans 15x while cost per window-day spans
    1.7x. Item cost tracks transcript length; day cost averages over however
    many items that day produced.
    """
    since = datetime.fromisoformat(snapshot["since"])
    until = datetime.fromisoformat(snapshot["until"])
    return max((until - since).total_seconds() / 86400.0, 1.0)


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, help="Frozen window from corpus_freeze_digest_window.py")
    parser.add_argument("--index", default="data/evidence.sqlite3")
    parser.add_argument("--model", default="")
    parser.add_argument("--provider-prefix", default="AGENT",
                        help="Environment prefix selecting the provider (AGENT, OPEN_WEIGHT)")
    parser.add_argument("--checkpoint", default="", help="Defaults to a per-window path")
    parser.add_argument("--output", default="", help="Defaults to a per-window path")
    parser.add_argument("--limit", type=int, default=0,
                        help="Assess at most this many items; 0 means the whole window")
    parser.add_argument(
        "--max-item-retries", type=bounded_item_retries, default=MAX_ITEM_RETRIES,
        help=("Retries after the first request for each item (default: 1; "
              f"maximum: {MAX_CONFIGURABLE_ITEM_RETRIES})"),
    )
    parser.add_argument("--estimate", action="store_true",
                        help="Report size and projected tokens without calling a provider")
    args = parser.parse_args()

    snapshot = load_snapshot(args.snapshot)
    items = attach_item_text(args.index, snapshot["items"])
    if args.limit:
        items = items[:args.limit]
    snapshot = {**snapshot, "items": items}

    if args.estimate:
        characters = [len(item["text"]) for item in items]
        # Four characters per token is a rough but stable rule for English prose;
        # it is a projection, not a measurement, and the run reports the real
        # numbers.
        tokens = sum(characters) // 4
        print(json.dumps({
            "items": len(items),
            "empty_text_items": sum(1 for count in characters if count == 0),
            "total_characters": sum(characters),
            "projected_input_tokens": tokens,
            "median_item_characters": sorted(characters)[len(characters) // 2] if characters else 0,
            "largest_item_characters": max(characters, default=0),
            "estimate_only": True,
        }, indent=2))
        return 0

    if not args.model:
        parser.error("--model is required unless --estimate is given")
    prefix = digest_artifact_prefix(
        args.snapshot, args.model, args.provider_prefix, SIGNIFICANCE_PROMPT_VERSION)
    result = run_digest(
        snapshot=snapshot, model=args.model,
        client=model_client_from_environment(prefix=args.provider_prefix),
        # Fitted to the window: an absolute call budget is idle headroom for a
        # short window and a wall for a long one.
        spec=TaskSpec.for_unit_count(
            # The resource is provider calls, not items. Each item can use its
            # initial request plus one validation/provider retry.
            "digest", f"window {snapshot['since']}",
            provider_request_budget_units(len(items), args.max_item_retries),
            cost_budget_usd=window_days(snapshot)
            * float(digest_parameters()["max_cost_usd_per_window_day"])),
        checkpoint_path=args.checkpoint or f"{prefix}-checkpoint.json",
        output_path=args.output or f"{prefix}-report.json",
        prompt_version=SIGNIFICANCE_PROMPT_VERSION,
        max_item_retries=args.max_item_retries,
    )
    print(json.dumps({
        "outcome": result["outcome"], "stop_reason": result["stop_reason"],
        "complete": result["complete"], "cache_hit": result["cache_hit"],
        "items_total": result["items_total"], "items_assessed": result["items_assessed"],
        "items_rejected": result["items_rejected"],
        "label_counts": result["label_counts"],
        "model_calls": result["model_calls"], "cost_usd": result["cost_usd"],
        # Historical cached reports predate this provenance field. Their retry
        # policy was the default, so printing can safely fall back to this
        # invocation's requested value instead of failing after the work ended.
        "max_item_retries": result.get("max_item_retries", args.max_item_retries),
        "report": args.output or f"{prefix}-report.json",
    }, indent=2))
    return completion_exit_code(bool(result["complete"]))


if __name__ == "__main__":
    raise SystemExit(main())
