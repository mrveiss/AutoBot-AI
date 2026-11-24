# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attempt and outcome rows for an audit-first control (#21375).

A control that must be on the trail BEFORE it runs writes an ``attempted`` row, changes state, then writes
the outcome row (``success`` or ``failed``). The trail then never claims a change that did not happen: a bare
``attempted`` row is an intent, and only its own ``success`` row counts it as done. This is the same shape the
secret routes use through ``services.audit_logger`` (``attempted`` then ``success`` / ``failed``), expressed
for :class:`AuditEvent` callers.
"""

import uuid
from dataclasses import replace

from fastapi import HTTPException

from autobot_shared.logging_manager import get_logger
from services.audit.audit import record_committed
from services.audit.taxonomy import AuditEvent

logger = get_logger(__name__)

ATTEMPTED = "attempted"
SUCCESS = "success"
FAILED = "failed"

#: Stable log marker: a bare ``attempted`` row whose change happened can be found by searching for it.
OUTCOME_MISSING_MARKER = "AUDIT_OUTCOME_MISSING"


async def record_audit_attempt(event: AuditEvent) -> None:
    """Durably record the intent; raise 503 when the write fails so nothing is changed."""
    if not await record_committed(replace(event, outcome=ATTEMPTED)):
        raise HTTPException(status_code=503, detail="Audit trail unavailable; nothing was changed")


async def record_audit_outcome(event: AuditEvent, outcome: str, failure: str | None = None) -> bool:
    """Record how the attempt ended, linked to it by ``attempt_id``; False (logged) when the write fails.

    *failure* is an exception class name or a fixed reason, never a message: exception text can echo a value.
    The change has already happened or failed by now, so an unwritable outcome is logged, not raised.
    """
    metadata = {**(event.metadata or {}), "attempt_id": event.id}
    if failure:
        metadata["failure"] = failure
    written = await record_committed(replace(event, id=str(uuid.uuid4()), outcome=outcome, metadata=metadata))
    if not written:
        logger.error(
            "%s attempt_id=%s control=%s agent=%s outcome=%s: the attempt row has no outcome row",
            OUTCOME_MISSING_MARKER,
            event.id,
            event.action,
            event.resource_id,
            outcome,
        )
    return written
