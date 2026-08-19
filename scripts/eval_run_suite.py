#!/usr/bin/env python3
"""Run the frozen answer cases through one bounded model provider."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import re

from llm_gym.agent.agent_runner import run_agent_task
from llm_gym.agent.synthesis import PROMPT_VERSION
from llm_gym.agent.agent_task import TaskSpec
from llm_gym.shared.atomic import atomic_write_text
from llm_gym.shared.config import load_dotenv
from llm_gym.shared.status import completion_exit_code
from llm_gym.corpus.evidence import index_signature
from llm_gym.shared.loops import LoopType, new_loop_context
from llm_gym.agent.model_client import model_client_from_environment
from llm_gym.agent.prompt_registry import load_prompt


TERMINAL_OUTCOMES = {
    "COMPLETED", "COMPLETED_AFTER_RETRY", "INSUFFICIENT_EVIDENCE",
    "CONFLICTING_EVIDENCE", "ESCALATED_FOR_REVIEW", "FAILED_BUDGET",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _task_key(case_id: str, repetition: int) -> str:
    return f"{case_id}::rep-{repetition}"


def _new_state(suite: dict[str, Any], model: str, repetitions: int,
               prompt_version: str) -> dict[str, Any]:
    return {
        "suite_version": suite.get("suite_version"),
        "model": model,
        "repetitions": repetitions,
        "prompt_version": prompt_version,
        "loop": new_loop_context(LoopType.MODEL_EVALUATION),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "entries": {},
    }


def _state_matches(state: dict[str, Any], suite: dict[str, Any], model: str,
                   repetitions: int, prompt_version: str) -> bool:
    return (state.get("suite_version") == suite.get("suite_version")
            and state.get("model") == model
            and state.get("repetitions") == repetitions
            and state.get("prompt_version") == prompt_version
            and isinstance(state.get("entries"), dict))


def _summary(result: dict[str, Any], *, case_id: str, repetition: int,
             expected: str | None, output_path: Path) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "repetition": repetition,
        "expected_outcome": expected,
        "outcome": result.get("outcome"),
        "stop_reason": result.get("stop_reason"),
        "model_calls": result.get("model_calls", 0),
        "cost_usd": result.get("cost_usd", 0.0),
        "elapsed_seconds": result.get("elapsed_seconds", 0.0),
        "output_path": str(output_path),
        "cache_hit": bool(result.get("cache_hit")),
    }


def run_suite(*, suite_path: str | Path, output_path: str | Path,
              state_path: str | Path, cache_dir: str | Path, model: str,
              repetitions: int = 1, max_cost_usd: float = 1.0,
              prompt_version: str | None = None, client=None,
              index_path: str | Path = "data/evidence.sqlite3",
              progress=print) -> dict[str, Any]:
    """Run or resume a sequential suite and return its compact report."""
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    if max_cost_usd <= 0:
        raise ValueError("max_cost_usd must be positive")
    suite_file = Path(suite_path)
    output_file = Path(output_path)
    state_file = Path(state_path)
    cache_root = Path(cache_dir)
    suite = _read_json(suite_file)
    selected_prompt_version = load_prompt(version=prompt_version).prompt_version
    current_index_signature = index_signature(index_path)
    cases = suite.get("answer_cases") or []
    if not isinstance(cases, list) or not cases:
        raise ValueError("suite must contain answer_cases")

    try:
        state = _read_json(state_file) if state_file.is_file() else {}
    except (OSError, json.JSONDecodeError, ValueError):
        state = {}
    if not _state_matches(state, suite, model, repetitions, selected_prompt_version):
        state = _new_state(suite, model, repetitions, selected_prompt_version)
    entries: dict[str, Any] = state["entries"]
    cache_root.mkdir(parents=True, exist_ok=True)
    if client is None:
        client = model_client_from_environment()

    summaries = [entry for entry in entries.values()
                 if isinstance(entry, dict) and entry.get("outcome") in TERMINAL_OUTCOMES]
    total_cost = sum(float(entry.get("cost_usd", 0.0) or 0.0) for entry in summaries)
    suite_stop_reason = None

    for case in cases:
        if not isinstance(case, dict) or not case.get("case_id"):
            raise ValueError("every answer case requires case_id")
        case_id = str(case["case_id"])
        question = str(case.get("question") or "").strip()
        evidence = tuple(case.get("evidence") or ())
        if not question or not evidence:
            raise ValueError(f"{case_id}: question and evidence are required")
        expected = case.get("expected_outcome")
        for repetition in range(1, repetitions + 1):
            key = _task_key(case_id, repetition)
            previous = entries.get(key) or {}
            if previous.get("outcome") in TERMINAL_OUTCOMES:
                progress(f"SKIP {key}: {previous['outcome']}")
                continue
            if total_cost >= max_cost_usd:
                suite_stop_reason = "SUITE_COST_BUDGET_EXHAUSTED"
                break

            task_id = f"suite-{case_id}-rep-{repetition}"
            task_dir = (output_file.parent / "eval-suite" / selected_prompt_version
                        / state["loop"]["run_id"] / case_id / f"rep-{repetition}")
            task_output = task_dir / "result.json"
            task_cache = (cache_root / selected_prompt_version / state["loop"]["run_id"]
                          / case_id / f"rep-{repetition}.json")
            entries[key] = {"status": "RUNNING", "case_id": case_id,
                            "repetition": repetition, "output_path": str(task_output)}
            _write_json(state_file, state)
            progress(f"RUN {key}: {case_id}")
            result = run_agent_task(
                TaskSpec.from_global_parameters(task_id, question), evidence, client,
                model=model, checkpoint_path=task_output, cache_path=task_cache,
                prompt_version=selected_prompt_version,
            )
            summary = _summary(result, case_id=case_id, repetition=repetition,
                               expected=expected, output_path=task_output)
            entries[key] = summary
            total_cost += float(summary["cost_usd"] or 0.0)
            summaries = [entry for entry in entries.values()
                         if isinstance(entry, dict) and entry.get("outcome") in TERMINAL_OUTCOMES]
            _write_json(state_file, state)
            progress(f"DONE {key}: {summary['outcome']} cost=${summary['cost_usd']:.6f}")
        if suite_stop_reason:
            break

    if not suite_stop_reason:
        pending = [case_id for case_id in entries
                   if isinstance(entries[case_id], dict)
                   and entries[case_id].get("outcome") not in TERMINAL_OUTCOMES]
        expected_count = len(cases) * repetitions
        if len(summaries) < expected_count:
            suite_stop_reason = "INTERRUPTED_OR_INCOMPLETE"
        else:
            suite_stop_reason = "SUITE_COMPLETE"
    finished_at = datetime.now(timezone.utc).isoformat()
    report = {
        "loop_type": LoopType.MODEL_EVALUATION.value,
        "run_id": state["loop"]["run_id"],
        "suite_version": suite.get("suite_version"),
        "model": model,
        "prompt_version": selected_prompt_version,
        "index_signature": current_index_signature,
        "repetitions": repetitions,
        "suite_stop_reason": suite_stop_reason,
        "started_at": state["started_at"],
        "finished_at": finished_at,
        "max_cost_usd": max_cost_usd,
        "total_cost_usd": round(total_cost, 8),
        "completed_tasks": len(summaries),
        "cache_hit_count": sum(bool(entry.get("cache_hit")) for entry in summaries),
        "total_tasks": len(cases) * repetitions,
        "results": sorted(summaries, key=lambda item: (item["case_id"], item["repetition"])),
        "state_path": str(state_file),
    }
    _write_json(output_file, report)
    state["finished_at"] = finished_at
    state["suite_stop_reason"] = suite_stop_reason
    state["total_cost_usd"] = round(total_cost, 8)
    _write_json(state_file, state)
    return report


def suite_artifact_prefix(model: str, prompt_version: str) -> str:
    """Per-arm artifact prefix, so one arm cannot overwrite another.

    The report, resume state, and cache all belong to a single combination of
    model and prompt version. Sharing a default path across arms is how a
    stale artifact gets read as the current one.
    """
    slug = re.sub(r"[^a-z0-9.]+", "-", f"{model}-{prompt_version}".lower()).strip("-")
    return f"data/eval-suite/{slug}"


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="config/agent_eval_suite.json")
    parser.add_argument("--output", default="",
                        help="Defaults to a per-arm path under data/eval-suite/")
    parser.add_argument("--state", default="")
    parser.add_argument("--cache-dir", default="")
    parser.add_argument("--index", default="data/evidence.sqlite3",
                        help="Evidence index used for corpus provenance stamping")
    parser.add_argument("--model", default=os.environ.get("AGENT_MODEL", ""))
    parser.add_argument("--prompt-version", default=None,
                        help="Immutable prompt version; defaults to the latest registered prompt")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--max-cost-usd", type=float, default=1.0)
    args = parser.parse_args()
    if not args.model:
        parser.error("--model or AGENT_MODEL is required")
    prefix = suite_artifact_prefix(args.model, args.prompt_version or PROMPT_VERSION)
    output_path = args.output or f"{prefix}-report.json"
    state_path = args.state or f"{prefix}-state.json"
    cache_dir = args.cache_dir or f"{prefix}-cache"
    try:
        report = run_suite(suite_path=args.suite, output_path=output_path,
                           state_path=state_path, cache_dir=cache_dir,
                           model=args.model, repetitions=args.repetitions,
                           max_cost_usd=args.max_cost_usd,
                           prompt_version=args.prompt_version,
                           index_path=args.index)
    except KeyboardInterrupt:
        print("Interrupted; per-task checkpoints remain resumable.", file=sys.stderr)
        return 130
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return completion_exit_code(report.get("suite_stop_reason") == "SUITE_COMPLETE")


if __name__ == "__main__":
    raise SystemExit(main())
