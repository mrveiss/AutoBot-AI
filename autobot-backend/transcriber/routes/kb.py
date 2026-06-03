# autobot-backend/transcriber/routes/kb.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""KB push and status routes."""
from fastapi import APIRouter, Depends, HTTPException, Request
from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import KbPushRequest, KbPushStatus
from transcriber.routes.export import _build_segment_list
from transcriber.knowledge.kb_push import push_to_kb

router = APIRouter(tags=["transcriber-kb"])


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else "default"


@router.post("/recordings/{recording_id}/kb/push")
async def kb_push(
    recording_id: int,
    body: KbPushRequest,
    request: Request,
    db: Database = Depends(get_db),
):
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Recording not found")
    if rec["status"] != "complete":
        raise HTTPException(400, "Recording not yet transcribed")
    segments = await _build_segment_list(recording_id, db)
    result = await push_to_kb(
        recording_id=recording_id,
        recording_filename=rec["filename"],
        segments=segments,
        collection_id=body.collection_id,
        pushed_by=_user_id(request),
    )
    await db.create_kb_push(recording_id, body.collection_id, _user_id(request))
    return {"status": "ok", "indexed": result.get("indexed", len(segments))}


@router.get("/recordings/{recording_id}/kb/status", response_model=KbPushStatus)
async def kb_status(recording_id: int, request: Request, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Recording not found")
    push = await db.get_latest_kb_push(recording_id)
    if not push:
        return KbPushStatus(pushed=False, pushed_at=None, kb_collection_id=None, pushed_by=None)
    return KbPushStatus(
        pushed=True,
        pushed_at=push["pushed_at"],
        kb_collection_id=push["kb_collection_id"],
        pushed_by=push["pushed_by"],
    )
