# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""TaskResult dataclass and builder functions for standardised task handler responses.

Issue #3545: Replaces 2200+ raw result dicts across task handler files with
typed builder functions that enforce a consistent schema.

Usage::

    from autobot_shared.models.task_result import task_success, task_error, task_pending

    return task_success("Command executed securely.", data={"output": output})
    return task_error("Command failed.", error=stderr)
    return task_pending()
"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class TaskResult:
    """Structured result returned by every task handler.

    Attributes:
        status:  Outcome category — "success", "error", or "pending".
        message: Human-readable description of the outcome.
        data:    Optional payload returned to the caller (arbitrary structure).
        error:   Optional error detail string (populated on failure).
    """

    status: str
    message: str
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict:
        """Serialise to a plain dict, omitting keys whose value is None."""
        return {k: v for k, v in asdict(self).items() if v is not None}


def task_success(message: str, data: Any = None) -> dict:
    """Return a success result dict.

    Args:
        message: Description of the successful outcome.
        data:    Optional structured payload to include in the response.

    Returns:
        Dict with ``status="success"`` and the supplied fields.
    """
    return TaskResult("success", message, data=data).to_dict()


def task_error(message: str, error: str | None = None) -> dict:
    """Return an error result dict.

    Args:
        message: Human-readable description of what went wrong.
        error:   Optional low-level error detail (e.g. stderr, exception text).

    Returns:
        Dict with ``status="error"`` and the supplied fields.
    """
    return TaskResult("error", message, error=error).to_dict()


def task_pending(message: str = "Task pending approval") -> dict:
    """Return a pending result dict.

    Args:
        message: Optional override for the default pending message.

    Returns:
        Dict with ``status="pending"`` and the supplied message.
    """
    return TaskResult("pending", message).to_dict()


def task_pending_approval(message: str = "Task pending approval") -> dict:
    """Return a pending-approval result dict.

    Used when a task has been queued and is waiting for explicit user
    confirmation before execution (distinct from a generic "pending" state).

    Args:
        message: Optional override for the default pending-approval message.

    Returns:
        Dict with ``status="pending_approval"`` and the supplied message.
    """
    return TaskResult("pending_approval", message).to_dict()
