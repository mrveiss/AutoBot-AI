# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Boards API — project-scoped board management.

Issue #3242: Boards are lightweight named namespaces stored in Redis as a sorted
set (``kb:boards``) so membership is O(log N) and listing is O(N).

Each board entry is a JSON object:
    {"board_id": str, "name": str, "description": str, "created_at": str}

The sentinel board ``__global__`` is always implicitly available and is never
stored in Redis — it represents the shared pool used before this feature existed.

Endpoints (all require admin auth):
    GET    /boards           — list all boards
    POST   /boards           — create a board
    DELETE /boards/{board_id} — delete a board (facts NOT deleted, just the entry)
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas_knowledge import (
    CreateBoardRequest,
    KnowledgeBoardCreateResponse,
    KnowledgeBoardDeleteResponse,
    KnowledgeBoardsListResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge_factory import get_or_create_knowledge_base

logger = get_logger(__name__)

router = APIRouter()

# Redis key that holds all known boards as a JSON-serialised hash-map
_BOARDS_KEY = "kb:boards"

# The implicit global board — never stored, always valid
GLOBAL_BOARD_ID = "__global__"


def _board_entry(board_id: str, name: str, description: str) -> dict:
    """Build a serialisable board entry dict."""
    return {
        "board_id": board_id,
        "name": name,
        "description": description,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/boards", response_model=KnowledgeBoardsListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_boards",
    error_code_prefix="KNOWLEDGE_BOARDS",
)
async def list_boards(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """List all project-scoped knowledge boards.

    The implicit ``__global__`` board is always included at the top.
    Issue #3242.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")
    try:
        redis_client = kb.redis()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Knowledge base not available") from exc
    raw = await redis_client.hgetall(_BOARDS_KEY)

    boards = [
        {
            "board_id": GLOBAL_BOARD_ID,
            "name": "Global (all boards)",
            "description": "Default shared knowledge pool — existing behaviour.",
            "created_at": None,
        }
    ]
    for _key, value in raw.items():
        try:
            entry = json.loads(value.decode("utf-8") if isinstance(value, bytes) else value)
            boards.append(entry)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Skipping malformed board entry: %s", exc)

    return {"boards": boards, "total": len(boards)}


@router.post("/boards", status_code=201, response_model=KnowledgeBoardCreateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_board",
    error_code_prefix="KNOWLEDGE_BOARDS",
)
async def create_board(
    request: CreateBoardRequest = None,
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """Create a new project-scoped knowledge board.

    Issue #3242.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")
    try:
        redis_client = kb.redis()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Knowledge base not available") from exc

    board_id = request.board_id or str(uuid.uuid4()).replace("-", "")[:16]

    # Guard against duplicates
    existing = await redis_client.hget(_BOARDS_KEY, board_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Board '{board_id}' already exists")

    entry = _board_entry(board_id, request.name, request.description)
    await redis_client.hset(_BOARDS_KEY, board_id, json.dumps(entry))

    logger.info("Created knowledge board: board_id=%s name='%s'", board_id, request.name)
    return {"board_id": board_id, "name": request.name, "created": True}


@router.delete("/boards/{board_id}", response_model=KnowledgeBoardDeleteResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_board",
    error_code_prefix="KNOWLEDGE_BOARDS",
)
async def delete_board(
    board_id: str,
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """Delete a board entry.

    Facts tagged with this board_id are NOT deleted — they remain accessible via
    the global board. Issue #3242.
    """
    if board_id == GLOBAL_BOARD_ID:
        raise HTTPException(status_code=400, detail="Cannot delete the global board")

    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")
    try:
        redis_client = kb.redis()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Knowledge base not available") from exc
    removed = await redis_client.hdel(_BOARDS_KEY, board_id)

    if not removed:
        raise HTTPException(status_code=404, detail=f"Board '{board_id}' not found")

    logger.info("Deleted knowledge board: board_id=%s", board_id)
    return {"board_id": board_id, "deleted": True}
