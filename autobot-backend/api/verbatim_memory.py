# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Verbatim Memory API

Issue #5070: REST surface for the verbatim-memory lane.

Endpoints:
    GET  /verbatim-memory/search?q=<query>&session_id=<optional>&limit=<int>
    DELETE /verbatim-memory/session/{session_id}
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, Request

from auth_middleware import get_auth_middleware
from autobot_shared.error_boundaries import with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["memory"])


def _require_user(request: Request) -> Dict[str, Any]:
    """Raise 401 if the request carries no authenticated user."""
    user = get_auth_middleware().get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------


@router.get("/verbatim-memory/search")
@with_error_handling
async def verbatim_search(
    request: Request,
    q: str = Query(..., description="Search query"),
    session_id: str | None = Query(None, description="Restrict results to this session"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
) -> Dict[str, Any]:
    """Search verbatim conversation chunks.

    Returns chunks ranked by cosine similarity.  When ``session_id`` is
    provided, only chunks from that session are considered.

    Args:
        q: Free-text query.
        session_id: Optional session scope.
        limit: Maximum chunks to return (1–100, default 10).

    Returns:
        JSON object with ``results`` list, each item having
        ``id``, ``text``, ``score``, and ``metadata`` keys.
    """
    _require_user(request)

    from memory.verbatim_store import get_verbatim_store

    store = await get_verbatim_store()
    results: List[Dict[str, Any]] = await store.search(
        query=q,
        session_filter=session_id,
        limit=limit,
    )
    return {"query": q, "session_id": session_id, "results": results}


# ---------------------------------------------------------------------------
# Delete (opt-out / retention) endpoint
# ---------------------------------------------------------------------------


@router.delete("/verbatim-memory/session/{session_id}")
@with_error_handling
async def delete_session_verbatim(
    session_id: str,
    request: Request,
) -> Dict[str, Any]:
    """Delete all verbatim chunks for a session.

    Used for user opt-out and retention enforcement.  The caller must be
    authenticated; in production the middleware additionally enforces that
    users can only delete their own sessions.

    Args:
        session_id: Session whose verbatim chunks to remove.

    Returns:
        JSON object with ``session_id`` and ``deleted_count``.
    """
    _require_user(request)

    from memory.verbatim_store import get_verbatim_store

    store = await get_verbatim_store()
    deleted = await store.delete_session(session_id)
    logger.info("verbatim_memory: deleted %d chunks for session %s", deleted, session_id)
    return {"session_id": session_id, "deleted_count": deleted}
