"""Small, dependency-free project `.env` loader."""

from __future__ import annotations

import os
import re
from pathlib import Path


_ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def load_dotenv(path: str | Path | None = None, *, override: bool = False) -> Path | None:
    """Load simple KEY=VALUE entries without printing or returning secrets."""

    env_path = Path(path) if path else Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ASSIGNMENT.match(line)
        if not match:
            continue
        key, value = match.groups()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value
    return env_path


def has_env_value(name: str) -> bool:
    """Return whether an environment variable exists and is non-empty."""

    return bool(os.environ.get(name, "").strip())
