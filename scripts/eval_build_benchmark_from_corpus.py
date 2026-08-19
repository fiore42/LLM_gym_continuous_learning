#!/usr/bin/env python3
"""Create a human-labeled benchmark from the local evidence index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.shared.atomic import atomic_write_text
from llm_gym.corpus.evidence import search_index


ALLOWED_OUTCOMES = {"SUPPORTED", "INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE"}


def build_cases(requests: list[dict[str, object]], index_path: str | Path, limit: int) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for request in requests:
        case_id = str(request.get("case_id") or "").strip()
        question = str(request.get("question") or "").strip()
        expected_outcome = str(request.get("expected_outcome") or "").strip().upper()
        if not case_id or not question:
            raise ValueError("each request requires case_id and question")
        if expected_outcome not in ALLOWED_OUTCOMES:
            raise ValueError(f"{case_id}: expected_outcome must be one of {sorted(ALLOWED_OUTCOMES)}")
        matches = search_index(str(request.get("search_query") or question), index_path, limit)
        if not matches:
            raise ValueError(f"{case_id}: no evidence matched the query")
        evidence = []
        for match in matches:
            evidence.append({key: match.get(key) for key in (
                "evidence_id", "canonical_url", "published_at", "title", "locator", "snippet"
            )})
        required = request.get("required_citation_ids") or []
        if not isinstance(required, list) or any(not str(item).strip() for item in required):
            raise ValueError(f"{case_id}: required_citation_ids must be a list of non-empty IDs")
        available_ids = {str(item["evidence_id"]) for item in evidence}
        unknown_required = sorted(set(str(item) for item in required) - available_ids)
        if unknown_required:
            raise ValueError(f"{case_id}: required citations were not retrieved: {unknown_required}")
        forbidden = request.get("forbidden_citation_ids") or []
        if not isinstance(forbidden, list) or any(not str(item).strip() for item in forbidden):
            raise ValueError(f"{case_id}: forbidden_citation_ids must be a list of non-empty IDs")
        unknown_forbidden = sorted(set(str(item) for item in forbidden) - available_ids)
        if unknown_forbidden:
            raise ValueError(f"{case_id}: forbidden citations were not retrieved: {unknown_forbidden}")
        cases.append({
            "case_id": case_id,
            "question": question,
            "expected_outcome": expected_outcome,
            "required_citation_ids": [str(item) for item in required],
            "forbidden_citation_ids": [str(item) for item in forbidden],
            "evidence": evidence,
        })
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", required=True, help="JSON file containing human-labeled benchmark requests")
    parser.add_argument("--index", default="data/evidence.sqlite3")
    parser.add_argument("--output", default="data/agent_benchmark_corpus.json")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    requests = json.loads(Path(args.requests).read_text(encoding="utf-8"))
    if not isinstance(requests, list) or not requests:
        parser.error("--requests must contain a non-empty JSON list")
    cases = build_cases(requests, args.index, args.limit)
    payload = {"benchmark_version": 1, "source": "local_evidence_index", "cases": cases}
    atomic_write_text(args.output, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"output": args.output, "cases": len(cases), "source": payload["source"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
