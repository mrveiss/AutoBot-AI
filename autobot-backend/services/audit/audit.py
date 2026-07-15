# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical audit service — single taxonomy for all audit categories (#6475).

Three prior log modules (services/event_log.py, services/audit/audit_log.py,
knowledge/audit_log.py) each stored overlapping data in separate Redis keys.
This module provides one canonical surface; the three originals forward to it
via shim helpers defined at the bottom of each legacy file.

Migration plan:
  Phase 1 (done):   audit.py landed; legacy files have shim wrappers.
  Phase 2 (GH#8290): Callers migrated area-by-area to import from here.
                     Backwards-compatible bridge symbols are exported so callers
                     only need to update their import line, not their call sites.
  Phase 3 (follow-up): Remove the three legacy files once all callers migrated.
"""

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.fire_and_forget import run_redis_write
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Retention constants (per category)
# ---------------------------------------------------------------------------

_SECURITY_TTL = 90 * 24 * 3600
_COMPLIANCE_TTL = 90 * 24 * 3600
_KNOWLEDGE_TTL = 365 * 24 * 3600
_GOVERNANCE_TTL = 365 * 24 * 3600

_CATEGORY_TTL: Dict[str, int] = {
    "security": _SECURITY_TTL,
    "compliance": _COMPLIANCE_TTL,
    "knowledge": _KNOWLEDGE_TTL,
    "governance": _GOVERNANCE_TTL,
}

# ---------------------------------------------------------------------------
# Public taxonomy
# ---------------------------------------------------------------------------

UNIFIED_KEY = "audit:unified"


class AuditCategory(str, Enum):
    SECURITY = "security"  # session, api_key, user, config (was audit_log)
    COMPLIANCE = "compliance"  # login/logout, agent invoke (was event_log)
    KNOWLEDGE = "knowledge"  # view, search, share (was knowledge/audit_log)
    GOVERNANCE = "governance"  # skill approval, budget breach, agent pause


@dataclass
class AuditEvent:
    category: AuditCategory
    action: str
    actor_id: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resource_type: str | None = None
    resource_id: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    occurred_at: float = field(default_factory=time.time)
    ip_address: str | None = None
    session_id: str | None = None
    outcome: str = "success"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        return d


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------


async def record(event: AuditEvent) -> None:
    """Persist a single audit event to the unified Redis sorted set."""
    redis = await get_async_redis_client(database="main")
    if redis is None:
        logger.debug(
            "audit: Redis unavailable, event dropped: %s/%s",
            event.category,
            event.action,
        )
        return
    raw = json.dumps(event.to_dict(), ensure_ascii=False)
    ttl = _CATEGORY_TTL.get(event.category.value, _COMPLIANCE_TTL)
    async with redis.pipeline() as pipe:
        await pipe.zadd(UNIFIED_KEY, {raw: event.occurred_at})
        # UNIFIED_KEY spans all categories with different TTLs — never set expire
        # on it (#8303). Per-category keys each carry their own TTL.
        cat_key = f"audit:category:{event.category.value}"
        await pipe.zadd(cat_key, {raw: event.occurred_at})
        await pipe.expire(cat_key, ttl)
        await pipe.execute()


def emit(event: AuditEvent) -> None:
    """Fire-and-forget wrapper around :func:`record`.

    Safe to call from any sync or async context.
    """
    run_redis_write(record(event), label="audit")


# Capture the real emit before the Phase-2 bridge shadows the name below.
# emit_compliance / emit_security must call _emit_real to avoid a recursion
# cycle: bridge-emit → emit_compliance → emit → bridge-emit → ...
_emit_real = emit


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------


async def query(
    category: AuditCategory | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    limit: int = 100,
    offset: int = 0,
    max_scan: int = 10_000,
) -> List[Dict[str, Any]]:
    """Query audit events.  Filters are applied in-memory after a Redis scan."""
    redis = await get_async_redis_client(database="main")
    if redis is None:
        return []
    key = f"audit:category:{category.value}" if category else UNIFIED_KEY
    min_score: Any = from_ts if from_ts is not None else 0
    max_score: Any = to_ts if to_ts is not None else "+inf"
    # #8302: cap Redis scan before Python-side filtering to prevent OOM
    raws = await redis.zrangebyscore(key, min_score, max_score, start=0, num=max_scan)
    results: List[Dict[str, Any]] = []
    for raw in raws:
        try:
            ev = json.loads(raw)
        except Exception:
            continue
        if actor_id and ev.get("actor_id") != actor_id:
            continue
        if action and ev.get("action") != action:
            continue
        results.append(ev)
    results.sort(key=lambda e: e.get("occurred_at", 0), reverse=True)
    return results[offset : offset + limit]


# ---------------------------------------------------------------------------
# Convenience helpers (match legacy call-sites during migration)
# ---------------------------------------------------------------------------


def emit_compliance(
    action: str,
    actor_id: str | None,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Drop-in shim for services/event_log.emit()."""
    _emit_real(
        AuditEvent(
            category=AuditCategory.COMPLIANCE,
            action=action,
            actor_id=actor_id or "system",
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
            ip_address=ip_address,
        )
    )


def emit_security(
    action: str,
    actor_id: str,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Dict[str, Any] | None = None,
    ip_address: str | None = None,
    session_id: str | None = None,
    outcome: str = "success",
) -> None:
    """Drop-in shim for services/audit/audit_log.audit_record()."""
    _emit_real(
        AuditEvent(
            category=AuditCategory.SECURITY,
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
            ip_address=ip_address,
            session_id=session_id,
            outcome=outcome,
        )
    )


async def emit_knowledge(
    action: str,
    actor_id: str,
    *,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Async shim for knowledge/audit_log.KnowledgeAuditLog.log_event()."""
    await record(
        AuditEvent(
            category=AuditCategory.KNOWLEDGE,
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
            ip_address=ip_address,
        )
    )


# ---------------------------------------------------------------------------
# Phase 2 (GH#8290): Backwards-compatible bridge symbols for migrated callers
#
# Callers of the three legacy modules update only their import line.
# These bridges accept the EXACT same signatures as the legacy functions so no
# call-site edits are needed.
# ---------------------------------------------------------------------------

# --- Re-export legacy enum types so import-only callers need no changes ----

import warnings as _warnings  # noqa: E402

with _warnings.catch_warnings():
    # Suppress the DeprecationWarnings these modules emit at import time — they
    # are designed to warn external callers, not the canonical migration target.
    _warnings.simplefilter("ignore", DeprecationWarning)
    from knowledge.audit_log import (
        AuditEventType,
    )
    from knowledge.audit_log import KnowledgeAuditLog as _KnowledgeAuditLog  # noqa: E402
    from services.audit.audit_log import AuditAction  # noqa: E402
    from services.event_log import EventType  # noqa: E402


# --- Drop-in replacements for services/event_log.emit() and query_events() -


def emit(  # type: ignore[misc]  — intentional override of local name  # noqa: F811
    event_type: "EventType",
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Bridge: drop-in for ``services.event_log.emit()`` (GH#8290 Phase 2)."""
    emit_compliance(
        action=event_type.value if hasattr(event_type, "value") else str(event_type),
        actor_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
        ip_address=ip_address,
    )


async def query_events(
    user_id: str | None = None,
    event_type: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Bridge: drop-in for ``services.event_log.query_events()`` (GH#8290 Phase 2)."""
    return await query(
        category=AuditCategory.COMPLIANCE,
        actor_id=user_id,
        action=event_type,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
    )


# --- Drop-in replacement for services/audit/audit_log.audit_record() -------


def audit_record(
    user_id: str,
    action: "AuditAction",
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Dict[str, Any] | None = None,
    ip_address: str | None = None,
    session_id: str | None = None,
    outcome: str = "success",
) -> None:
    """Bridge: drop-in for ``services.audit.audit_log.audit_record()`` (GH#8290 Phase 2)."""
    emit_security(
        action=action.value if hasattr(action, "value") else str(action),
        actor_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
        ip_address=ip_address,
        session_id=session_id,
        outcome=outcome,
    )


# --- Drop-in compatibility class for knowledge/audit_log.KnowledgeAuditLog --


class KnowledgeAuditLog(_KnowledgeAuditLog):
    """Bridge: subclass of ``KnowledgeAuditLog`` that delegates to audit.

    Callers that instantiate ``KnowledgeAuditLog(redis_client)`` and call
    ``.log_event()`` continue to work unchanged (GH#8290 Phase 2).
    The ``log_event`` override also writes to the unified Redis key so all
    knowledge events appear in the unified audit stream.
    """

    async def log_event(
        self,
        event_type: "AuditEventType",
        user_id: str,
        fact_id: str | None = None,
        organization_id: str | None = None,
        details: Dict | None = None,
        ip_address: str | None = None,
    ) -> str:
        event_id = await super().log_event(
            event_type=event_type,
            user_id=user_id,
            fact_id=fact_id,
            organization_id=organization_id,
            details=details,
            ip_address=ip_address,
        )
        # Also write to unified stream
        await emit_knowledge(
            action=(event_type.value if hasattr(event_type, "value") else str(event_type)),
            actor_id=user_id,
            resource_type="fact" if fact_id else "knowledge",
            resource_id=fact_id or organization_id,
            metadata=details or {},
            ip_address=ip_address,
        )
        return event_id
