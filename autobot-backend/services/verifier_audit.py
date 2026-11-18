# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Audit trail for a verifier pass that gave no reading (#21844).

The verifier fails open by owner decision, so an action can run with no adversarial check at all. Every such pass
is an audit event (``verifier.degraded``) carrying the tool, the degradation class and the model, so a person can
see how often and why the check was skipped; a log line alone is not a record.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.verifier_degradation import VerifierDegradation
from services.audit.taxonomy import AuditAction

logger = get_logger(__name__)


async def audit_verifier_degraded(result: Any, session_id: str | None = None) -> bool:
    """Record ``verifier.degraded`` when *result* carries a degradation; True when an event was written."""
    if getattr(result, "degradation", VerifierDegradation.NONE) is VerifierDegradation.NONE:
        return False
    from services.audit_logger import audit_log

    details = {
        "tool": result.tool_name,
        "degradation": result.degradation.value,
        "model": result.model_used,
        "provider": result.provider_used,
        "verdict": result.verdict.value,
    }
    try:
        return await audit_log(
            AuditAction.VERIFIER_DEGRADED.value,
            "attempted",
            session_id=session_id,
            resource=result.tool_name,
            details=details,
        )
    except Exception as exc:  # noqa: BLE001 - the audit write must never break the action path
        logger.warning("verifier.degraded audit event not written (%s: %r)", type(exc).__name__, exc)
        return False
