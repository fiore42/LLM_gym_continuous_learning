#!/usr/bin/env python3
"""Run the same benchmark suite against two provider environments."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.shared.config import load_dotenv
from llm_gym.shared.status import completion_exit_code
from llm_gym.agent.model_client import model_client_from_environment
from llm_gym.agent.model_evaluation import load_benchmark_cases, run_model_comparison


def validate_benchmark_source(path: str | Path, *, allow_synthetic: bool = False) -> str:
    """Reject placeholder cases before a paid/live comparison is started."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    source = str(payload.get("source") or "synthetic")
    if source != "local_evidence_index" and not allow_synthetic:
        raise ValueError(
            "model comparison requires a corpus-grounded benchmark; "
            "pass --allow-synthetic only for offline development"
        )
    return source


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default="config/agent_benchmark.json")
    parser.add_argument("--output", default="data/model-comparison-report.json")
    parser.add_argument("--work-dir", default="data/model-comparison-work")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--allow-synthetic", action="store_true",
                        help="Allow placeholder cases for offline development only")
    parser.add_argument("--frontier-model", default=os.environ.get("FRONTIER_MODEL", ""))
    parser.add_argument("--open-weight-model", default=os.environ.get("OPEN_WEIGHT_MODEL", ""))
    args = parser.parse_args()
    if not args.frontier_model or not args.open_weight_model:
        parser.error("set FRONTIER_MODEL and OPEN_WEIGHT_MODEL or pass both model arguments")
    validate_benchmark_source(args.benchmark, allow_synthetic=args.allow_synthetic)
    cases = load_benchmark_cases(args.benchmark)
    providers = {
        "frontier": (args.frontier_model, model_client_from_environment(prefix="FRONTIER")),
        "open_weight": (args.open_weight_model, model_client_from_environment(prefix="OPEN_WEIGHT")),
    }
    report = run_model_comparison(cases, providers, work_dir=args.work_dir,
                                  output_path=args.output, repetitions=args.repetitions)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return completion_exit_code(bool(report.get("comparison_contract", {}).get("complete")))


if __name__ == "__main__":
    raise SystemExit(main())
