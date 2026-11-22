# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Activity storage for chat sessions (split out of ``api.chat_sessions`` in #18825)."""

from typing import Dict, List

from fastapi import HTTPException

from api.schemas_chat import ActivityCreate
from autobot_memory_graph import AutoBotMemoryGraph
from autobot_memory_graph.owner_scope import OwnerScope, OwnerScopeRequired
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def activity_principal_id(ownership: Dict) -> str:
    """Id of the authenticated principal behind a validated session request (#18825).

    The activity body carries its own ``user_id``; trusting it let any caller attribute
    activity (and graph ownership) to someone else, so only ``ownership["user_data"]`` counts.
    """
    try:
        return OwnerScope.from_auth_user((ownership or {}).get("user_data")).user_id
    except OwnerScopeRequired:
        raise HTTPException(status_code=403, detail="Authenticated user required")


def activity_principal(ownership: Dict) -> tuple[str, str | None]:
    """``(user_id, org_id)`` of the authenticated principal; the org is its JWT/TenantContext org, or None (#18825)."""
    return activity_principal_id(ownership), ((ownership or {}).get("user_data") or {}).get("org_id") or None


async def _store_single_activity(
    memory_graph: AutoBotMemoryGraph,
    session_id: str,
    activity: ActivityCreate,
    user_id: str,
    org_id: str | None = None,
) -> Dict:
    """
    Store a single activity in memory graph.

    Issue #665: Extracted helper for activity storage.
    #18825: ``user_id`` is the authenticated principal; ``activity.user_id`` (request body) is
    client-supplied and never used for attribution or ownership.

    Returns:
        Entity creation result dict
    """
    return await memory_graph.create_activity_entity(
        activity_type=f"{activity.type}_activity",
        session_id=session_id,
        user_id=user_id,
        org_id=org_id,
        content=activity.content,
        secrets_used=activity.secrets_used,
        metadata={
            "frontend_id": activity.activity_id,
            "frontend_timestamp": activity.timestamp,
            **(activity.metadata or {}),
        },
    )


async def _try_store_activity(
    memory_graph: AutoBotMemoryGraph,
    session_id: str,
    activity: ActivityCreate,
    request_id: str,
    user_id: str,
    org_id: str | None,
) -> bool:
    """Store one activity; a failure is logged and counted by the caller, never raised."""
    try:
        await _store_single_activity(memory_graph, session_id, activity, user_id, org_id)
        return True
    except Exception as activity_error:
        logger.warning("[%s] Failed to store activity %s: %s", request_id, activity.activity_id, activity_error)
        return False


async def _process_activity_batch(
    memory_graph: AutoBotMemoryGraph,
    session_id: str,
    activities: List[ActivityCreate],
    request_id: str,
    user_id: str,
    org_id: str | None = None,
) -> Dict:
    """
    Process a batch of activities and store them in memory graph.

    Issue #620.

    Args:
        memory_graph: Memory graph instance for storage
        session_id: Session ID for the activities
        activities: List of activities to process
        request_id: Request ID for logging
        user_id: Authenticated principal id used for every activity (#18825)

    Returns:
        Dict with stored_count, failed_count, and stored_ids
    """
    stored_ids: List[str] = []
    for activity in activities:
        if await _try_store_activity(memory_graph, session_id, activity, request_id, user_id, org_id):
            stored_ids.append(activity.activity_id)

    return {
        "stored_count": len(stored_ids),
        "failed_count": len(activities) - len(stored_ids),
        "stored_ids": stored_ids,
    }
