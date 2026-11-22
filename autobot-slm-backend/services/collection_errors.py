# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one decision between an operational failure and a programming error (#21334).

A lookup that feeds an operator-visible verdict ("nothing to update") must not turn
an error into an empty result. Expected operational failures are reported as
"could not determine"; anything else is a programming error and propagates.
``mark_stage_failed`` is where an update-all stage and its job record that verdict.
"""

from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# DB session and query failures (SQLAlchemyError) and filesystem reads (OSError).
OPERATIONAL_COLLECTION_ERRORS = (SQLAlchemyError, OSError)


def operational_failure_reason(what: str, exc: BaseException) -> str:
    """Return the operator-facing "could not determine" reason for an operational *exc*.

    Re-raises *exc* when it is not an expected operational error, so a programming
    error is never reported as an empty, successful result.
    """
    if not isinstance(exc, OPERATIONAL_COLLECTION_ERRORS):
        raise exc
    logger.warning("Could not determine %s: %s", what, exc)
    return f"Could not determine {what}: {type(exc).__name__}"


def mark_stage_failed(job: Any, stage: Any, reason: str, failed_status: str, now: Any) -> None:
    """Mark *stage* and its *job* failed with one reason (capped at 300 characters)."""
    stage.status = failed_status
    stage.message = reason[:300]
    stage.completed_at = now
    job.status = "failed"
    job.failure_reason = reason[:300]
    job.completed_at = now
