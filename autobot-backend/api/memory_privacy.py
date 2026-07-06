# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Memory Privacy API — Issue #10554.

Per-user memory transparency, edit/forget, and export endpoints.

Endpoints
---------
GET  /memory/privacy/list              — list all memories stored for the caller
DELETE /memory/privacy/{store}/{memory_id}  — forget one memory item from its store
DELETE /memory/privacy/forget-everywhere/{memory_id}  — cascade delete across all stores
PUT  /memory/privacy/{store}/{memory_id}   — amend a verbatim/working-memory item's content
GET  /memory/privacy/export            — download the caller's full memory footprint (JSON)

Tenant isolation
----------------
Every endpoint derives the target user_id from `get_current_user()`.  An admin
may pass ?target_user_id= to inspect/manage another user's memories.  Without
that param, users can only see and modify their own memories — cross-user access
is enforced server-side and any mis-routed request returns 403.

Audit
-----
Every mutating call (forget, amend) is logged via the `audit_log` helper so
access is traceable for GDPR accountability (who deleted what, when).
"""

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.audit_logger import audit_log

logger = get_logger(__name__)

router = APIRouter(prefix="/memory/privacy", tags=["memory-privacy"])

_VALID_STORES = frozenset({"verbatim", "trajectory", "working_memory", "graph", "retrieval_learner"})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AmendRequest(BaseModel):
    """Body for PUT /memory/privacy/{store}/{memory_id}."""

    content: str = Field(..., min_length=1, max_length=8192, description="Replacement content text")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_target_user(
    current_user: Dict[str, Any],
    target_user_id: Optional[str],
    request: Request,
) -> str:
    """Return the effective user_id for the operation.

    Admins may supply ?target_user_id=; non-admins always get their own id.
    Raises 403 if a non-admin supplies a different target_user_id.
    """
    caller_id = current_user.get("user_id") or current_user.get("username", "")
    if not target_user_id or target_user_id == caller_id:
        return caller_id

    # Only admins may operate on another user's memories.
    try:
        check_admin_permission(request)
    except HTTPException:
        raise HTTPException(
            status_code=403,
            detail="Only admins may access another user's memory records.",
        )
    return target_user_id


def _validate_store(store: str) -> None:
    if store not in _VALID_STORES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown store {store!r}. Valid: {sorted(_VALID_STORES)}",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/list")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_user_memories",
    error_code_prefix="MEMORY_PRIVACY",
)
async def list_memories(
    request: Request,
    target_user_id: Optional[str] = Query(None, description="Admin only: inspect another user"),
    current_user: Dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """List all memory items stored for the authenticated user.

    Returns items from every store (verbatim, trajectory, working_memory,
    graph, retrieval_learner) with provenance and timestamps.
    """
    from memory.transparency import list_user_memories

    user_id = _resolve_target_user(current_user, target_user_id, request)
    memories = await list_user_memories(user_id)

    await audit_log(
        "memory.privacy.list",
        result="success",
        user_id=current_user.get("user_id") or current_user.get("username"),
        resource=f"user:{user_id}",
        details={"item_count": len(memories)},
    )
    return {
        "user_id": user_id,
        "total": len(memories),
        "memories": memories,
    }


@router.delete("/forget-everywhere/{memory_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="forget_memory_everywhere",
    error_code_prefix="MEMORY_PRIVACY",
)
async def forget_everywhere(
    memory_id: str,
    request: Request,
    target_user_id: Optional[str] = Query(None),
    current_user: Dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Cascade-delete a memory item from every store.

    Returns a per-store map of ``{store: true/false}`` indicating whether the
    item existed in that store.  A True value means it was deleted from there.
    """
    from memory.transparency import forget_everywhere as _forget_everywhere

    user_id = _resolve_target_user(current_user, target_user_id, request)
    results = await _forget_everywhere(user_id, memory_id)
    deleted_from = [s for s, ok in results.items() if ok]

    await audit_log(
        "memory.privacy.forget_everywhere",
        result="success",
        user_id=current_user.get("user_id") or current_user.get("username"),
        resource=f"memory:{memory_id}",
        details={"target_user": user_id, "deleted_from": deleted_from},
    )
    return {
        "memory_id": memory_id,
        "user_id": user_id,
        "results": results,
        "deleted_from": deleted_from,
    }


