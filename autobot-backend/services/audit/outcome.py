# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attempt and outcome rows for an audit-first control (#21375).

A control that must be on the trail BEFORE it runs writes an ``attempted`` row, changes state, then writes
the outcome row (``success``, ``denied`` or ``failed``) linked to it by ``attempt_id``. The trail then never
claims a change that did not happen: a bare ``attempted`` row is an intent, and only its own ``success`` row
counts it as done. This is the ONE implementation of that shape: the heartbeat controls call it directly and
the secret routes reach it through ``api.secrets_audit.audit_secret_op``; no route writes its own pair.
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
DENIED = "denied"  # a refusal (permission, dependents, a conflict): nothing was changed on purpose

#: Stable log marker: a bare ``attempted`` row whose change happened can be found by searching for it.
OUTCOME_MISSING_MARKER = "AUDIT_OUTCOME_MISSING"

#: The fixed 503 text of an attempt that could not be written; a caller's tests and clients match on it.
AUDIT_UNAVAILABLE_DETAIL = "Audit trail unavailable; nothing was changed"


def attempt_unrecorded() -> HTTPException:
    """The 503 for an attempt row that could not be written: nothing has been changed."""
    return HTTPException(status_code=503, detail=AUDIT_UNAVAILABLE_DETAIL)


async def _written(event: AuditEvent) -> bool:
    """Whether the durable row was committed; a write that raises is a failed write, logged by class name only."""
    try:
        return await record_committed(event)
    except Exception as exc:  # noqa: BLE001 -- an audit write is reported by its caller, never allowed to escape
        logger.error("audit: write of %s raised %s", event.action, type(exc).__name__)
        return False


async def record_audit_attempt(event: AuditEvent) -> None:
    """Durably record the intent; raise 503 when the write fails so nothing is changed."""
    if not await _written(replace(event, outcome=ATTEMPTED)):
        logger.error("audit: attempt row for %s (%s) was not written; refusing with 503", event.action, event.id)
        raise attempt_unrecorded()


async def record_audit_outcome(
    event: AuditEvent, outcome: str, failure: str | None = None, *, attempt_id: str | None = None
) -> bool:
    """Record how the attempt ended, linked to it by ``attempt_id``; False (logged) when the write fails.

    *failure* is an exception class name or a fixed reason, never a message: exception text can echo a value.
    The change has already happened or failed by now, so an unwritable outcome is logged, not raised.
    *attempt_id* is the id of the attempt row when *event* is the outcome's own event rather than the
    attempt's (the default: the attempt's event is reused and its id is the link).
    """
    link = attempt_id or event.id
    metadata = {**(event.metadata or {}), "attempt_id": link}
    if failure:
        metadata["failure"] = failure
    written = await _written(replace(event, id=str(uuid.uuid4()), outcome=outcome, metadata=metadata))
    if not written:
        logger.error(
            "%s attempt_id=%s control=%s agent=%s outcome=%s: the attempt row has no outcome row",
            OUTCOME_MISSING_MARKER,
            link,
            event.action,
            event.resource_id,
            outcome,
        )
    return written
