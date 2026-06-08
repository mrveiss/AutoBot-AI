# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/routes/recordings.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Recording upload, list, delete routes. Pipeline trigger wired in Plan 2."""

import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile

from autobot_shared.logging_manager import get_logger
from transcriber.database import Database
from transcriber.deps import DEFAULT_USER, get_db
from transcriber.models import RecordingOut

logger = get_logger(__name__)

router = APIRouter(tags=["transcriber-recordings"])

_ALLOWED_EXTENSIONS = {".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm"}


def _upload_dir(request: Request) -> Path:
    return Path(request.app.state.transcriber_upload_dir)


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else DEFAULT_USER


@router.post("/projects/{project_id}/recordings", response_model=RecordingOut, status_code=202)
async def upload_recording(
    project_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Database = Depends(get_db),
):
    project = await db.get_project(project_id)
    if not project or project["user_id"] != _user_id(request):
        raise HTTPException(404, "Project not found")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported audio format: {ext}")
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = _upload_dir(request) / safe_name
    async with aiofiles.open(dest, "wb") as f:
        while chunk := await file.read(65536):
            await f.write(chunk)
    rid = await db.create_recording(project_id, file.filename or safe_name, str(dest), user_id=_user_id(request))
    logger.info("Recording uploaded: recording_id=%s project_id=%s filename=%s", rid, project_id, file.filename)
    rec = await db.get_recording(rid)
    return RecordingOut(**rec)


@router.get("/projects/{project_id}/recordings", response_model=list[RecordingOut])
async def list_recordings(
    project_id: int,
    request: Request,
    db: Database = Depends(get_db),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    project = await db.get_project(project_id)
    if not project or project["user_id"] != _user_id(request):
        raise HTTPException(404, "Project not found")
    rows = await db.list_recordings(project_id, limit=limit, offset=offset)
    return [RecordingOut(**r) for r in rows]


@router.get("/recordings/{recording_id}", response_model=RecordingOut)
async def get_recording(recording_id: int, request: Request, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Recording not found")
    return RecordingOut(**rec)


@router.delete("/recordings/{recording_id}", status_code=204)
async def delete_recording(recording_id: int, request: Request, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Recording not found")
    filepath = Path(rec["filepath"])
    if filepath.exists():
        filepath.unlink(missing_ok=True)
    try:
        await db.delete_recording(recording_id)
    except KeyError:
        raise HTTPException(404, "Recording not found")
    logger.info("Recording deleted: recording_id=%s", recording_id)
    return Response(status_code=204)
