"""Project-wide append-only run logging with credential redaction."""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .status import status_category
from .loops import LoopType


_SECRET_KEY = re.compile(r"(password|passwd|token|secret|api[_-]?key|cookie|authorization)", re.I)
_SECRET_VALUE = re.compile(r"(?i)(bearer\s+)[^\s]+")
_SIGNED_URL = re.compile(r"(https?://[^\s\"']+\?)[^\s\"']+")
_MAX_STRING = 2000


def _redact(value: Any, key: str | None = None) -> Any:
    if key and _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        redacted = []
        redact_next = False
        for item in value:
            if redact_next:
                redacted.append("[REDACTED]")
                redact_next = False
                continue
            if isinstance(item, str) and item.startswith("--") and _SECRET_KEY.search(item):
                redacted.append(item)
                redact_next = True
            else:
                redacted.append(_redact(item))
        return redacted
    if isinstance(value, str):
        value = _SIGNED_URL.sub(r"\1[QUERY_REDACTED]", value)
        value = _SECRET_VALUE.sub(r"\1[REDACTED]", value)
        if len(value) > _MAX_STRING:
            return value[:_MAX_STRING] + "...[TRUNCATED]"
        return value
    return value


class RunLogger:
    """Append structured events to one chronological JSONL log."""

    def __init__(self, path: str | Path = "data/run-log.jsonl", run_id: str | None = None,
                 loop_type: LoopType | str | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or uuid.uuid4().hex
        self.loop_type = str(loop_type) if loop_type else None
        self._write_lock = threading.Lock()

    def event(
        self,
        *,
        stage: str,
        category: str = "INFO",
        status: str | None = None,
        operation: str | None = None,
        parameters: Any = None,
        output: Any = None,
        error: str | None = None,
        parent_event_id: str | None = None,
        artifact_paths: list[str] | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        duration_ms: float | None = None,
        loop_type: LoopType | str | None = None,
    ) -> str:
        event_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "run_id": self.run_id,
            "loop_type": str(loop_type) if loop_type else self.loop_type,
            "event_id": event_id,
            "parent_event_id": parent_event_id,
            "logged_at": now,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "operation": operation,
            "stage": stage,
            "category": category,
            "status": status,
            "parameters": _redact(parameters),
            "output": _redact(output),
            "error": _redact(error),
            "artifact_paths": _redact(artifact_paths or []),
        }
        with self._write_lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return event_id


def log_script_run(
    logger: RunLogger,
    *,
    operation: str,
    parameters: dict[str, Any],
    output: Any,
    status: str,
    artifact_paths: list[str] | None = None,
) -> None:
    category = status_category(status)
    logger.event(
        operation=operation,
        stage="script",
        category=category,
        status=status,
        parameters=parameters,
        output=output,
        artifact_paths=artifact_paths,
    )
