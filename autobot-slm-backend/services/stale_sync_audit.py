# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The audit trail entry for the stale code-sync file cleanup (#22033), the shape of ``rollback_audit``.

Written to ``audit_logs`` through ``rollback_audit.record_audit_step``, the SLM's one writer of that table
(``audit_row`` underneath), so no second audit store exists (#17225). The ``intent`` entry is committed
BEFORE the approval is claimed and before any file is removed: if the trail cannot record it, nothing is
claimed and nothing is removed (fail closed). ``outcome`` is ``success`` / ``denied`` / ``failed`` / ``error``;
details carry counts, the approval id and per-path results, never a file's contents.
"""

from __future__ import annotations

from typing import Any

from services.rollback_audit import DENIED, ERROR, FAILED, OUTCOMES, SUCCESS, AuditRowUnavailable, record_audit_step

#: ``AuditAction.CODE_SYNC_STALE_FILES_CLEANUP`` in autobot-backend/services/audit/taxonomy.py (the SLM backend
#: cannot import that package; ``rollback_audit.ACTION`` does the same).
ACTION = "code_sync.stale_files.cleanup"
RESOURCE_TYPE = "node"

PHASE_PROPOSED = "proposed"
PHASE_INTENT = "intent"
PHASE_FINISHED = "finished"


class StaleFileAuditUnavailable(Exception):
    """The entry could not be made durable."""


async def record_cleanup_step(*, actor: str | None, node_id: str, outcome: str, phase: str, **details: Any) -> None:
    """Commit one audit entry through the SLM's one ``audit_logs`` writer; raises ``StaleFileAuditUnavailable``."""
    try:
        await record_audit_step(
            action=ACTION,
            resource_type=RESOURCE_TYPE,
            resource=node_id,
            actor=actor,
            outcome=outcome,
            phase=phase,
            **details,
        )
    except AuditRowUnavailable as exc:
        raise StaleFileAuditUnavailable(str(exc)) from exc


__all__ = [
    "ACTION",
    "DENIED",
    "ERROR",
    "FAILED",
    "OUTCOMES",
    "PHASE_FINISHED",
    "PHASE_INTENT",
    "PHASE_PROPOSED",
    "SUCCESS",
    "StaleFileAuditUnavailable",
    "record_cleanup_step",
]
