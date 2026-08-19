"""Capture periodic screenshots for short videos without usable audio."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from ..shared.atomic import atomic_write_text
from ..shared.settings import ingestion_parameters, runtime_parameters, tool_parameters


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def capture_video_screenshots(
    video_path: str | Path,
    output_dir: str | Path,
    *,
    runner: CommandRunner = subprocess.run,
) -> int:
    """Capture one JPEG every configured interval, returning the frame count."""
    video = Path(video_path)
    destination = Path(output_dir)
    existing = sorted(destination.glob("screenshot_*.jpg"))
    if existing:
        return len(existing)
    destination.mkdir(parents=True, exist_ok=True)
    interval = ingestion_parameters()["screenshot_interval_seconds"]
    result = runner(
        [tool_parameters()["ffmpeg"], "-y", "-i", str(video), "-vf", f"fps=1/{interval}",
         "-q:v", "2", str(destination / "screenshot_%05d.jpg")],
        check=False, capture_output=True, text=True,
        timeout=runtime_parameters()["subprocess_timeout_seconds"],
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "screenshot extraction failed").strip()
        raise RuntimeError(detail[-1000:])
    frames = sorted(destination.glob("screenshot_*.jpg"))
    atomic_write_text(
        destination / "manifest.json",
        json.dumps({"interval_seconds": interval, "video": str(video), "count": len(frames)}, indent=2) + "\n",
    )
    return len(frames)
