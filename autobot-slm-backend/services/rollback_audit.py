# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit trail entry for a rollback (#20214).

A rollback is written to ``audit_logs`` (the audit trail's system of record) through the one row
constructor, ``audit_row``. The first entry is committed BEFORE the run starts: if the trail cannot
record the request, the rollback is refused rather than run unrecorded. ``outcome`` is one of
``success`` / ``denied`` / ``failed`` / ``error`` and nothing else.

``success`` on the first entry means "authorised and about to run" (``details.phase`` says so); how
the run ended is the update-all job and ``GET /code-sync/update-all/report``. When the run ends in
the same process an entry with the final outcome is added; a run cut by the SLM's own restart
finishes in a process that does not know it was a rollback, so that last entry is not written.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: ``AuditAction.CODE_ROLLBACK`` in autobot-backend/services/audit/taxonomy.py.
ACTION = "code.rollback"
RESOURCE_TYPE = "code_version"

SUCCESS, DENIED, FAILED, ERROR = "success", "denied", "failed", "error"
OUTCOMES = frozenset({SUCCESS, DENIED, FAILED, ERROR})

PHASE_REQUESTED = "requested"
PHASE_FINISHED = "finished"


class AuditUnavailable(Exception):
    """The entry could not be made durable."""


async def record_rollback(*, actor: str | None, commit: str | None, outcome: str, phase: str, **details: Any) -> None:
    """Commit one audit entry; raises ``AuditUnavailable`` when it cannot be stored."""
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown audit outcome: {outcome!r}")
    from autobot_shared.user_management.audit_rows import audit_row
    from user_management.database import get_slm_session

    try:
        async with get_slm_session() as session:
            session.add(
                audit_row(
                    action=ACTION,
                    resource_type=RESOURCE_TYPE,
                    resource=commit,
                    actor=actor,
                    outcome=outcome,
                    details={"phase": phase, **details},
                )
            )
    except Exception as exc:
        logger.error("rollback: audit entry could not be stored (%s)", type(exc).__name__)
        raise AuditUnavailable(type(exc).__name__) from exc
