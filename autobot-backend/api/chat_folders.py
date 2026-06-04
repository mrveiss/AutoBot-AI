# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""
CRUD endpoints for chat conversation folders (GH#8987).

Folders are stored per-user in Redis as a JSON array under the key
``chat:folders:{username}``.  Each folder carries its own ``session_ids``
list so a single read gives the full folder tree without a secondary lookup.

Response shape: plain JSONResponse (matches chat_presets.py pattern).
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from api.schemas_chat import FolderCreate, FolderUpdate, SessionFolderAssign
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.redis_constants import REDIS_KEY

logger = get_logger(__name__)

router = APIRouter()

_MAX_NESTING = 3


def _folder_redis_key(username: str) -> str:
    return REDIS_KEY.CHAT_FOLDERS.format(username=username)


async def _load_folders(redis: Any, username: str) -> List[Dict]:
    raw = await redis.get(_folder_redis_key(username))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


async def _save_folders(redis: Any, username: str, folders: List[Dict]) -> None:
    await redis.set(_folder_redis_key(username), json.dumps(folders))


def _folder_depth(folders: List[Dict], folder_id: str, seen: set | None = None) -> int:
    """Return 1-based depth of folder_id in the tree."""
    if seen is None:
        seen = set()
    if folder_id in seen:
        return 0
    seen.add(folder_id)
    folder = next((f for f in folders if f["id"] == folder_id), None)
    if not folder or folder.get("parent_id") is None:
        return 1
    return 1 + _folder_depth(folders, folder["parent_id"], seen)


def _serialize_folder(f: Dict) -> Dict:
    session_ids = f.get("session_ids", [])
    return {
        "id": f["id"],
        "name": f["name"],
        "parent_id": f.get("parent_id"),
        "owner": f.get("owner", ""),
        "pinned": f.get("pinned", False),
        "created_at": f.get("created_at", ""),
        "session_ids": session_ids,
        "session_count": len(session_ids),
    }


@router.get("/chat/folders")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_chat_folders",
    error_code_prefix="CHAT_FOLDERS",
)
async def list_folders(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Return all folders for the authenticated user."""
    from autobot_shared.redis_client import get_redis_client as get_redis_mgr

    username = current_user.get("username", "")
    redis = await get_redis_mgr(async_client=True, database="main")
    if redis is None:
        return JSONResponse(status_code=503, content={"error": "Redis unavailable"})

    folders = await _load_folders(redis, username)
    sorted_folders = sorted(folders, key=lambda f: (not f.get("pinned", False), f.get("name", "")))
    result = [_serialize_folder(f) for f in sorted_folders]
    return JSONResponse(content={"folders": result, "count": len(result)})


@router.post("/chat/folders", status_code=201)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_chat_folder",
    error_code_prefix="CHAT_FOLDERS",
)
async def create_folder(
    request: Request,
    body: FolderCreate,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Create a new folder. Enforces max 3-level nesting."""
    from autobot_shared.redis_client import get_redis_client as get_redis_mgr
    from exceptions import get_exceptions_lazy

    _, _, _, ValidationError, _ = get_exceptions_lazy()

    username = current_user.get("username", "")
    redis = await get_redis_mgr(async_client=True, database="main")
    if redis is None:
        return JSONResponse(status_code=503, content={"error": "Redis unavailable"})

    folders = await _load_folders(redis, username)

    if body.parent_id:
        parent = next((f for f in folders if f["id"] == body.parent_id), None)
        if not parent:
            raise ValidationError("Parent folder not found")
        depth = _folder_depth(folders, body.parent_id)
        if depth >= _MAX_NESTING:
            raise ValidationError(f"Maximum folder nesting depth ({_MAX_NESTING}) reached")

    folder: Dict = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "parent_id": body.parent_id,
        "owner": username,
        "pinned": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "session_ids": [],
    }
    folders.append(folder)
    await _save_folders(redis, username, folders)
    logger.info("Created folder %s for user %s", folder["id"], username)
    return JSONResponse(content=_serialize_folder(folder), status_code=201)


