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


def _push_outcome(result: dict, collection_id: str) -> str:
    """Name the outcome from the counts, never from the fact that the call returned.

    A collection that was asked for and joined nothing is reported too: the
    segments are in the Knowledge Base and retrievable, but the collection the
    caller named does not hold them.
    """
    landed = result["indexed"] + result["duplicate"]
    if result["failed"] and not landed:
        return "failed"
    joined = result["collection"]["added"] + result["collection"]["already_present"]
    if result["failed"] or (collection_id and landed and not joined):
        return "partial"
    return "ok"


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
    caller = caller_id_of(request)
    segments = await build_segment_list(recording_id, db)
    result = await push_to_kb(
        recording_id=recording_id,
        recording_filename=rec["filename"],
        segments=segments,
        collection_id=body.collection_id,
        pushed_by=caller,
    )
    # A row here is what /kb/status reports as "pushed", so it is written only once
    # something actually reached the Knowledge Base. The previous
    # `result.get("indexed", len(segments))` reported every segment as indexed
    # whenever the push returned no count at all -- which, while push_to_kb called
    # a method that does not exist, was every push it could ever have made (#17022).
    landed = result["indexed"] + result["duplicate"]
    if landed:
        await db.create_kb_push(recording_id, body.collection_id, caller)
    return {
        "status": _push_outcome(result, body.collection_id),
        "segments": result["segments"],
        "indexed": result["indexed"],
        "duplicate": result["duplicate"],
        "failed": result["failed"],
        "collection": result["collection"],
    }


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
