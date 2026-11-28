# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A stand-in for the audit store's one durable write, for tests of a control that writes through
``services.audit.outcome`` (#22130).

Every attempt and outcome row reaches ``services.audit.audit.record_committed``; patching that one seam sees them
all, whichever module wrote them. ``written`` is what the write answers: a bool, an exception to raise, or a
callable taking the event (so a test can fail one row only, e.g. the attempt).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from services.audit.taxonomy import AuditEvent

_SEAM = "services.audit.audit.record_committed"


class AuditDouble:
    """Records every event handed to the durable write, in order."""

    def __init__(self, written: bool | BaseException | Callable[[AuditEvent], bool] = True) -> None:
        self.written = written
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> bool:
        self.events.append(event)
        if isinstance(self.written, BaseException):
            raise self.written
        return self.written(event) if callable(self.written) else self.written

    def patch(self):
        """The context manager that routes the durable write to this double."""
        return patch(_SEAM, self.record)

    @property
    def results(self) -> list[str]:
        return [e.outcome for e in self.events]

    @property
    def details(self) -> list[dict[str, Any]]:
        return [(e.metadata or {}).get("details", {}) for e in self.events]

    @property
    def awaited(self) -> bool:
        return bool(self.events)


def unwritable_attempt(event: AuditEvent) -> bool:
    """``written`` for a store that refuses the ``attempted`` row only."""
    return event.outcome != "attempted"


def audit_log_shim(mock):
    """Route the durable write to *mock*, called as ``audit_log(action, result=..., details=..., durable=True)``.

    For a test written against ``audit_log`` that keeps its assertions on the call's ``result`` and ``details``
    and its ``side_effect``, while the rows now arrive through ``services.audit.outcome``.
    """

    async def record(event: AuditEvent) -> bool:
        return await mock(
            event.action,
            result=event.outcome,
            user_id=event.actor_id,
            session_id=event.session_id,
            resource=event.resource_id,
            durable=True,
            details=(event.metadata or {}).get("details", {}),
        )

    return record


def patch_audit_log(mock):
    """The context manager that routes the durable write to *mock* (see :func:`audit_log_shim`)."""
    return patch(_SEAM, audit_log_shim(mock))
