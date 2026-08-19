"""Interactive progress display for multi-source ingestion."""

from __future__ import annotations

import re
import threading
import time


_TRANSCRIPTION_QUEUED = re.compile(
    r"(?:\[(?P<prefix>[^\]]+)\]\s*)?Transcription queued for (?P<video>\S+): duration=(?P<duration>[0-9.]+|unknown)s"
)


class ProgressDashboard:
    """Render one continuously updated line for an interactive run."""

    def __init__(self, *, enabled: bool = True, initial_ratio: float = 0.35) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()
        self.total = 0
        self.completed = 0
        self.failed = 0
        self._current: dict[str, object] | None = None
        self._processing_ratio = initial_ratio
        self._ratio_samples: list[float] = []
        self._last_stage = ""

    def planned(self, video_id: str, title: str | None = None) -> None:
        if not self.enabled:
            return
        with self._lock:
            self.total += 1
            self._render_locked()

    def started(self, video_id: str, title: str | None = None) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._last_stage = f"starting {video_id}"
            self._render_locked()

    def finished(self, video_id: str, status: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            current = self._current
            if status == "COMPLETED" or status.startswith("SKIPPED_"):
                self.completed += 1
            elif status.startswith("FAILED"):
                self.failed += 1
            if current and current.get("video_id") == video_id:
                duration = current.get("duration")
                started = current.get("started")
                if isinstance(duration, (int, float)) and isinstance(started, (int, float)):
                    elapsed = max(time.monotonic() - started, 0.001)
                    self._ratio_samples.append(elapsed / duration)
                    self._ratio_samples = self._ratio_samples[-10:]
                    self._processing_ratio = sum(self._ratio_samples) / len(self._ratio_samples)
                self._current = None
            self._last_stage = f"finished {video_id}: {status.lower()}"
            self._render_locked()

    def stage(self, message: str) -> None:
        """Consume detailed stage messages while retaining a single display line."""
        if not self.enabled:
            return
        match = _TRANSCRIPTION_QUEUED.search(message)
        with self._lock:
            if match:
                duration_text = match.group("duration")
                duration = None if duration_text == "unknown" else float(duration_text)
                self._current = {
                    "video_id": match.group("video"),
                    "duration": duration,
                    "started": None,
                }
                self._last_stage = "queued"
            elif "starting whisper_transcription" in message.lower():
                if self._current:
                    self._current["started"] = time.monotonic()
                self._last_stage = "transcribing"
            elif "whisper_transcription" in message.lower():
                self._last_stage = message.split(":", 1)[0]
            self._render_locked()

    def _render_locked(self) -> None:
        if not self.enabled:
            return
        current_text = "waiting"
        if self._current:
            video_id = str(self._current["video_id"])
            duration = self._current.get("duration")
            started = self._current.get("started")
            if isinstance(duration, (int, float)) and isinstance(started, (int, float)):
                elapsed = max(time.monotonic() - started, 0.0)
                raw_estimate = elapsed / max(duration * self._processing_ratio, 0.001) * 100
                estimate = min(99.0, raw_estimate)
                speed = duration / max(elapsed, 0.001)
                suffix = "+" if raw_estimate >= 99.0 else ""
                current_text = f"{video_id} {estimate:5.1f}%{suffix} ({speed:4.1f}x realtime)"
            elif self._current:
                current_text = f"{video_id} queued"
        line = (
            f"Transcripts: {self.completed}/{self.total} completed | "
            f"failed: {self.failed} | current: {current_text}"
        )
        print(f"\r{line:<120}", end="", flush=True)

    def finish(self) -> None:
        if self.enabled:
            with self._lock:
                self._render_locked()
                print(flush=True)
