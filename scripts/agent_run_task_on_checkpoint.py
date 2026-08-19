#!/usr/bin/env python3
"""Synthesize a research checkpoint through the configured model provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.shared.atomic import atomic_write_text
from llm_gym.shared.config import load_dotenv
from llm_gym.agent.agent_runner import run_agent_task
from llm_gym.agent.model_client import model_client_from_environment
from llm_gym.agent.agent_task import TaskSpec
from llm_gym.shared.status import task_outcome_exit_code


def run_from_checkpoint(
    *,
    checkpoint_path: str | Path,
    output_path: str | Path,
    cache_path: str | Path,
    model: str,
    task_id: str = "",
    client=None,
) -> dict:
    """Run one bounded task over a research checkpoint's frozen evidence.

    The provider client is injectable so this path can be exercised offline
    without a network call or spend; ``main`` supplies the configured one.
    """
    checkpoint = json.loads(Path(checkpoint_path).read_text(encoding="utf-8"))
    evidence = tuple(checkpoint.get("evidence") or ())
    question = checkpoint["question"]
    resolved_task_id = task_id or "research-" + hashlib.sha256(
        question.encode("utf-8")
    ).hexdigest()[:16]
    spec = TaskSpec.from_global_parameters(resolved_task_id, question)
    payload = run_agent_task(
        spec, evidence, client if client is not None else model_client_from_environment(),
        model=model, checkpoint_path=output_path, cache_path=cache_path,
    )
    # Keep review self-contained: the model sees only these bounded snippets,
    # so the reviewer should see the same evidence beside the answer.
    payload["retrieved_evidence"] = [
        {
            "evidence_id": item.get("evidence_id"),
            "canonical_url": item.get("canonical_url"),
            "title": item.get("title"),
            "locator": item.get("locator"),
            "artifact_path": item.get("artifact_path"),
            "snippet": item.get("snippet"),
        }
        for item in evidence
    ]
    payload["source_checkpoint"] = str(checkpoint_path)
    atomic_write_text(output_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload


def answer_output_path(model: str) -> str:
    """Per-model answer path. Two models writing one file leaves the second
    reading as though it were the first."""
    slug = re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")
    return f"data/research-answer-{slug}.json"


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default="data/research-checkpoint.json")
    parser.add_argument("--output", default="",
                        help="Defaults to a per-model path, so two models cannot "
                             "overwrite each other's answer")
    parser.add_argument("--cache", default="data/agent-task-cache.json")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--model", default=os.environ.get("AGENT_MODEL", ""))
    args = parser.parse_args()
    if not args.model:
        parser.error("--model or AGENT_MODEL is required")
    output_path = args.output or answer_output_path(args.model)
    payload = run_from_checkpoint(
        checkpoint_path=args.checkpoint,
        output_path=output_path,
        cache_path=args.cache,
        model=args.model,
        task_id=args.task_id,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return task_outcome_exit_code(payload.get("outcome"))


if __name__ == "__main__":
    raise SystemExit(main())
