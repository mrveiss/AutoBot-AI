# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit trail entry for the stale code-sync file cleanup (#22033), the shape of ``rollback_audit``.

Written to ``audit_logs`` through the one row constructor, ``audit_row``. The ``intent`` entry is committed
BEFORE the approval is claimed and before any file is removed: if the trail cannot record it, nothing is
claimed and nothing is removed (fail closed). ``outcome`` is ``success`` / ``denied`` / ``failed`` / ``error``;
details carry counts, the approval id and per-path results, never a file's contents.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: ``AuditAction.CODE_SYNC_STALE_FILES_CLEANUP`` in autobot-backend/services/audit/taxonomy.py (the SLM backend
#: cannot import that package; ``rollback_audit.ACTION`` does the same).
ACTION = "code_sync.stale_files.cleanup"
RESOURCE_TYPE = "node"

SUCCESS, DENIED, FAILED, ERROR = "success", "denied", "failed", "error"
OUTCOMES = frozenset({SUCCESS, DENIED, FAILED, ERROR})

PHASE_PROPOSED = "proposed"
PHASE_INTENT = "intent"
PHASE_FINISHED = "finished"


class StaleFileAuditUnavailable(Exception):
    """The entry could not be made durable."""


async def record_cleanup_step(*, actor: str | None, node_id: str, outcome: str, phase: str, **details: Any) -> None:
    """Commit one audit entry; raises ``StaleFileAuditUnavailable`` when it cannot be stored."""
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
                    resource=node_id,
                    actor=actor,
                    outcome=outcome,
                    details={"phase": phase, **details},
                )
            )
    except Exception as exc:
        logger.error("stale-file cleanup: audit entry could not be stored (%s)", type(exc).__name__)
        raise StaleFileAuditUnavailable(type(exc).__name__) from exc
