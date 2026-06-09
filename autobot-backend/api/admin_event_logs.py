# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: queryable compliance event log (Issue #4461).

Endpoint:
    GET /api/admin/event-logs

Filters:
    user_id      – filter by user
    event_type   – filter by event type (e.g. user.login)
    from_ts      – Unix timestamp lower bound (inclusive)
    to_ts        – Unix timestamp upper bound (inclusive)
    limit        – max results per page (1–1000, default 100)
    offset       – pagination offset (default 0)

Access: admin role required.
"""

from fastapi import APIRouter, Depends, Query, Request

from auth_middleware import get_auth_middleware
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.audit.unified_audit import EventType, query_events  # GH#8290 Phase 2
from utils.catalog_http_exceptions import raise_auth_error

router = APIRouter(prefix="/admin", tags=["admin", "compliance"])
logger = get_logger(__name__)


def _require_admin(request: Request) -> bool:
    """Dependency: reject non-admin callers."""
    user_data = get_auth_middleware().get_user_from_request(request)
    if not user_data:
        raise_auth_error("AUTH_0002", "Authentication required")
    if user_data.get("role") != "admin":
        raise_auth_error("AUTH_0003", "Admin permission required")
    return True


@router.get("/event-logs")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_event_logs",
    error_code_prefix="EVT",
)
async def list_event_logs(
    request: Request,
    user_id: str | None = Query(None, description="Filter by user ID"),
    event_type: str | None = Query(None, description="Filter by event type"),
    from_ts: float | None = Query(None, description="Unix timestamp lower bound"),
    to_ts: float | None = Query(None, description="Unix timestamp upper bound"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    _admin: bool = Depends(_require_admin),
) -> dict:
    """Return compliance events with optional filters.

    Results are ordered newest-first.  All parameters are optional.

    **Event types:** user.login · user.logout · user.created ·
    user.role_changed · document.uploaded · document.deleted ·
    agent.invoked · config.changed · api_key.created · api_key.deleted
    """
    events = await query_events(
        user_id=user_id,
        event_type=event_type,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
    )
    return {
        "events": events,
        "count": len(events),
        "limit": limit,
        "offset": offset,
        "available_event_types": [e.value for e in EventType],
    }
