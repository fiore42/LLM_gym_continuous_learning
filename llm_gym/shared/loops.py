"""Explicit loop taxonomy and runtime metadata."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any


class LoopType(StrEnum):
    SOURCE_INGESTION = "SOURCE_INGESTION"
    LIBRARY_UPDATE = "LIBRARY_UPDATE"
    RESEARCH_QUERY = "RESEARCH_QUERY"
    AGENT_TASK = "AGENT_TASK"
    MODEL_EVALUATION = "MODEL_EVALUATION"
    PROJECT_IMPROVEMENT = "PROJECT_IMPROVEMENT"
    DIGEST = "DIGEST"


LOOP_CONTRACTS: dict[LoopType, dict[str, Any]] = {
    LoopType.SOURCE_INGESTION: {
        "trigger": "one configured source run",
        "purpose": "discover and persist new source content",
        "stochastic": False,
        "children": (),
        "commit_after_success": False,
    },
    LoopType.LIBRARY_UPDATE: {
        "trigger": "manual or scheduled update",
        "purpose": "run incremental ingestion and refresh the evidence index",
        "stochastic": False,
        "children": (LoopType.SOURCE_INGESTION,),
        "commit_after_success": False,
    },
    LoopType.RESEARCH_QUERY: {
        "trigger": "one user question",
        "purpose": "retrieve and cite evidence for a question",
        "stochastic": False,
        "children": (),
        "commit_after_success": False,
    },
    LoopType.AGENT_TASK: {
        "trigger": "one bounded research task",
        "purpose": "draft, evaluate, retry, stop, or escalate an answer",
        "stochastic": True,
        "children": (LoopType.RESEARCH_QUERY,),
        "commit_after_success": False,
    },
    LoopType.DIGEST: {
        "trigger": "one frozen corpus window",
        "purpose": "assess every item in the window and rank what changed",
        "stochastic": True,
        "children": [],
        "commit_after_success": False,
    },
    LoopType.MODEL_EVALUATION: {
        "trigger": "one provider comparison suite",
        "purpose": "run identical benchmark tasks and compare measured outcomes",
        "stochastic": True,
        "children": (LoopType.AGENT_TASK,),
        "commit_after_success": False,
    },
    LoopType.PROJECT_IMPROVEMENT: {
        "trigger": "one roadmap iteration",
        "purpose": "implement and evaluate one project objective",
        "stochastic": True,
        "children": (),
        "commit_after_success": True,
    },
}


def new_loop_context(loop_type: LoopType, *, parent_run_id: str | None = None) -> dict[str, str]:
    """Create explicit metadata for reports, checkpoints, and parent/child runs."""
    if loop_type not in LOOP_CONTRACTS:
        raise ValueError(f"unsupported loop type: {loop_type}")
    result = {"loop_type": loop_type.value, "run_id": uuid.uuid4().hex}
    if parent_run_id:
        result["parent_run_id"] = parent_run_id
    return result