@router.put("/chat/folders/{folder_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_chat_folder",
    error_code_prefix="CHAT_FOLDERS",
)
async def update_folder(
    folder_id: str,
    request: Request,
    body: FolderUpdate,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Rename, pin, or re-parent a folder."""
    from autobot_shared.redis_client import get_redis_client as get_redis_mgr
    from exceptions import get_exceptions_lazy

    _, _, ResourceNotFoundError, ValidationError, _ = get_exceptions_lazy()

    username = current_user.get("username", "")
    redis = await get_redis_mgr(async_client=True, database="main")
    if redis is None:
        return JSONResponse(status_code=503, content={"error": "Redis unavailable"})

    folders = await _load_folders(redis, username)
    folder = next((f for f in folders if f["id"] == folder_id), None)
    if not folder:
        raise ResourceNotFoundError(f"Folder {folder_id} not found")

    if body.name is not None:
        folder["name"] = body.name
    if body.pinned is not None:
        folder["pinned"] = body.pinned
    if "parent_id" in body.model_fields_set:
        if body.parent_id is not None:
            if body.parent_id == folder_id:
                raise ValidationError("A folder cannot be its own parent")
            parent = next((f for f in folders if f["id"] == body.parent_id), None)
            if not parent:
                raise ValidationError("Parent folder not found")
            depth = _folder_depth(folders, body.parent_id)
            if depth >= _MAX_NESTING:
                raise ValidationError(f"Maximum folder nesting depth ({_MAX_NESTING}) reached")
        folder["parent_id"] = body.parent_id

    await _save_folders(redis, username, folders)
    return JSONResponse(content=_serialize_folder(folder))


@router.delete("/chat/folders/{folder_id}", status_code=204)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_chat_folder",
    error_code_prefix="CHAT_FOLDERS",
)
async def delete_folder(
    folder_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> Response:
    """Delete a folder. Child folders are re-parented to root; sessions stay unfoldered."""
    from autobot_shared.redis_client import get_redis_client as get_redis_mgr
    from exceptions import get_exceptions_lazy

    _, _, ResourceNotFoundError, _, _ = get_exceptions_lazy()

    username = current_user.get("username", "")
    redis = await get_redis_mgr(async_client=True, database="main")
    if redis is None:
        return Response(status_code=503)

    folders = await _load_folders(redis, username)
    folder = next((f for f in folders if f["id"] == folder_id), None)
    if not folder:
        raise ResourceNotFoundError(f"Folder {folder_id} not found")

    # Re-parent direct children to deleted folder's parent
    for f in folders:
        if f.get("parent_id") == folder_id:
            f["parent_id"] = folder.get("parent_id")

    folders = [f for f in folders if f["id"] != folder_id]
    await _save_folders(redis, username, folders)
    logger.info("Deleted folder %s for user %s", folder_id, username)
    return Response(status_code=204)


@router.put("/chat/sessions/{session_id}/folder")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="assign_session_folder",
    error_code_prefix="CHAT_FOLDERS",
)
async def assign_session_to_folder(
    session_id: str,
    request: Request,
    body: SessionFolderAssign,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Assign a chat session to a folder (or remove it when folder_id is None)."""
    from autobot_shared.redis_client import get_redis_client as get_redis_mgr
    from exceptions import get_exceptions_lazy

    _, _, ResourceNotFoundError, _, _ = get_exceptions_lazy()

    username = current_user.get("username", "")
    redis = await get_redis_mgr(async_client=True, database="main")
    if redis is None:
        return JSONResponse(status_code=503, content={"error": "Redis unavailable"})

    folders = await _load_folders(redis, username)

    # Remove session from all folders first
    for f in folders:
        f.setdefault("session_ids", [])
        if session_id in f["session_ids"]:
            f["session_ids"].remove(session_id)

    # Add to target folder
    if body.folder_id:
        target = next((f for f in folders if f["id"] == body.folder_id), None)
        if not target:
            raise ResourceNotFoundError(f"Folder {body.folder_id} not found")
        if session_id not in target["session_ids"]:
            target["session_ids"].append(session_id)

    await _save_folders(redis, username, folders)
    logger.info("Assigned session %s to folder %s for user %s", session_id, body.folder_id, username)
    return JSONResponse(content={"session_id": session_id, "folder_id": body.folder_id})
