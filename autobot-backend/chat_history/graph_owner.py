# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Owner scope for a chat session's memory-graph entity (#18825)."""

from typing import Any, Dict, List

from autobot_memory_graph.owner_scope import OwnerScope, OwnerScopeRequired
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def session_owner_scope(metadata: Dict[str, Any] | None) -> OwnerScope:
    """OwnerScope recorded in a session's stored metadata.

    Uses the same identity the session entity is written under (``user_id``, else the
    ``owner`` / ``username`` stamped by ``build_owner_metadata``) plus ``org_id``. A
    session with no recorded owner (CLI, tests) maps to ``OwnerScope.system()``: the
    entity still exists but no user-scoped read can see it -- never ownerless-visible.
    """
    meta = metadata or {}
    user = meta.get("user_id") or meta.get("owner") or meta.get("username")
    if not user:
        return OwnerScope.system()
    try:
        return OwnerScope.for_user(user, meta.get("org_id"))
    except OwnerScopeRequired:
        return OwnerScope.system()


async def create_entity_on_missing(
    memory_graph: Any,
    session_id: str,
    name: str,
    metadata: Dict[str, Any],
    observations: List[str],
    session_metadata: Dict[str, Any] | None,
) -> None:
    """Create the conversation entity for a session that has none, stamped with its owner.

    The create-on-missing path used to drop the owner metadata (#18825).
    """
    entity_metadata = {
        "session_id": session_id,
        "title": name or session_id,
        "status": "active",
        "priority": "medium",
        "topics": metadata["topics"],
        "entity_mentions": metadata["entity_mentions"],
    }
    await memory_graph.create_conversation_entity(
        session_id=session_id,
        metadata=entity_metadata,
        observations=observations,
        owner=session_owner_scope(session_metadata),
    )
    logger.info("Created Memory Graph entity for session: %s", session_id)
