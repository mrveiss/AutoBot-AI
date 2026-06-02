# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Slash command presets API (GH#4449, GH#8595).

GET    /api/chat/presets        -> SlashCommandPreset[]
POST   /api/chat/presets        -> SlashCommandPreset
PUT    /api/chat/presets/{id}   -> SlashCommandPreset
DELETE /api/chat/presets/{id}   -> 204

Storage: Redis hashes in the sessions database:
- Personal: `chat:presets:user:{user_id}`
- Org-wide: `chat:presets:org:{org_id}`

Each field in the hash is a preset ID whose value is a JSON-encoded preset.

Permissions:
- Any user can create/update/delete personal presets
- Only org admins can create/update/delete org-wide presets
- All org members can read org-wide presets

Frontend contract: plain JSON, no envelope wrapper.
"""

import json
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])

REDIS_DB = "sessions"


def _user_hash_key(user_id: str) -> str:
    return f"chat:presets:user:{user_id}"


def _org_hash_key(org_id: str) -> str:
    return f"chat:presets:org:{org_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_org_admin(current_user: dict) -> bool:
    """Check if user has org admin privileges."""
    role = current_user.get("role", "").lower()
    return role in ["admin", "org_admin", "owner"]


class PresetCreate(BaseModel):
    name: str
    description: str
    content: str
    scope: Literal["personal", "org"] = "personal"


class PresetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None


@router.get("/chat/presets")
async def list_presets(
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Return all presets for the authenticated user (personal + org-wide)."""
    user_id = current_user.get("username", "")
    org_id = current_user.get("org_id")
    redis = await get_async_redis_client(database=REDIS_DB)
    if redis is None:
        logger.warning("chat_presets: Redis unavailable for user %s", user_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    presets = []

    # Fetch personal presets
    user_raw = await redis.hgetall(_user_hash_key(user_id))
    for value in user_raw.values():
        try:
            presets.append(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            logger.warning("Skipping corrupt personal preset entry for user %s", user_id)

    # Fetch org-wide presets if user belongs to an org
    if org_id:
        org_raw = await redis.hgetall(_org_hash_key(org_id))
        for value in org_raw.values():
            try:
                presets.append(json.loads(value))
            except (json.JSONDecodeError, TypeError):
                logger.warning("Skipping corrupt org preset entry for org %s", org_id)

    presets.sort(key=lambda p: p.get("createdAt", ""))
    return JSONResponse(content=presets)


@router.post("/chat/presets", status_code=201)
async def create_preset(
    payload: PresetCreate,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Create a new preset (personal or org-wide).

    Org-wide presets require admin privileges.
    """
    user_id = current_user.get("username", "")
    org_id = current_user.get("org_id")

    # Permission check for org presets
    if payload.scope == "org":
        if not org_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot create org preset: user not associated with an organization"
            )
        if not _is_org_admin(current_user):
            raise HTTPException(
                status_code=403,
                detail="Only org admins can create org-wide presets"
            )

    now = _now_iso()
    preset = {
        "id": str(uuid4()),
        "name": payload.name,
        "description": payload.description,
        "content": payload.content,
        "scope": payload.scope,
        "createdAt": now,
        "updatedAt": now,
    }

    redis = await get_async_redis_client(database=REDIS_DB)
    if redis is None:
        logger.warning("chat_presets: Redis unavailable for user %s", user_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Store in appropriate hash based on scope
    hash_key = _org_hash_key(org_id) if payload.scope == "org" else _user_hash_key(user_id)
    await redis.hset(hash_key, preset["id"], json.dumps(preset))

    logger.info(
        "Created %s preset %s for %s",
        payload.scope,
        preset["id"],
        f"org {org_id}" if payload.scope == "org" else f"user {user_id}"
    )
    return JSONResponse(content=preset, status_code=201)


@router.put("/chat/presets/{preset_id}")
async def update_preset(
    preset_id: str,
    payload: PresetUpdate,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Update an existing preset.

    Users can update their own personal presets.
    Only org admins can update org-wide presets.
    """
    user_id = current_user.get("username", "")
    org_id = current_user.get("org_id")
    redis = await get_async_redis_client(database=REDIS_DB)
    if redis is None:
        logger.warning("chat_presets: Redis unavailable for user %s", user_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Try to find the preset in user's personal presets first
    raw = await redis.hget(_user_hash_key(user_id), preset_id)
    hash_key = _user_hash_key(user_id)
    is_org_preset = False

    # If not found in personal presets, try org presets
    if raw is None and org_id:
        raw = await redis.hget(_org_hash_key(org_id), preset_id)
        if raw is not None:
            hash_key = _org_hash_key(org_id)
            is_org_preset = True

    if raw is None:
        raise HTTPException(status_code=404, detail="Preset not found")

    # Permission check for org presets
    if is_org_preset and not _is_org_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only org admins can update org-wide presets"
        )

    try:
        preset = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=500, detail="Preset data corrupted")

    if payload.name is not None:
        preset["name"] = payload.name
    if payload.description is not None:
        preset["description"] = payload.description
    if payload.content is not None:
        preset["content"] = payload.content
    preset["updatedAt"] = _now_iso()

    await redis.hset(hash_key, preset_id, json.dumps(preset))
    logger.info(
        "Updated %s preset %s",
        "org" if is_org_preset else "personal",
        preset_id
    )
    return JSONResponse(content=preset)


@router.delete("/chat/presets/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: str,
    current_user: dict = Depends(get_current_user),
) -> Response:
    """Delete a preset.

    Users can delete their own personal presets.
    Only org admins can delete org-wide presets.
    """
    user_id = current_user.get("username", "")
    org_id = current_user.get("org_id")
    redis = await get_async_redis_client(database=REDIS_DB)
    if redis is None:
        logger.warning("chat_presets: Redis unavailable for user %s", user_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Try to delete from user's personal presets first
    deleted = await redis.hdel(_user_hash_key(user_id), preset_id)
    if deleted > 0:
        logger.info("Deleted personal preset %s for user %s", preset_id, user_id)
        return Response(status_code=204)

    # If not found in personal presets, try org presets
    if org_id:
        # Check if preset exists in org presets
        raw = await redis.hget(_org_hash_key(org_id), preset_id)
        if raw is not None:
            # Permission check for org presets
            if not _is_org_admin(current_user):
                raise HTTPException(
                    status_code=403,
                    detail="Only org admins can delete org-wide presets"
                )
            await redis.hdel(_org_hash_key(org_id), preset_id)
            logger.info("Deleted org preset %s for org %s", preset_id, org_id)
            return Response(status_code=204)

    raise HTTPException(status_code=404, detail="Preset not found")
