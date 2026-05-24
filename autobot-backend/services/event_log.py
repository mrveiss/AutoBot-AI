# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Append-only compliance event log (Issue #4461).

Stores structured compliance events in a Redis sorted set keyed by Unix
timestamp.  All writes are fire-and-forget — callers are never blocked.

.. deprecated::
    Use ``services.audit.unified_audit`` directly (GH#8290 Phase 2).
    This module will be removed in Phase 3 once all callers are migrated.
"""

import warnings

warnings.warn(
    "services.event_log is deprecated (GH#8290). " "Import from services.audit.unified_audit instead.",
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

EVENT_LOG_KEY = "autobot:event_log"
EVENT_LOG_TTL_SECONDS = 90 * 24 * 3600  # 90-day default retention


class EventType(str, Enum):
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_CREATED = "user.created"
    USER_ROLE_CHANGED = "user.role_changed"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_DELETED = "document.deleted"
    AGENT_INVOKED = "agent.invoked"
    CONFIG_CHANGED = "config.changed"
    API_KEY_CREATED = "api_key.created"
    API_KEY_DELETED = "api_key.deleted"


async def _write_event(
    event_type: EventType,
    user_id: str | None,
    resource_type: str | None,
    resource_id: str | None,
    metadata: Dict[str, Any],
    ip_address: str | None,
) -> None:
    """Write a single compliance event to the Redis sorted set."""
    redis = await get_async_redis_client(database="main")
    if redis is None:
        logger.debug("event_log: Redis unavailable, event dropped: %s", event_type)
        return
    now = time.time()
    entry = {
        "id": str(uuid.uuid4()),
        "event_type": event_type.value,
        "user_id": user_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "metadata": metadata,
        "ip_address": ip_address,
        "created_at": now,
    }
    raw = json.dumps(entry, ensure_ascii=False)
    await redis.zadd(EVENT_LOG_KEY, {raw: now})
    await redis.expire(EVENT_LOG_KEY, EVENT_LOG_TTL_SECONDS)


def emit(
    event_type: EventType,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: Dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Fire-and-forget compliance event emission.

    Safe to call from any async context.  Errors are swallowed at DEBUG level
    so compliance writes never propagate to the caller.
    """
    run_redis_write(
        _write_event(
            event_type,
            user_id,
            resource_type,
            resource_id,
            metadata or {},
            ip_address,
        ),
        label="event_log",
    )


async def query_events(
    user_id: str | None = None,
    event_type: str | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Query compliance events from the Redis sorted set.

    Filters are applied in-memory after the timestamp range scan.
    Results are returned newest-first.
    """
    redis = await get_async_redis_client(database="main")
    if redis is None:
        return []
    min_score: Any = from_ts if from_ts is not None else 0
    max_score: Any = to_ts if to_ts is not None else "+inf"
    raws = await redis.zrangebyscore(EVENT_LOG_KEY, min_score, max_score)
    events: List[Dict[str, Any]] = []
    for raw in raws:
        try:
            e = json.loads(raw)
        except Exception:
            continue
        if user_id and e.get("user_id") != user_id:
            continue
        if event_type and e.get("event_type") != event_type:
            continue
        events.append(e)
    events.sort(key=lambda e: e.get("created_at", 0), reverse=True)
    return events[offset : offset + limit]
