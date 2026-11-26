# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Audit trail for a verifier pass that gave no reading (#21844).

The verifier fails open by owner decision, so an action can run with no adversarial check at all. Every such pass
is an audit event (``verifier.degraded``) carrying the tool, the degradation class and the model, so a person can
see how often and why the check was skipped; a log line alone is not a record. A timeout is also counted per tool
in metrics (``autobot_verifier_timeout_total``), so the rate is readable without querying the audit log.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.verifier_degradation import VerifierDegradation
from services.audit.taxonomy import AuditAction

logger = get_logger(__name__)


def count_verifier_timeout(result: Any) -> bool:
    """Count a verifier TIMEOUT per tool in metrics (#21844); True when counted. A metrics fault never stops it."""
    if getattr(result, "degradation", None) is not VerifierDegradation.TIMEOUT:
        return False
    try:
        from autobot_shared.monitoring.metrics.quality_gates import quality_gate_metrics

        quality_gate_metrics().record_verifier_timeout(str(result.tool_name))
        return True
    except Exception as exc:  # noqa: BLE001 - observability must not break the action path
        logger.warning("verifier timeout not counted (%s: %r)", type(exc).__name__, exc)
        return False


async def audit_verifier_degraded(result: Any, session_id: str | None = None, user_id: Any = None) -> bool:
    """Record ``verifier.degraded`` when *result* carries a degradation; True when an event was written.

    *user_id* is the server-verified user when the caller has one in scope; the session id is kept either way.
    """
    if getattr(result, "degradation", VerifierDegradation.NONE) is VerifierDegradation.NONE:
        return False
    count_verifier_timeout(result)
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
            user_id=str(user_id) if user_id else None,
            session_id=session_id,
            resource=result.tool_name,
            details=details,
        )
    except Exception as exc:  # noqa: BLE001 - the audit write must never break the action path
        logger.warning("verifier.degraded audit event not written (%s: %r)", type(exc).__name__, exc)
        return False
