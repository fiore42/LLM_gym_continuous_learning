"""Run one incremental source update and refresh the searchable library."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..shared.atomic import atomic_write_text
from .evidence import build_index, collect_records
from ..shared.loops import LoopType, new_loop_context


def run_library_update(
    *,
    project_root: str | Path = ".",
    ingest_args: list[str] | None = None,
    run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    checkpoint_path: str | Path = "data/library-update.json",
) -> dict[str, object]:
    """Run incremental ingestion, then index whatever completed successfully."""
    root = Path(project_root)
    context = new_loop_context(LoopType.LIBRARY_UPDATE)
    command = [sys.executable, str(root / "scripts" / "ingest_all_configured_sources.py"), *(ingest_args or [])]
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        ingestion = run_command(command, cwd=root, check=False)
        ingestion_exit_code = int(ingestion.returncode)
    except OSError as exc:
        ingestion_exit_code = 127
        ingestion = None
        ingestion_error = str(exc)
    else:
        ingestion_error = None

    records, warnings = collect_records(root / "source")
    index_summary = build_index(records, root / "data" / "evidence.sqlite3")
    status = "COMPLETED" if ingestion_exit_code == 0 else "COMPLETED_WITH_FAILURES"
    result: dict[str, object] = {
        "status": status,
        **context,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ingestion_exit_code": ingestion_exit_code,
        "ingestion_error": ingestion_error,
        "index": index_summary,
        "index_warnings": warnings[:100],
        "index_warning_count": len(warnings),
        "completed_stages": ["ingest", "index", "checkpoint"],
    }
    destination = root / checkpoint_path
    if not destination.is_absolute():
        destination = root / checkpoint_path
    atomic_write_text(destination, json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result
