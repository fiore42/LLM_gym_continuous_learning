"""Shared status classification; warnings never become failures."""

from __future__ import annotations


def is_failure_status(status: str | None) -> bool:
    return bool(status) and (status.startswith("FAILED") or status == "COMPLETED_WITH_FAILURES")


def is_warning_status(status: str | None) -> bool:
    return bool(status) and (status.startswith("SKIPPED_") or status == "COMPLETED_WITH_WARNINGS")


def status_category(status: str | None) -> str:
    if is_failure_status(status):
        return "FAILURE"
    if is_warning_status(status):
        return "WARNING"
    return "INFO"


def exit_code(status: str | None) -> int:
    return 1 if is_failure_status(status) else 0


_SUCCESSFUL_TASK_OUTCOMES = frozenset({
    "COMPLETED", "COMPLETED_AFTER_RETRY", "INSUFFICIENT_EVIDENCE",
    "CONFLICTING_EVIDENCE",
})


def task_outcome_exit_code(outcome: str | None) -> int:
    """Return success only for terminal outcomes safe to consume as results."""
    return 0 if outcome in _SUCCESSFUL_TASK_OUTCOMES else 1


def completion_exit_code(complete: bool) -> int:
    """Return success only when a multi-unit operation completed its contract."""
    return 0 if complete else 1
