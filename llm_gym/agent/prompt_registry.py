"""Immutable, versioned prompt definitions used by agent tasks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
# One directory per prompt family. load_prompt() returns the highest
# version_number in its root, so families must not share a directory: a
# second family reaching a higher number would silently hijack the first
# family's default.
PROMPT_ROOT = _PROMPTS / "agent_task"
VERIFICATION_PROMPT_ROOT = _PROMPTS / "verification"


@dataclass(frozen=True)
class PromptDefinition:
    prompt_id: str
    prompt_version: str
    version_number: int
    source_path: str
    system_template: str
    user_template: str
    revision_templates: dict[str, str]
    sha256: str


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _load(path: Path) -> PromptDefinition:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"prompt definition must be an object: {path}")
    required = ("prompt_id", "prompt_version", "version_number",
                "system_template", "user_template", "revision_templates")
    if any(field not in payload for field in required):
        raise ValueError(f"prompt definition is incomplete: {path}")
    if not isinstance(payload["version_number"], int):
        raise ValueError(f"prompt version_number must be an integer: {path}")
    if not isinstance(payload["revision_templates"], dict):
        raise ValueError(f"revision_templates must be an object: {path}")
    return PromptDefinition(
        prompt_id=str(payload["prompt_id"]),
        prompt_version=str(payload["prompt_version"]),
        version_number=payload["version_number"],
        source_path=str(path),
        system_template=str(payload["system_template"]),
        user_template=str(payload["user_template"]),
        revision_templates={str(key): str(value)
                            for key, value in payload["revision_templates"].items()},
        sha256=hashlib.sha256(_canonical_payload(payload)).hexdigest(),
    )


def load_prompt(*, version: str | None = None,
                root: str | Path = PROMPT_ROOT) -> PromptDefinition:
    """Load an explicit prompt version or the highest immutable version."""
    prompt_root = Path(root)
    definitions = [_load(path) for path in sorted(prompt_root.glob("*.json"))]
    if not definitions:
        raise FileNotFoundError(f"no prompt definitions found in {prompt_root}")
    if version is not None:
        matches = [item for item in definitions if item.prompt_version == version]
        if not matches:
            raise ValueError(f"prompt version not found: {version}")
        return matches[0]
    return max(definitions, key=lambda item: item.version_number)
