# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Slash command presets API (GH#8595).

GET    /api/chat/presets        -> SlashCommandPreset[]
POST   /api/chat/presets        -> SlashCommandPreset
PUT    /api/chat/presets/{id}   -> SlashCommandPreset
DELETE /api/chat/presets/{id}   -> 204

Storage: Redis hash `chat:presets:{user_id}` in the sessions database.
Each field in the hash is a preset ID whose value is a JSON-encoded preset.

Frontend contract: plain JSON, no envelope wrapper.
"""

import json
from datetime import datetime, timezone
from typing import Optional
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


def _hash_key(user_id: str) -> str:
    return f"chat:presets:{user_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PresetCreate(BaseModel):
    name: str
    description: str
    content: str


class PresetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None


@router.get("/chat/presets")
async def list_presets(
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Return all presets for the authenticated user."""
    user_id = current_user.get("username", "")
    redis = await get_async_redis_client(database=REDIS_DB)
    if redis is None:
        logger.warning("chat_presets: Redis unavailable for user %s", user_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    raw = await redis.hgetall(_hash_key(user_id))
    presets = []
    for value in raw.values():
        try:
            presets.append(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            logger.warning("Skipping corrupt preset entry for user %s", user_id)
    presets.sort(key=lambda p: p.get("createdAt", ""))
    return JSONResponse(content=presets)


@router.post("/chat/presets", status_code=201)
async def create_preset(
    payload: PresetCreate,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Create a new preset for the authenticated user."""
    user_id = current_user.get("username", "")
    now = _now_iso()
    preset = {
        "id": str(uuid4()),
        "name": payload.name,
        "description": payload.description,
        "content": payload.content,
        "createdAt": now,
        "updatedAt": now,
    }
    redis = await get_async_redis_client(database=REDIS_DB)
    if redis is None:
        logger.warning("chat_presets: Redis unavailable for user %s", user_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    await redis.hset(_hash_key(user_id), preset["id"], json.dumps(preset))
    logger.info("Created preset %s for user %s", preset["id"], user_id)
    return JSONResponse(content=preset, status_code=201)


@router.put("/chat/presets/{preset_id}")
async def update_preset(
    preset_id: str,
    payload: PresetUpdate,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Update an existing preset owned by the authenticated user."""
    user_id = current_user.get("username", "")
    redis = await get_async_redis_client(database=REDIS_DB)
    if redis is None:
        logger.warning("chat_presets: Redis unavailable for user %s", user_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    raw = await redis.hget(_hash_key(user_id), preset_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="Preset not found")
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

    await redis.hset(_hash_key(user_id), preset_id, json.dumps(preset))
    logger.info("Updated preset %s for user %s", preset_id, user_id)
    return JSONResponse(content=preset)


@router.delete("/chat/presets/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: str,
    current_user: dict = Depends(get_current_user),
) -> Response:
    """Delete a preset owned by the authenticated user."""
    user_id = current_user.get("username", "")
    redis = await get_async_redis_client(database=REDIS_DB)
    if redis is None:
        logger.warning("chat_presets: Redis unavailable for user %s", user_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    deleted = await redis.hdel(_hash_key(user_id), preset_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Preset not found")
    logger.info("Deleted preset %s for user %s", preset_id, user_id)
    return Response(status_code=204)
