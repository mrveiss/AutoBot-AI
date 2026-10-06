# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Feed the unified audit bus into :class:`ThreatDetectionEngine` (#13562).

The engine shipped complete — six analyzers, an adaptive confidence learner, ML
anomaly detection, a response-action table — and nothing ever constructed it.
Three of its analyzers crashed on every detection for an unknown period and the
primary-threat selector ranked severities alphabetically, so a MEDIUM anomaly
outranked a CRITICAL injection. Neither defect could be observed, because no
production path ran the code.

**Where security events enter, and why here.** ``services/audit/audit.py``'s
``record()`` is the single write path of the unified audit bus (GH#8290): every
``emit``, ``emit_security``, ``emit_compliance``, ``emit_knowledge`` and
``audit_record`` call funnels through it, it is already async, and
``AuditEvent`` carries actor, IP, session, resource, outcome and metadata —
every field :class:`SecurityEvent` reads. #13562 asks to converge on an existing
entry point rather than add a second path, and that is the one that exists.

**The bound, stated rather than implied.** This covers the unified bus, not
every security event in the process. Failed interactive logins still go to the
legacy file-backed ``security_layer.audit_log`` (``auth_middleware`` records
them with ``action="login_attempt"``, ``outcome="denied"``), which GH#8290 is
migrating away from and which has not been migrated yet. Until it is, the
``BruteForceAnalyzer`` sees credential-operation failures on this bus — JWT
mints, API-key creation, user administration — and not password guesses. That
is a real gap in coverage, and naming it is the point: a wiring that quietly
covered less than it appeared to would be worse than none.

**Vocabulary.** The bus and the engine disagree, and the disagreement is
load-bearing rather than cosmetic. The bus says ``action="run_jwt.mint"`` with
``outcome="denied"``; :meth:`SecurityEvent.is_authentication_failure` requires
``action == "authentication"`` and ``outcome == "failure"`` exactly. Without
:func:`engine_action` and :func:`engine_outcome` the brute-force and
malicious-file analyzers would receive events forever and fire on none of them —
a wiring that passes a grep and detects nothing.

**Response actions.** ``analyze_event`` can reach ``_execute_response_actions``.
As shipped, every handler there logs and does nothing else, and
``auto_block_critical`` defaults to ``False``. This module does not authorise
automated response; it makes detection observable. Anything that later gives
those handlers teeth is a separate decision with a human in it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Bus action prefixes that are credential operations, mapped onto the engine's
# one authentication token. Derived from `services/audit/audit_log.AuditAction`
# and read as families rather than as the exact members, so a new
# `run_jwt.rotate` is covered the day it is added.
AUTHENTICATION_PREFIXES = ("auth.", "login", "api_key.", "run_jwt.", "device_jwt.", "user.")

# Bus action -> the engine's FILE_OPERATION_ACTIONS. The engine matches these by
# exact string, so a near-miss reads as "no file operation ever happened".
FILE_ACTION_BY_SUFFIX: Dict[str, str] = {
    "upload": "file_upload",
    "create": "file_write",
    "write": "file_write",
    "modify": "file_write",
    "delete": "file_delete",
    "remove": "file_delete",
    "download": "file_read",
    "read": "file_read",
    "view": "file_read",
}

# Everything the engine should still see, behaviourally, without pretending to
# be one of the specialised shapes above.
DEFAULT_ENGINE_ACTION = "api_request"

# The bus writes `outcome` free-form; `success` is its documented default and
# every other value its producers use means the operation did not happen.
SUCCESS_OUTCOME = "success"
FAILURE_OUTCOME = "failure"

_engine: Any = None
_engine_lock: Optional[asyncio.Lock] = None
_engine_unavailable: str = ""


def engine_action(audit_action: str) -> str:
    """Translate a bus action into the vocabulary the analyzers match on.

    Exact-string matching is the whole hazard: ``is_file_operation`` tests
    membership of ``FILE_OPERATION_ACTIONS``, so ``"file.upload"`` and
    ``"file_upload"`` are not near-misses, they are a silent zero.
    """
    action = (audit_action or "").strip().lower()
    if not action:
        return DEFAULT_ENGINE_ACTION
    if any(action.startswith(prefix) for prefix in AUTHENTICATION_PREFIXES):
        return "authentication"
    if action.startswith("file."):
        return FILE_ACTION_BY_SUFFIX.get(action.split(".", 1)[1], "file_read")
    return DEFAULT_ENGINE_ACTION


def engine_outcome(audit_outcome: str) -> str:
    """``success`` stays ``success``; every other value is a failure.

    Deliberately a denylist of one rather than an allowlist of the outcomes
    seen today. ``denied``, ``failed`` and ``error`` are all current producers,
    and a value nobody has written yet must read as a failure rather than fall
    through to "fine" — an unrecognised outcome scoring as success is how a
    detector reports clean over the thing it was built for.
    """
    return SUCCESS_OUTCOME if (audit_outcome or "").strip().lower() == SUCCESS_OUTCOME else FAILURE_OUTCOME


def audit_event_to_engine_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build the dict :meth:`ThreatDetectionEngine.analyze_event` consumes.

    *payload* is ``AuditEvent.to_dict()``. Taking the dict rather than the
    dataclass keeps this module importable from the audit bus without a cycle.
    """
    resource_type = payload.get("resource_type") or ""
    resource_id = payload.get("resource_id") or ""
    resource = ":".join(part for part in (resource_type, resource_id) if part)
    occurred_at = payload.get("occurred_at")
    timestamp = (
        datetime.fromtimestamp(float(occurred_at), tz=timezone.utc) if occurred_at else datetime.now(timezone.utc)
    )

    return {
        "user_id": payload.get("actor_id") or "unknown",
        "source_ip": payload.get("ip_address") or "unknown",
        "action": engine_action(str(payload.get("action") or "")),
        "outcome": engine_outcome(str(payload.get("outcome") or "")),
        "resource": resource,
        "timestamp": timestamp.isoformat(),
        "session_id": payload.get("session_id"),
        "details": dict(payload.get("metadata") or {}),
        # Kept so a detection can be traced back to the audit row it came from.
        "audit_category": payload.get("category"),
        "audit_action": payload.get("action"),
        "audit_event_id": payload.get("id"),
    }


async def get_threat_detection_engine() -> Any:
    """The process-wide engine, constructed once, or ``None`` with a reason.

    Construction is deferred to the first event rather than done at import for
    three measured reasons: the engine imports scikit-learn at module scope,
    its ``__init__`` reads and creates a profile store on disk, and it starts
    three perpetual background tasks that need a running loop. None of that
    belongs in an import of the audit bus.

    ``None`` is returned — never raised — when the engine cannot be built, and
    the reason is logged once rather than per event. A detector that cannot run
    must not take the audit write path down with it.
    """
    global _engine, _engine_lock, _engine_unavailable
    if _engine is not None:
        return _engine
    if _engine_unavailable:
        return None
    if _engine_lock is None:
        _engine_lock = asyncio.Lock()
    async with _engine_lock:
        if _engine is not None:
            return _engine
        if _engine_unavailable:
            return None
        try:
            from security.enterprise.threat_detection.engine import ThreatDetectionEngine

            _engine = ThreatDetectionEngine()
        except Exception as exc:  # noqa: BLE001 — recorded below, never discarded
            _engine_unavailable = type(exc).__name__
            logger.error(
                "Threat detection engine unavailable (%s); audit events will not be analysed (#13562)",
                _engine_unavailable,
                exc_info=True,
            )
            return None
    return _engine


async def analyze_audit_event(payload: Dict[str, Any]) -> Any:
    """Analyse one audit row; return the ``ThreatEvent`` found, or ``None``.

    Called from the unified bus's write path. Every failure is logged and
    swallowed *at this boundary on purpose*: an audit record must be persisted
    whether or not the detector can run, and the alternative — a detector fault
    suppressing the audit trail — is strictly worse than a missed detection.
    """
    engine = await get_threat_detection_engine()
    if engine is None:
        return None
    try:
        threat = await engine.analyze_event(audit_event_to_engine_event(payload))
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.error("Threat analysis failed for audit event: %s", type(exc).__name__, exc_info=True)
        return None
    if threat is not None:
        logger.warning(
            "Threat detected on audit event %s: %s (%s, confidence %.2f)",
            payload.get("id"),
            threat.threat_category.value,
            threat.threat_level.value,
            threat.confidence_score,
        )
    return threat


def _reset_engine_for_testing() -> None:
    """Drop the cached engine so a test can install its own."""
    global _engine, _engine_lock, _engine_unavailable
    _engine, _engine_lock, _engine_unavailable = None, None, ""
