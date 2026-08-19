"""Load validated project-wide ingestion parameters."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PARAMETERS_PATH = PROJECT_ROOT / "config" / "PARAMETERS.json"


def load_parameters(path: str | Path = PARAMETERS_PATH) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ingestion = data.get("ingestion")
    tools = data.get("tools")
    if not isinstance(ingestion, dict) or not isinstance(tools, dict):
        raise ValueError("config/PARAMETERS.json must contain ingestion and tools objects")
    default_days = ingestion.get("default_window_days")
    max_days = ingestion.get("max_window_days")
    if not isinstance(default_days, int) or not isinstance(max_days, int):
        raise ValueError("ingestion window parameters must be integers")
    if default_days < 1 or max_days < 1 or default_days > max_days:
        raise ValueError("ingestion window parameters must satisfy 1 <= default <= max")
    for key in ("short_video_max_seconds", "screenshot_interval_seconds"):
        if not isinstance(ingestion.get(key), int) or ingestion[key] < 1:
            raise ValueError(f"ingestion.{key} must be a positive integer")
    for key in ("yt_dlp", "ffmpeg", "whisper_script", "ffprobe"):
        if not isinstance(tools.get(key), str) or not tools[key]:
            raise ValueError(f"tools.{key} must be a non-empty string")
    runtime = data.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("config/PARAMETERS.json must contain a runtime object")
    timeout = runtime.get("subprocess_timeout_seconds")
    if not isinstance(timeout, int) or timeout < 1:
        raise ValueError("runtime.subprocess_timeout_seconds must be a positive integer")
    agent = data.get("agent")
    if not isinstance(agent, dict):
        raise ValueError("config/PARAMETERS.json must contain an agent object")
    for key in ("max_rounds", "max_minutes", "max_model_calls", "max_output_tokens",
                "max_model_calls_ceiling"):
        if not isinstance(agent.get(key), int) or agent[key] < 1:
            raise ValueError(f"agent.{key} must be a positive integer")
    for key in ("max_cost_usd", "max_cost_usd_per_task", "max_cost_usd_ceiling"):
        if not isinstance(agent.get(key), (int, float)) or agent[key] <= 0:
            raise ValueError(f"agent.{key} must be positive")
    digest = data.get("digest")
    if not isinstance(digest, dict):
        raise ValueError("config/PARAMETERS.json must contain a digest object")
    per_day = digest.get("max_cost_usd_per_window_day")
    if not isinstance(per_day, (int, float)) or per_day <= 0:
        raise ValueError("digest.max_cost_usd_per_window_day must be positive")
    for key in ("stop_at_budget_fraction", "minimum_eval_pass_fraction"):
        value = agent.get(key)
        if not isinstance(value, (int, float)) or not 0 < value <= 1:
            raise ValueError(f"agent.{key} must be between 0 and 1")
    comparison = data.get("model_evaluation")
    if not isinstance(comparison, dict):
        raise ValueError("config/PARAMETERS.json must contain a model_evaluation object")
    for key in ("max_minutes", "max_model_calls"):
        if not isinstance(comparison.get(key), int) or comparison[key] < 1:
            raise ValueError(f"model_evaluation.{key} must be a positive integer")
    if not isinstance(comparison.get("max_cost_usd"), (int, float)) or comparison["max_cost_usd"] <= 0:
        raise ValueError("model_evaluation.max_cost_usd must be positive")
    value = comparison.get("stop_at_budget_fraction")
    if not isinstance(value, (int, float)) or not 0 < value <= 1:
        raise ValueError("model_evaluation.stop_at_budget_fraction must be between 0 and 1")
    x = data.get("x")
    if not isinstance(x, dict):
        raise ValueError("config/PARAMETERS.json must contain an x object")
    for key in ("include_replies", "include_retweets"):
        if not isinstance(x.get(key), bool):
            raise ValueError(f"x.{key} must be a boolean")
    max_results = x.get("max_results_per_request")
    if not isinstance(max_results, int) or not 5 <= max_results <= 100:
        raise ValueError("x.max_results_per_request must be between 5 and 100")
    for key in ("download_media", "download_linked_documents"):
        if not isinstance(x.get(key), bool):
            raise ValueError(f"x.{key} must be a boolean")
    for key in ("max_media_bytes", "max_document_bytes", "download_timeout_seconds"):
        if not isinstance(x.get(key), int) or x[key] < 1:
            raise ValueError(f"x.{key} must be a positive integer")
    for key in ("post_read_cost_usd", "user_read_cost_usd"):
        if not isinstance(x.get(key), (int, float)) or x[key] < 0:
            raise ValueError(f"x.{key} must be a non-negative number")
    return data


def ingestion_parameters() -> dict[str, int]:
    return load_parameters()["ingestion"]


def tool_parameters() -> dict[str, str]:
    tools = dict(load_parameters()["tools"])
    tools["yt_dlp"] = os.environ.get("YTDLP_PATH", tools["yt_dlp"])
    tools["whisper_script"] = os.environ.get("WHISPER_SCRIPT", tools["whisper_script"])
    tools["ffmpeg"] = os.environ.get("FFMPEG_PATH", tools["ffmpeg"])
    tools["ffprobe"] = os.environ.get("FFPROBE_PATH", tools["ffprobe"])
    return tools


def runtime_parameters() -> dict[str, int]:
    return dict(load_parameters()["runtime"])


def agent_parameters() -> dict[str, Any]:
    return dict(load_parameters()["agent"])


def digest_parameters() -> dict[str, Any]:
    return dict(load_parameters()["digest"])


def model_evaluation_parameters() -> dict[str, Any]:
    return dict(load_parameters()["model_evaluation"])


def x_parameters() -> dict[str, Any]:
    return dict(load_parameters()["x"])


def estimate_x_api_cost(*, post_reads: int, user_lookups: int) -> float:
    prices = x_parameters()
    return round(
        post_reads * float(prices["post_read_cost_usd"])
        + user_lookups * float(prices["user_read_cost_usd"]),
        6,
    )
