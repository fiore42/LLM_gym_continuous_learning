#!/usr/bin/env python3
"""Check required project configuration without printing secret values.

The checks are scoped to the platforms present in the source manifest.  This
keeps an X-only run independent of YouTube credentials and vice versa.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_gym.shared.config import has_env_value, load_dotenv
from llm_gym.sources.manifest import load_sources_markdown
from llm_gym.shared.settings import load_parameters, tool_parameters


def required_tools(platforms: set[str], configured: dict[str, str]) -> dict[str, str]:
    """Return only executables needed by the configured source platforms."""
    names: set[str] = set()
    if "youtube" in platforms:
        names.update({"yt_dlp", "ffmpeg", "ffprobe", "whisper_script"})
    if "x" in platforms:
        names.update({"ffmpeg", "ffprobe", "whisper_script"})
    return {name: configured[name] for name in sorted(names)}


def missing_tools(tools: dict[str, str], *, root: Path) -> list[str]:
    """Return configured tools that are neither on PATH nor an existing file.

    A relative path is resolved against the project root rather than the
    current working directory, so the check gives the same answer wherever it
    is run from.
    """
    missing = []
    for name, command in sorted(tools.items()):
        if shutil.which(command) is not None:
            continue
        candidate = Path(command)
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.is_file():
            missing.append(name)
    return missing


def required_agent_environment(env: dict[str, str], *, prefix: str = "AGENT") -> list[str]:
    """Return missing non-secret settings for one model provider environment."""
    provider = env.get(f"{prefix}_PROVIDER", "openai-compatible").strip().lower()
    required = [f"{prefix}_MODEL", f"{prefix}_API_KEY"]
    if provider not in {"anthropic", "openai", "openai-compatible"}:
        return [f"{prefix}_PROVIDER unsupported: {provider}"]
    if prefix == "AGENT" and provider == "anthropic" and not env.get(f"{prefix}_API_KEY", "").strip():
        required[-1] = "ANTHROPIC_API_KEY"
    return [name for name in required if not env.get(name, "").strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--noout", action="store_true", help="Suppress normal output")
    parser.add_argument("--manifest", default="config/SOURCES.md", help="Source manifest path")
    parser.add_argument("--check-agent", action="store_true", help="Also validate bounded agent provider settings")
    parser.add_argument("--check-model-comparison", action="store_true",
                        help="Also validate frontier and open-weight provider settings")
    args = parser.parse_args()
    # Load .env before reading any setting. Tool paths are environment
    # overridable, so validating them first checks the packaged defaults and
    # reports a configured tool as missing.
    root = Path(__file__).resolve().parents[1]
    loaded_path = load_dotenv()
    try:
        load_parameters()
        manifest = load_sources_markdown(args.manifest)
        platforms = {str(source["platform"]) for source in manifest["sources"]}
        tools = required_tools(platforms, tool_parameters())
        missing = missing_tools(tools, root=root)
        if missing:
            raise ValueError(f"required executable(s) not found: {', '.join(missing)}")
    except (OSError, ValueError) as exc:
        print(f"Global parameter validation failed: {exc}", file=sys.stderr)
        return 1

    missing_credentials = []
    if "x" in platforms and not has_env_value("X_API_BEARER_TOKEN"):
        missing_credentials.append("X_API_BEARER_TOKEN")
    if args.check_agent:
        missing_credentials.extend(required_agent_environment(dict(os.environ)))
    if args.check_model_comparison:
        missing_credentials.extend(required_agent_environment(dict(os.environ), prefix="FRONTIER"))
        missing_credentials.extend(required_agent_environment(dict(os.environ), prefix="OPEN_WEIGHT"))
    if not args.noout:
        source = str(loaded_path) if loaded_path else "process environment"
        print(f"Platforms checked: {', '.join(sorted(platforms))}")
        print(f"Required executables checked: {', '.join(sorted(tools)) or 'none'}")
        print(f"YOUTUBE_API_KEY: {'configured' if has_env_value('YOUTUBE_API_KEY') else 'not configured (optional)'}")
        if "x" in platforms:
            print(f"X_API_BEARER_TOKEN: {'configured' if has_env_value('X_API_BEARER_TOKEN') else 'missing'}")
        if args.check_agent:
            print("Agent provider settings: checked")
        if args.check_model_comparison:
            print("Model comparison provider settings: checked")
        print(f"Environment values loaded from {source}")
    if missing_credentials:
        print(
            "Required credential(s) missing for configured platforms: "
            + ", ".join(missing_credentials),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
