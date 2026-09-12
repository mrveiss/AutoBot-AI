#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat-knowledge context deletion and orphan cleanup (#16490).

Before this module, ``api/chat_knowledge.py`` could create
(``POST /context/create``) and read (``GET /context/{chat_id}``) a
chat-knowledge context, but nothing could delete one -- a context whose chat
never existed, or whose chat was later deleted, stayed forever.

Split out as its own router rather than added to ``api/chat_knowledge.py``
directly: that file sits close enough to
``scripts/check_python_file_size.py``'s MAX_LINES that these three routes
would put it over, the same reason ``api/chat_knowledge_manager.py`` and
``api/chat_knowledge_prompt.py`` were split out of it in the first place
(#15160). ``api/chat_knowledge.py`` mounts this router onto its own via
``router.include_router(...)``, the same composition
``api/chat.py``/``api/chat_sessions.py`` already use, so both still answer
under the one ``/api/chat-knowledge`` prefix.

Routes:
    ``DELETE /context/{chat_id}``  -- owner-or-admin delete of one context,
        together with its file associations (and any file this manager
        itself wrote to disk for them) and its pending-decisions entry.
        Temporary knowledge lives on the context dataclass itself, so it
        goes with it; there is no separate store for it to leave behind.
    ``GET/DELETE /context-orphans`` -- admin-only discovery and cleanup of
        contexts whose ``chat_id`` matches no chat, in the same
        list-then-cleanup, dry-run-by-default shape as
        ``api/knowledge_maintenance.py``'s ``/session-orphans`` endpoints.
        Named with a hyphen rather than nested under ``/context/`` so it can
        never be shadowed by (or shadow) ``/context/{chat_id}`` regardless of
        router registration order.

``api/chat_sessions.py``'s own session-delete cascade
(``api/chat_sessions_delete_cleanup.py``'s ``_cleanup_chat_knowledge_context``)
calls :func:`delete_chat_knowledge_context` directly rather than going back
through HTTP.
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.chat_knowledge_manager import peek_chat_knowledge_manager
from api.schemas_common import DataResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from utils.chat_utils import get_chat_history_manager

logger = get_logger(__name__)

router = APIRouter(tags=["chat_knowledge"])


async def _delete_owned_file(storage_dir: str, file_path: str) -> None:
    """Remove a file this manager itself wrote, never one merely referenced.

    ``associate_file_with_chat`` can point ``file_path`` at a file elsewhere
    on disk that some other subsystem owns -- only files under *storage_dir*,
    the directory ``upload_file_to_chat`` itself writes into, are removed.
    """
    try:
        storage_root = Path(storage_dir).resolve()
        resolved = Path(file_path).resolve()
    except (OSError, ValueError):
        return
    if resolved != storage_root and storage_root not in resolved.parents:
        return
    try:
        if await asyncio.to_thread(os.path.exists, resolved):
            await asyncio.to_thread(os.remove, resolved)
    except OSError as exc:
        logger.warning("Could not remove chat-knowledge file %s: %s", resolved, exc)


async def delete_chat_knowledge_context(manager, chat_id: str) -> int | None:
    """Delete *chat_id*'s context and everything it owns (#16490).

    Removes the context record -- its temporary knowledge lives on the
    dataclass itself, so it goes with it -- its file associations (deleting
    any file this manager wrote to disk for them), and clears
    ``pending_decisions`` for *chat_id* too: nothing writes into that store
    today, but the issue names "pending decisions" explicitly and the store
    already exists on the manager, so it is swept regardless.

    Persistent facts already promoted to the knowledge base
    (``context.persistent_knowledge_ids``) are untouched -- they outlive the
    session context that produced them.
    ``api/chat_sessions_delete_cleanup.py``'s ``_cleanup_knowledge_base_facts``
    is what retires those, separately, on session deletion.

    Returns the number of file associations removed, or ``None`` if
    *chat_id* had no context.
    """
    if chat_id not in manager.chat_contexts:
        return None

    del manager.chat_contexts[chat_id]
    associations = manager.file_associations.pop(chat_id, [])
    for assoc in associations:
        await _delete_owned_file(manager.storage_dir, assoc.file_path)
    manager.pending_decisions.pop(chat_id, None)

    logger.info(
        "Deleted chat-knowledge context %s (%d file association(s) removed)",
        chat_id,
        len(associations),
    )
    return len(associations)


async def _existing_chat_ids(request: Request) -> set:
    """Every chat_id chat history currently has a session for (#16490).

    Same ``list_sessions_fast`` read ``api/knowledge_maintenance.py``'s
    ``find_session_orphan_facts`` uses, so "orphan" means the same thing in
    both places.
    """
    chat_history_manager = get_chat_history_manager(request)
    if chat_history_manager is None:
        raise HTTPException(status_code=503, detail="Chat history service not available")
    sessions = await chat_history_manager.list_sessions_fast()
    return {s["id"] for s in sessions}


def _find_orphaned_context_ids(manager, existing_chat_ids: set) -> list:
    """chat_ids in *manager*'s contexts with no matching chat session."""
    return [chat_id for chat_id in manager.chat_contexts if chat_id not in existing_chat_ids]


@router.delete("/context/{chat_id}", response_model=DataResponse[Dict[str, Any]])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_chat_context",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def delete_chat_context(chat_id: str, request: Request):
    """Delete a chat-knowledge context -- its owner or an admin only (#16490).

    404 is checked before authorization, using ``peek_chat_knowledge_manager``
    (never the constructing accessor -- a manager that was never built has
    certainly never held a context for *chat_id*). Checking existence first
    also matters for a reason beyond cost: ``validate_chat_ownership``
    (``api/chat.py``) silently claims an unowned ``chat_id`` for the caller
    on its legacy-migration path (sessions predating ownership tracking)
    rather than 404ing, so calling it before this existence check would let a
    probe against a chat_id nothing ever created come back authorized with
    nothing to delete, instead of a clean 404.
    """
    manager = peek_chat_knowledge_manager(request)
    if manager is None or chat_id not in manager.chat_contexts:
        raise HTTPException(status_code=404, detail="No context found for chat")

    # Local import: api.chat also imports api.chat_sessions at module level,
    # and this module's own router gets pulled in from api.chat_sessions_
    # delete_cleanup -- importing api.chat at this module's top would cycle.
    from api.chat import validate_chat_ownership

    ownership = await validate_chat_ownership(chat_id, request)  # SECURITY: owner/org-admin/#689-shared only

    removed = await delete_chat_knowledge_context(manager, chat_id)

    return {
        "success": True,
        "data": {
            "chat_id": chat_id,
            "deleted": True,
            "file_associations_removed": removed,
            "authorized_via": ownership.get("reason"),
        },
    }


@router.get("/context-orphans", response_model=DataResponse[Dict[str, Any]])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_orphaned_chat_contexts",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def find_orphaned_chat_contexts(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
):
    """List chat-knowledge contexts whose chat_id matches no chat (#16490).

    Same list-then-cleanup, admin-only shape as
    ``api/knowledge_maintenance.py``'s ``GET /session-orphans``.
    """
    manager = peek_chat_knowledge_manager(request)
    if manager is None:
        return {"success": True, "data": {"orphaned_count": 0, "orphaned_chat_ids": []}}

    orphan_ids = _find_orphaned_context_ids(manager, await _existing_chat_ids(request))
    return {
        "success": True,
        "data": {"orphaned_count": len(orphan_ids), "orphaned_chat_ids": orphan_ids},
    }


@router.delete("/context-orphans", response_model=DataResponse[Dict[str, Any]])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_orphaned_chat_contexts",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def cleanup_orphaned_chat_contexts(
    request: Request,
    _admin: bool = Depends(check_admin_permission),
    dry_run: bool = Query(True, description="If True, only report without deleting"),
):
    """Delete orphaned chat-knowledge contexts (#16490); dry_run defaults True."""
    manager = peek_chat_knowledge_manager(request)
    if manager is None:
        return {
            "success": True,
            "data": {
                "dry_run": dry_run,
                "orphaned_count": 0,
                "deleted_count": 0,
                "orphaned_chat_ids": [] if dry_run else None,
            },
        }

    orphan_ids = _find_orphaned_context_ids(manager, await _existing_chat_ids(request))

    deleted_count = 0
    if not dry_run:
        for chat_id in list(orphan_ids):
            await delete_chat_knowledge_context(manager, chat_id)
            deleted_count += 1

    return {
        "success": True,
        "data": {
            "dry_run": dry_run,
            "orphaned_count": len(orphan_ids),
            "deleted_count": deleted_count,
            "orphaned_chat_ids": orphan_ids if dry_run else None,
        },
    }
