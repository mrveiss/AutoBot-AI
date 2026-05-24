# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Structured, queryable AuditLog service (Issue #4456).

Records who did what and when for security/compliance purposes.
Each record is stored in a Redis sorted set keyed by user ID, with the
Unix timestamp as score.  A global index key is also maintained so that
cross-user queries are possible without scanning every user's key.

Key design choices
------------------
- Per-user key ``audit_log:{user_id}`` enables O(log n) user-scoped queries.
- Global index ``audit_log:global`` enables admin-level cross-user queries.
- 90-day TTL is refreshed on every write to each key.
- ``audit_record()`` is a sync fire-and-forget wrapper (never blocks callers).
- ``record_event()`` is the async implementation for direct await use.
- ``query_audit_log()`` filters in-memory after a Redis range scan — acceptable
  given the expected event volume and the 90-day retention window.

.. deprecated::
    Use ``services.audit.unified_audit`` directly (GH#8290 Phase 2).
    This module will be removed in Phase 3 once all callers are migrated.
"""

import warnings

warnings.warn(
    "services.audit.audit_log is deprecated (GH#8290). " "Import from services.audit.unified_audit instead.",
    DeprecationWarning,
    stacklevel=2,
)

import json
import time
import uuid
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.fire_and_forget import run_redis_write
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

AUDIT_LOG_TTL_SECONDS = 90 * 24 * 3600  # 90-day retention
_GLOBAL_KEY = "audit_log:global"


class AuditAction(str, Enum):
    """Actions recorded by the audit log."""

    SESSION_CREATE = "session.create"
    SESSION_DELETE = "session.delete"
    SESSION_EXPORT = "session.export"
    KNOWLEDGE_ADD = "knowledge.add"
    KNOWLEDGE_REMOVE = "knowledge.remove"
    API_KEY_CREATE = "api_key.create"
    API_KEY_REVOKE = "api_key.revoke"
    USER_CREATE = "user.create"
    USER_DELETE = "user.delete"
    CONFIG_CHANGE = "config.change"
    ADMIN_ACTION = "admin.action"
    RUN_JWT_MINT = "run_jwt.mint"
    RUN_JWT_REVOKE = "run_jwt.revoke"
    RUN_JWT_REFRESH = "run_jwt.refresh"


async def record_event(
    user_id: str,
    action: AuditAction,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Dict[str, Any] | None = None,
    ip_address: str | None = None,
    session_id: str | None = None,
    outcome: str = "success",
) -> None:
    """Write a single audit record to Redis.

    Writes to two sorted sets:
    - ``audit_log:{user_id}`` — per-user index, score = Unix timestamp
    - ``audit_log:global``   — global index, score = Unix timestamp

    Both keys receive a 90-day TTL refresh on every write.

    Args:
        user_id: Identifier of the user who performed the action.
        action: The :class:`AuditAction` that occurred.
        resource_type: Category of the affected resource (e.g. ``"session"``).
        resource_id: Unique ID of the affected resource.
        metadata: Arbitrary extra context; sensitive keys are NOT stored here
                  (callers must sanitize before passing).
        ip_address: Source IP address of the request.
        session_id: Session in which the action occurred.
        outcome: Result of the action — ``"success"``, ``"denied"``,
                 ``"failed"``, or ``"error"``.
    """
    redis = await get_async_redis_client(database="main")
    if redis is None:
        logger.debug(
            "audit_log: Redis unavailable — event dropped: user=%s action=%s",
            user_id,
            action,
        )
        return

    now = time.time()
    entry: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "action": action.value,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "metadata": metadata or {},
        "ip_address": ip_address,
        "session_id": session_id,
        "outcome": outcome,
        "created_at": now,
    }
    raw = json.dumps(entry, ensure_ascii=False)
    user_key = f"audit_log:{user_id}"

    async with redis.pipeline() as pipe:
        await pipe.zadd(user_key, {raw: now})
        await pipe.expire(user_key, AUDIT_LOG_TTL_SECONDS)
        await pipe.zadd(_GLOBAL_KEY, {raw: now})
        await pipe.expire(_GLOBAL_KEY, AUDIT_LOG_TTL_SECONDS)
        await pipe.execute()


def audit_record(
    user_id: str,
    action: AuditAction,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Dict[str, Any] | None = None,
    ip_address: str | None = None,
    session_id: str | None = None,
    outcome: str = "success",
) -> None:
    """Fire-and-forget wrapper around :func:`record_event`.

    Safe to call from any sync or async context.  Errors are swallowed at
    DEBUG level so audit writes never propagate to the caller.

    Args:
        user_id: Identifier of the user who performed the action.
        action: The :class:`AuditAction` that occurred.
        resource_type: Category of the affected resource.
        resource_id: Unique ID of the affected resource.
        metadata: Extra context dict (caller must sanitize sensitive keys).
        ip_address: Source IP address of the request.
        session_id: Session in which the action occurred.
        outcome: Result string — ``"success"``, ``"denied"``, ``"failed"``,
                 or ``"error"``.
    """
    run_redis_write(
        record_event(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
            ip_address=ip_address,
            session_id=session_id,
            outcome=outcome,
        ),
        label="audit_log",
    )


async def query_audit_log(
    user_id: str | None = None,
    action: AuditAction | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Query audit records from Redis.

    Scans either the per-user sorted set (when *user_id* is given) or the
    global index, then applies in-memory filters for *action*, *from_ts*,
    and *to_ts*.  Results are returned newest-first.

    Args:
        user_id: When provided, restricts results to a single user's records.
        action: When provided, only records with this :class:`AuditAction` are
                returned.
        from_ts: Unix timestamp lower bound (inclusive).  Defaults to 0.
        to_ts: Unix timestamp upper bound (inclusive).  Defaults to ``+inf``.
        limit: Maximum number of records to return.
        offset: Number of matching records to skip (pagination).

    Returns:
        List of audit record dicts, sorted newest-first.
    """
    redis = await get_async_redis_client(database="main")
    if redis is None:
        return []

    key = f"audit_log:{user_id}" if user_id else _GLOBAL_KEY
    min_score: Any = from_ts if from_ts is not None else 0
    max_score: Any = to_ts if to_ts is not None else "+inf"

    raws = await redis.zrangebyscore(key, min_score, max_score)
    records: List[Dict[str, Any]] = []
    action_value = action.value if action is not None else None

    for raw in raws:
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        if action_value and rec.get("action") != action_value:
            continue
        records.append(rec)

    records.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return records[offset : offset + limit]