@router.delete("/{store}/{memory_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="forget_memory_from_store",
    error_code_prefix="MEMORY_PRIVACY",
)
async def forget_from_store(
    store: str,
    memory_id: str,
    request: Request,
    target_user_id: Optional[str] = Query(None),
    current_user: Dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Forget a specific memory item from a named store.

    Use the ``store`` and ``memory_id`` values returned by GET /list.
    Returns 404 when the item is not found in the named store.
    """
    from memory.transparency import forget_memory

    _validate_store(store)
    user_id = _resolve_target_user(current_user, target_user_id, request)
    deleted = await forget_memory(user_id, memory_id, store)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Memory item {memory_id!r} not found in store {store!r}",
        )

    await audit_log(
        "memory.privacy.forget",
        result="success",
        user_id=current_user.get("user_id") or current_user.get("username"),
        resource=f"memory:{store}:{memory_id}",
        details={"target_user": user_id, "store": store},
    )
    return {
        "memory_id": memory_id,
        "store": store,
        "user_id": user_id,
        "deleted": True,
    }


@router.put("/{store}/{memory_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="amend_memory",
    error_code_prefix="MEMORY_PRIVACY",
)
async def amend_memory(
    store: str,
    memory_id: str,
    body: AmendRequest,
    request: Request,
    target_user_id: Optional[str] = Query(None),
    current_user: Dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Amend (correct) a memory item's content.

    Only ``verbatim`` and ``working_memory`` stores support amendment.
    For graph entities, delete and recreate via the knowledge graph API.
    """
    _validate_store(store)
    user_id = _resolve_target_user(current_user, target_user_id, request)

    if store == "verbatim":
        updated = await _amend_verbatim(user_id, memory_id, body.content)
    elif store == "working_memory":
        updated = await _amend_working_memory(user_id, memory_id, body.content)
    else:
        raise HTTPException(
            status_code=422,
            detail=f"Amendment not supported for store {store!r}. Use forget+recreate.",
        )

    if not updated:
        raise HTTPException(status_code=404, detail=f"Memory item {memory_id!r} not found.")

    await audit_log(
        "memory.privacy.amend",
        result="success",
        user_id=current_user.get("user_id") or current_user.get("username"),
        resource=f"memory:{store}:{memory_id}",
        details={"target_user": user_id, "store": store},
    )
    return {"memory_id": memory_id, "store": store, "user_id": user_id, "amended": True}


@router.get("/export")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_user_memory",
    error_code_prefix="MEMORY_PRIVACY",
)
async def export_memory(
    request: Request,
    target_user_id: Optional[str] = Query(None),
    current_user: Dict = Depends(get_current_user),
) -> Response:
    """Download the caller's complete memory footprint as a JSON file.

    Reuses the LLC full-state-snapshot export pattern: returns
    Content-Disposition: attachment so browsers trigger a download.
    """
    from memory.transparency import export_user_memory

    user_id = _resolve_target_user(current_user, target_user_id, request)
    payload = await export_user_memory(user_id)

    await audit_log(
        "memory.privacy.export",
        result="success",
        user_id=current_user.get("user_id") or current_user.get("username"),
        resource=f"user:{user_id}",
        details={"item_count": payload.get("total_items", 0)},
    )
    filename = f"memory_export_{user_id}.json"
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Amendment helpers (inline — short, each ≤30 lines)
# ---------------------------------------------------------------------------


async def _amend_verbatim(user_id: str, chunk_id: str, new_content: str) -> bool:
    """Replace a verbatim chunk's text (delete + re-add with same metadata)."""
    from memory.verbatim_store import get_verbatim_store

    store = await get_verbatim_store()
    collection = await store._get_collection()
    existing = await collection.get(ids=[chunk_id], include=["documents", "metadatas"])
    if not existing.get("ids"):
        return False
    meta = (existing.get("metadatas") or [{}])[0]
    if meta.get("user_id") != user_id:
        logger.warning(
            "_amend_verbatim: tenant mismatch chunk=%s owner=%s caller=%s", chunk_id, meta.get("user_id"), user_id
        )
        return False
    await collection.delete(ids=[chunk_id])
    await collection.add(ids=[chunk_id], documents=[new_content], metadatas=[meta])
    logger.info("_amend_verbatim: amended chunk %s", chunk_id)
    return True


async def _amend_working_memory(user_id: str, redis_key: str, new_content: str) -> bool:
    """Replace a working-memory entry's content field in-place."""
    from autobot_shared.redis_client import get_redis_client

    redis = await get_redis_client(async_client=True, database="knowledge")
    raw = await redis.get(redis_key)
    if not raw:
        return False
    value = json.loads(raw) if isinstance(raw, (str, bytes)) else {}
    if isinstance(value, dict) and value.get("user_id") != user_id:
        logger.warning("_amend_working_memory: tenant mismatch key=%s caller=%s", redis_key, user_id)
        return False
    value["content"] = new_content
    ttl = await redis.ttl(redis_key)
    if ttl > 0:
        await redis.setex(redis_key, ttl, json.dumps(value, ensure_ascii=False))
    else:
        await redis.set(redis_key, json.dumps(value, ensure_ascii=False))
    logger.info("_amend_working_memory: amended key %s", redis_key)
    return True
