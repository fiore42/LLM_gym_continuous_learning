"""Bounded, resumable research retrieval loop."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..shared.atomic import atomic_write_text
from ..corpus.evidence import index_signature, search_index_with_metadata
from ..shared.loops import LoopType, new_loop_context


LOOP_VERSION = 2


def run_research(
    question: str,
    *,
    index_path: str | Path = "data/evidence.sqlite3",
    checkpoint_path: str | Path = "data/research-checkpoint.json",
    limit: int = 8,
    force: bool = False,
) -> dict[str, Any]:
    """Retrieve evidence and persist a resumable research checkpoint.

    This stage deliberately returns evidence and citations, not an unsupported
    generated answer. SUPPORTED means relevant supplied retrieved evidence was
    found; it does not mean the entire corpus agrees or the claim has been
    independently verified.
    """
    question = question.strip()
    if not question:
        raise ValueError("question must not be empty")
    if limit < 1:
        raise ValueError("limit must be positive")
    checkpoint = Path(checkpoint_path)
    current_index_signature = index_signature(index_path)
    if not force and checkpoint.is_file():
        try:
            previous = json.loads(checkpoint.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None
        if (
            isinstance(previous, dict)
            and previous.get("question") == question
            and previous.get("loop_version") == LOOP_VERSION
            and previous.get("loop_type") == LoopType.RESEARCH_QUERY.value
            and previous.get("retrieval", {}).get("index_signature") == current_index_signature
            # Breadth changes what was retrieved, so it belongs in the reuse
            # test. Without it, asking for eight items returned a cached
            # three-item checkpoint and reported limit=3, silently ignoring the
            # request (Rule 30: a guard protects only the fields it names).
            and previous.get("retrieval", {}).get("limit") == limit
        ):
            return previous

    retrieval = search_index_with_metadata(question, index_path, limit)
    matches = retrieval["matches"]
    context = new_loop_context(LoopType.RESEARCH_QUERY)
    classification = "SUPPORTED" if matches else "INSUFFICIENT_EVIDENCE"
    result: dict[str, Any] = {
        "loop_version": LOOP_VERSION,
        **context,
        "status": "COMPLETED",
        "question": question,
        "classification": classification,
        "retrieval": {
            "limit": retrieval["limit"],
            "returned_count": retrieval["returned_count"],
            "matched_chunk_count": retrieval["matched_chunk_count"],
            "matched_evidence_count": retrieval["matched_evidence_count"],
            "truncated": retrieval["truncated"],
            "index_version": retrieval["index_version"],
            "scope": "supplied retrieved evidence",
            "index_signature": current_index_signature,
        },
        "answer": None,
        "answer_note": "Model synthesis is intentionally not run in this retrieval-only stage.",
        "evidence": [
            {
                "evidence_id": item["evidence_id"],
                "platform": item["platform"],
                "source_key": item["source_key"],
                "content_id": item["content_id"],
                "canonical_url": item["canonical_url"],
                "published_at": item["published_at"],
                "title": item["title"],
                "kind": item["kind"],
                "locator": item.get("locator"),
                "artifact_path": item["artifact_path"],
                "snippet": item["snippet"],
            }
            for item in matches
        ],
        "completed_stages": ["retrieve", "cite", "classify", "checkpoint"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write_text(checkpoint, json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result
