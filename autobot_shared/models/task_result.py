# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""TaskResult dataclass and builder functions for standardised task handler responses.

Issue #3545: Replaces 2200+ raw result dicts across task handler files with
typed builder functions that enforce a consistent schema.

Issue #3564: Adds ``extra`` field so callers can merge additional top-level keys
into the serialised dict without post-hoc dict mutation.

Usage::

    from autobot_shared.models.task_result import task_success, task_error, task_pending

    return task_success("Command executed securely.", data={"output": output})
    return task_error("Command failed.", error=stderr)
    return task_error("Command failed.", error=stderr, extra={"output": out, "returncode": rc})
    return task_pending()
"""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TaskResult:
    """Structured result returned by every task handler.

    Attributes:
        status:  Outcome category — "success", "error", or "pending".
        message: Human-readable description of the outcome.
        data:    Optional payload returned to the caller (arbitrary structure).
        error:   Optional error detail string (populated on failure).
        extra:   Optional mapping of additional top-level keys to merge into the
                 serialised dict.  Keys in ``extra`` take precedence over the
                 fixed fields when names collide.
    """

    status: str
    message: str
    data: Any = None
    error: str | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialise to a plain dict, omitting fixed-field keys whose value is None.

        ``extra`` keys are merged last so they can extend (but not accidentally
        overwrite) the standard fields.  The ``extra`` key itself is never
        included in the output.
        """
        base = {k: v for k, v in asdict(self).items() if k != "extra" and v is not None}
        return {**base, **self.extra}


def task_success(message: str, data: Any = None, extra: dict | None = None) -> dict:
    """Return a success result dict.

    Args:
        message: Description of the successful outcome.
        data:    Optional structured payload to include in the response.
        extra:   Optional mapping of additional top-level keys to merge into
                 the serialised dict.

    Returns:
        Dict with ``status="success"`` and the supplied fields.
    """
    return TaskResult("success", message, data=data, extra=extra or {}).to_dict()


def task_error(
    message: str,
    error: str | None = None,
    extra: dict | None = None,
) -> dict:
    """Return an error result dict.

    Args:
        message: Human-readable description of what went wrong.
        error:   Optional low-level error detail (e.g. stderr, exception text).
        extra:   Optional mapping of additional top-level keys to merge into
                 the serialised dict.

    Returns:
        Dict with ``status="error"`` and the supplied fields.
    """
    return TaskResult("error", message, error=error, extra=extra or {}).to_dict()


def task_pending(message: str = "Task pending approval", extra: dict | None = None) -> dict:
    """Return a pending result dict.

    Args:
        message: Optional override for the default pending message.
        extra:   Optional mapping of additional top-level keys to merge into
                 the serialised dict.

    Returns:
        Dict with ``status="pending"`` and the supplied message.
    """
    return TaskResult("pending", message, extra=extra or {}).to_dict()


def task_pending_approval(
    message: str = "Task pending approval",
    extra: dict | None = None,
) -> dict:
    """Return a pending-approval result dict.

    Used when a task has been queued and is waiting for explicit user
    confirmation before execution (distinct from a generic "pending" state).

    Args:
        message: Optional override for the default pending-approval message.
        extra:   Optional mapping of additional top-level keys to merge into
                 the serialised dict.

    Returns:
        Dict with ``status="pending_approval"`` and the supplied message.
    """
    return TaskResult("pending_approval", message, extra=extra or {}).to_dict()
