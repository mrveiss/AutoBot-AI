# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resumable knowledge uploads under /api/knowledge_base/uploads (#19713). Admin, as the single-request routes.

The handoff runs after the response, because transcribing a long video outlasts any proxy timeout; the
client polls the session. A failed handoff keeps the file, so it can be completed again. So can one whose
worker went away, once it has sat for the session TTL; until then it's taken to be still running.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request

from auth_middleware import check_admin_permission, get_auth_middleware
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import SecurityConstants
from knowledge.schemas.chunked_upload import UploadCreate
from security.upload_filename_policy import require_safe_upload
from services import chunked_upload as uploads

logger = get_logger(__name__)
router = APIRouter(prefix="/uploads")

DOCUMENT_MAX_BYTES = env_int_clamped("AUTOBOT_UPLOAD_DOCUMENT_MAX_MB", 200, 1, 4096) * 1024 * 1024


def _owner(request: Request) -> str:
    user = get_auth_middleware().get_user_from_request(request) or {}
    owner = user.get("user_id") or user.get("username")
    if not owner:
        raise HTTPException(status_code=403, detail="The upload cannot be attributed to a person")
    return str(owner)


def _session(upload_id: str, request: Request) -> uploads.UploadSession:
    try:
        return uploads.get_upload_session(upload_id, _owner(request))
    except uploads.UploadSessionNotFound as exc:
        raise HTTPException(status_code=404, detail="No such upload") from exc


def _max_bytes(body: UploadCreate) -> int:
    """Judges the name for what the file is for, and returns the size that use allows."""
    if body.target == "document":
        from api.knowledge import require_safe_kb_name  # that module mounts this router

        require_safe_kb_name(body.filename)
        return DOCUMENT_MAX_BYTES
    require_safe_upload(body.filename, SecurityConstants.ALLOWED_AUDIO_EXTENSIONS)
    return uploads.MAX_TOTAL_BYTES


@router.get("/limits")
async def get_upload_limits(_admin: bool = Depends(check_admin_permission)) -> dict:
    """So the upload dialog mirrors nothing: what each use allows, and which files are media."""
    return {
        "chunk_bytes": uploads.CHUNK_BYTES,
        "document_max_bytes": min(DOCUMENT_MAX_BYTES, uploads.MAX_TOTAL_BYTES),
        "media_max_bytes": uploads.MAX_TOTAL_BYTES,
        "media_extensions": sorted(SecurityConstants.ALLOWED_AUDIO_EXTENSIONS),
    }


@router.post("")
async def create_upload(body: UploadCreate, request: Request, _admin: bool = Depends(check_admin_permission)) -> dict:
    params = body.model_dump(exclude={"filename", "total_size"})
    params["title"] = body.title or body.filename
    try:
        session = await asyncio.to_thread(
            uploads.create_session, _owner(request), body.filename, body.total_size, _max_bytes(body), params
        )
    except uploads.UploadRejected as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return uploads.describe_upload(session)


@router.get("/expired")
async def list_expired_uploads(_admin: bool = Depends(check_admin_permission)) -> dict:
    """Abandoned sessions for a person to review; each still takes up its disk space until cancelled."""
    sessions = await asyncio.to_thread(uploads.expired_sessions)
    return {"expired": [uploads.describe_upload(session) for session in sessions]}


@router.get("/{upload_id}")
async def get_upload(upload_id: str, request: Request, _admin: bool = Depends(check_admin_permission)) -> dict:
    """Where to resume from, and how the handoff went."""
    return uploads.describe_upload(_session(upload_id, request))


@router.put("/{upload_id}/chunks")
async def put_chunk(
    upload_id: str,
    request: Request,
    offset: int = Query(ge=0),
    x_chunk_sha256: str = Header(default=""),
    _admin: bool = Depends(check_admin_permission),
) -> dict:
    session = _session(upload_id, request)
    try:
        session = await uploads.write_chunk(session, offset, request.stream(), x_chunk_sha256)
    except uploads.UploadOffsetMismatch as exc:
        raise HTTPException(status_code=409, detail={"received": exc.received}) from exc
    except uploads.UploadBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except uploads.UploadRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return uploads.describe_upload(session)


async def _hand_to_document(kb, request: Request, session: uploads.UploadSession) -> dict:
    from api.knowledge import ingest_uploaded_document

    params = session.params
    content = await asyncio.to_thread(uploads.staged_path(session).read_bytes)
    reply = await ingest_uploaded_document(
        kb, request, session.filename, content, params["title"], params["category"], params["tags"]
    )
    return {"document_id": reply.document_id, "word_count": reply.word_count}


async def _hand_to_transcript(kb, session: uploads.UploadSession) -> dict:
    from api.knowledge import _ingest_audio_source

    params = session.params
    reply = await _ingest_audio_source(
        kb_to_use=kb,
        source=os.fspath(uploads.staged_path(session)),
        title=params["title"],
        category=params["category"],
        tags=params["tags"],
        whisper_model=params["whisper_model"],
        language=params["language"],
    )
    return {"document_id": reply.document_id, "word_count": reply.word_count}


async def _hand_over(kb, request: Request, session: uploads.UploadSession) -> None:
    try:
        if session.params["target"] == "document":
            result = await _hand_to_document(kb, request, session)
        else:
            result = await _hand_to_transcript(kb, session)
    except Exception as exc:  # recorded for the person polling; the file stays for another try
        logger.exception("Upload %s could not be handed over", session.id)
        detail = getattr(exc, "detail", None) or getattr(exc, "message", None) or type(exc).__name__
        uploads.record_handoff_failure(session, str(detail))
        return
    uploads.record_handoff(session, result)


@router.post("/{upload_id}/complete", status_code=202)
async def complete_upload(
    upload_id: str,
    request: Request,
    background: BackgroundTasks,
    _admin: bool = Depends(check_admin_permission),
) -> dict:
    """Every byte is here: check it, and hand it to the knowledge base. Poll the session for the result."""
    from api.knowledge import get_or_create_knowledge_base

    session = _session(upload_id, request)
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not initialized")
    try:
        session = await uploads.begin_handoff(session)
    except uploads.UploadOffsetMismatch as exc:
        raise HTTPException(status_code=409, detail={"received": exc.received}) from exc
    except (uploads.UploadRejected, uploads.UploadBusy) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background.add_task(_hand_over, kb, request, session)
    return uploads.describe_upload(session)


@router.delete("/{upload_id}")
async def cancel_upload(upload_id: str, request: Request, _admin: bool = Depends(check_admin_permission)) -> dict:
    """The person gives up on their own upload, which removes what was staged."""
    session = _session(upload_id, request)
    try:
        await asyncio.to_thread(uploads.cancel_session, session)
    except (uploads.UploadRejected, uploads.UploadBusy) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"upload_id": upload_id, "cancelled": True}
