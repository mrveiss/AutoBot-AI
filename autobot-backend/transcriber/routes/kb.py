# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/routes/kb.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""KB push and status routes."""

from fastapi import APIRouter, Depends, HTTPException, Request

from transcriber.database import Database
from transcriber.deps import authenticate, caller_can_access, caller_id_of, get_db
from transcriber.export.segments import build_segment_list
from transcriber.knowledge.kb_push import push_to_kb
from transcriber.models import KbPushRequest, KbPushStatus

router = APIRouter(tags=["transcriber-kb"], dependencies=[Depends(authenticate)])


@router.post("/recordings/{recording_id}/kb/push")
async def kb_push(
    recording_id: int,
    body: KbPushRequest,
    request: Request,
    db: Database = Depends(get_db),
):
    rec = await db.get_recording(recording_id)
    if not rec or not caller_can_access(rec, request):
        raise HTTPException(404, "Recording not found")
    if rec["status"] != "complete":
        raise HTTPException(400, "Recording not yet transcribed")
    segments = await build_segment_list(recording_id, db)
    result = await push_to_kb(
        recording_id=recording_id,
        recording_filename=rec["filename"],
        segments=segments,
        collection_id=body.collection_id,
        pushed_by=caller_id_of(request),
    )
    await db.create_kb_push(recording_id, body.collection_id, caller_id_of(request))
    return {"status": "ok", "indexed": result.get("indexed", len(segments))}


@router.get("/recordings/{recording_id}/kb/status", response_model=KbPushStatus)
async def kb_status(recording_id: int, request: Request, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec or not caller_can_access(rec, request):
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
