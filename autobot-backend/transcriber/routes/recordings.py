# autobot-backend/transcriber/routes/recordings.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Recording upload, list, delete routes. Pipeline trigger wired in Plan 2."""
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File

from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import RecordingOut

router = APIRouter(tags=["transcriber-recordings"])

_ALLOWED_EXTENSIONS = {".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm"}


def _upload_dir(request: Request) -> Path:
    return Path(request.app.state.transcriber_upload_dir)


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else "default"


@router.post("/projects/{project_id}/recordings", response_model=RecordingOut, status_code=202)
async def upload_recording(
    project_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Database = Depends(get_db),
):
    if not await db.get_project(project_id):
        raise HTTPException(404, "Project not found")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported audio format: {ext}")
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = _upload_dir(request) / safe_name
    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)
    rid = await db.create_recording(
        project_id, file.filename or safe_name, str(dest), user_id=_user_id(request)
    )
    rec = await db.get_recording(rid)
    return RecordingOut(**rec)


@router.get("/projects/{project_id}/recordings", response_model=list[RecordingOut])
async def list_recordings(project_id: int, db: Database = Depends(get_db)):
    if not await db.get_project(project_id):
        raise HTTPException(404, "Project not found")
    rows = await db.list_recordings(project_id)
    return [RecordingOut(**r) for r in rows]


@router.get("/recordings/{recording_id}", response_model=RecordingOut)
async def get_recording(recording_id: int, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    return RecordingOut(**rec)


@router.delete("/recordings/{recording_id}", status_code=204)
async def delete_recording(recording_id: int, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    filepath = Path(rec["filepath"])
    if filepath.exists():
        filepath.unlink(missing_ok=True)
    await db.delete_recording(recording_id)
    return Response(status_code=204)
