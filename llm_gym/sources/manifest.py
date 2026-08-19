"""Loading and validating the hand-edited Markdown source list."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_sources_markdown(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    header_index = next((i for i, line in enumerate(lines) if line.startswith("| Platform |")), None)
    if header_index is None:
        raise ValueError("sources Markdown must contain the source table")
    headers = [part.strip().lower() for part in lines[header_index].strip().strip("|").split("|")]
    required = ["platform", "name", "handle", "category", "subscribed", "since"]
    if headers != required:
        raise ValueError("sources table has unexpected columns")

    sources = []
    for line in lines[header_index + 2 :]:
        if not line.strip() or not line.lstrip().startswith("|"):
            continue
        values = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(values) != len(headers):
            raise ValueError("source table row has the wrong number of columns")
        row = dict(zip(headers, values))
        platform = row["platform"].lower()
        handle = row["handle"]
        source = {
            "name": row["name"],
            "handle": handle,
            "url": f"https://www.youtube.com/{handle}" if platform == "youtube" else f"https://x.com/{handle.lstrip('@')}",
            "platform": platform,
            "category": row["category"],
            "subscribed": row["subscribed"] or None,
            "since": row["since"] or None,
            "source_folder": f"source/{platform}/{handle.lstrip('@')}"
        }
        sources.append(source)
    if not sources:
        raise ValueError("sources table must contain at least one source")

    handles: set[str] = set()
    urls: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ValueError(f"source {index} must be an object")
        for field in ("name", "handle", "url", "category"):
            if field not in source:
                raise ValueError(f"source {index} is missing {field}")
        handle_key = (source["platform"], source["handle"])
        if handle_key in handles or source["url"] in urls:
            raise ValueError(f"duplicate source at index {index}")
        handles.add(handle_key)
        urls.add(source["url"])
        if source["platform"] not in {"youtube", "x"}:
            raise ValueError(f"source {index} has an unsupported platform")
        expected_prefix = "https://www.youtube.com/" if source["platform"] == "youtube" else "https://x.com/"
        if not str(source["url"]).startswith(expected_prefix):
            raise ValueError(f"source {index} has an invalid platform URL")
    return {"version": 1, "sources": sources}


def load_youtube_manifest(path: str | Path) -> dict[str, Any]:
    """Backward-compatible name for callers while the source list is Markdown."""

    data = load_sources_markdown(path)
    youtube_sources = [source for source in data["sources"] if source["platform"] == "youtube"]
    return {"version": 1, "platform": "youtube", "sources": youtube_sources}


def unsupported_platforms(sources: list[dict[str, Any]], supported: set[str]) -> list[dict[str, Any]]:
    """Return configured sources that the selected runner cannot process."""
    return [source for source in sources if source.get("platform") not in supported]
