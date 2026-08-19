"""Deterministic corpus-window selection, frozen to an inspectable snapshot.

The digest assesses one corpus item per model call, so the set of items must be
decided before any model runs and must not move underneath a resumed run. This
module is the deterministic half: given a window and an index, it always yields
the same items in the same order, and records what it considered as well as what
it selected.

No model call, no network, no cost.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .evidence import index_signature
from ..shared.atomic import atomic_write_text

SNAPSHOT_VERSION = 1
_BRACKETED_TRANSCRIPT_CUE = re.compile(r"\[[^\[\]]+\]")


def normalise_timestamp(value: str | None) -> datetime | None:
    """Parse a stored `published_at` into an aware UTC datetime.

    The corpus holds two representations of the same instant — `+00:00` from one
    adapter and `.000Z` from another — so comparing the stored strings orders
    identical instants differently and makes a window boundary ambiguous. Parse
    before comparing, never after.

    A value that will not parse returns None rather than raising: one bad
    timestamp must not lose the window, but it must be counted, so the caller
    reports it instead of silently dropping the item.
    """
    if not value or not str(value).strip():
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None
    # A naive timestamp is treated as UTC: every adapter records UTC, and
    # guessing a local zone would shift items across the boundary.
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class WindowSelection:
    """What a window selected, and what it had to choose from."""

    items: tuple[dict[str, Any], ...]
    since: str
    until: str
    platforms: tuple[str, ...]
    index_signature: str
    considered: int
    unparseable_published_at: int
    excluded_non_substantive: int = 0

    @property
    def selected(self) -> int:
        return len(self.items)

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "snapshot_version": SNAPSHOT_VERSION,
            "index_signature": self.index_signature,
            "since": self.since,
            "until": self.until,
            "platforms": list(self.platforms),
            # Considered versus selected is the honest denominator: a window
            # returning 3 items means something different out of 12 than out of
            # 1,600.
            "considered": self.considered,
            "selected": self.selected,
            "unparseable_published_at": self.unparseable_published_at,
            "excluded_non_substantive": self.excluded_non_substantive,
            "items": [dict(item) for item in self.items],
        }


def select_window(index_path: str | Path, *, since: datetime, until: datetime,
                  platforms: Iterable[str] = ()) -> WindowSelection:
    """Select corpus items published in the half-open interval [since, until).

    Half-open so that consecutive windows tile the timeline without selecting a
    boundary item twice. Ordering is by published instant then evidence_id, so a
    tie cannot reorder between runs and a resumed digest continues at the same
    position.
    """
    if until <= since:
        raise ValueError("until must be after since")
    wanted = tuple(sorted({str(platform).strip().lower() for platform in platforms if str(platform).strip()}))
    columns = ("evidence_id", "platform", "source_key", "canonical_url",
               "published_at", "title", "author", "kind")

    connection = sqlite3.connect(f"file:{Path(index_path)}?mode=ro", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"SELECT {', '.join(columns)} FROM evidence_items").fetchall()
    finally:
        connection.close()

    considered = 0
    unparseable = 0
    selected: list[tuple[datetime, str, dict[str, Any]]] = []
    for row in rows:
        if wanted and str(row["platform"]).strip().lower() not in wanted:
            continue
        considered += 1
        published = normalise_timestamp(row["published_at"])
        if published is None:
            unparseable += 1
            continue
        if since <= published < until:
            item = {key: row[key] for key in columns}
            item["published_at_utc"] = published.isoformat()
            selected.append((published, str(row["evidence_id"]), item))

    selected.sort(key=lambda entry: (entry[0], entry[1]))
    return WindowSelection(
        items=tuple(item for _, _, item in selected),
        since=since.astimezone(timezone.utc).isoformat(),
        until=until.astimezone(timezone.utc).isoformat(),
        platforms=wanted,
        index_signature=index_signature(index_path),
        considered=considered,
        unparseable_published_at=unparseable,
    )


def deoverlap_captions(chunks: Iterable[str]) -> str:
    """Rebuild prose from rolling captions by appending only what is new.

    Subtitle formats repeat each line as the next scrolls in, so the stored item
    text restates almost every sentence two or three times, interleaved with
    timestamps. On a measured 30-minute video that is 107,682 characters, about
    27,000 tokens, of which four fifths is duplication.

    Two consequences, both of which this fixes. The cost is paid per item on
    every digest call. And a model asked to quote verbatim will quote the
    spoken sentence, which does not exist contiguously in the raw text, so
    every grounded-quote check would fail on formatting rather than on honesty.
    """
    out = ""
    for raw in chunks:
        text = " ".join(str(raw or "").split())
        if not text:
            continue
        overlap = 0
        for size in range(min(len(out), len(text)), 0, -1):
            if out.endswith(text[:size]):
                overlap = size
                break
        addition = text[overlap:]
        if not addition.strip():
            continue
        out = addition if not out else f"{out} {addition}".replace("  ", " ")
    return " ".join(out.split())


def item_text(index_path: str | Path, evidence_id: str) -> str:
    """Assemble one item's readable text from its ordered chunks."""
    connection = sqlite3.connect(f"file:{Path(index_path)}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT text FROM evidence_chunks WHERE evidence_id = ? ORDER BY chunk_index",
            (str(evidence_id),)).fetchall()
    finally:
        connection.close()
    return deoverlap_captions(row[0] for row in rows)


def attach_item_text(index_path: str | Path,
                     items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the items with readable `text` attached, ready to assess."""
    return [{**item, "text": item_text(index_path, item["evidence_id"])} for item in items]


def source_text_is_substantive(text: str) -> bool:
    """Reject empty transcripts and bracketed non-lexical stage directions.

    A one-word factual transcript remains eligible. The rule removes bracketed
    caption cues and then asks only whether any letter or number remains; it
    does not attempt to judge topic, quality, or significance.
    """
    without_cues = _BRACKETED_TRANSCRIPT_CUE.sub(" ", str(text or ""))
    return any(character.isalnum() for character in without_cues)


def exclude_non_substantive_items(
    index_path: str | Path, selection: WindowSelection,
) -> WindowSelection:
    """Remove placeholder-only items before a frozen window can spend money."""
    attached = attach_item_text(index_path, selection.items)
    substantive_ids = {
        str(item["evidence_id"]) for item in attached
        if source_text_is_substantive(str(item.get("text") or ""))
    }
    kept = tuple(
        item for item in selection.items
        if str(item.get("evidence_id")) in substantive_ids
    )
    return replace(
        selection,
        items=kept,
        excluded_non_substantive=selection.excluded_non_substantive + len(selection.items) - len(kept),
    )


def freeze_window(selection: WindowSelection, output_path: str | Path) -> dict[str, Any]:
    """Persist the selection so a later run assesses the same items.

    The snapshot carries its `index_signature`: a rebuilt index may contain
    different items for the same window, and a resumed digest must be able to
    detect that rather than silently assess a different set.
    """
    snapshot = selection.to_snapshot()
    atomic_write_text(Path(output_path),
                      json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    return snapshot


def load_snapshot(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("snapshot_version") != SNAPSHOT_VERSION:
        raise ValueError(f"unsupported window snapshot: {path}")
    return payload
