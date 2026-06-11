# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/routes/export.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Export route — DOCX, PDF, SRT, VTT."""

import re
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from transcriber.database import Database
from transcriber.deps import DEFAULT_USER, can_access, get_db
from transcriber.export.segments import build_segment_list
from transcriber.models import ExportRequest

router = APIRouter(tags=["transcriber-export"])


# Development fallback — auth middleware populates request.state.user in production
def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else DEFAULT_USER


_MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "srt": "text/plain; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
}
_EXT = {"docx": "docx", "pdf": "pdf", "srt": "srt", "vtt": "vtt"}


@router.post("/recordings/{recording_id}/export")
async def export_recording(
    recording_id: int,
    body: ExportRequest,
    request: Request,
    db: Database = Depends(get_db),
):
    rec = await db.get_recording(recording_id)
    if not rec or not can_access(rec, _user_id(request)):
        raise HTTPException(404, "Recording not found")
    segments = await build_segment_list(recording_id, db)
    title = rec["filename"]
    fmt = body.format

    if fmt == "srt":
        from transcriber.export.srt_export import segments_to_srt

        content = segments_to_srt(segments, include_speaker=body.include_speaker_names).encode("utf-8")
    elif fmt == "vtt":
        from transcriber.export.vtt_export import segments_to_vtt

        content = segments_to_vtt(segments, include_speaker=body.include_speaker_names).encode("utf-8")
    elif fmt == "docx":
        from transcriber.export.docx_export import build_docx

        content = build_docx(
            title,
            segments,
            include_timestamps=body.include_timestamps,
            include_notes=body.include_notes,
            include_speaker_names=body.include_speaker_names,
        )
    elif fmt == "pdf":
        from transcriber.export.pdf_export import build_pdf

        content = build_pdf(
            title,
            segments,
            include_timestamps=body.include_timestamps,
            include_notes=body.include_notes,
            include_speaker_names=body.include_speaker_names,
        )
    else:
        raise HTTPException(400, f"Unknown format: {fmt}")

    # Sanitize filename to prevent header injection
    safe_title = re.sub(r'[\r\n"\\]+', "_", title)
    filename = f"{safe_title}.{_EXT[fmt]}"
    quoted = urllib.parse.quote(filename)
    return Response(
        content=content,
        media_type=_MIME[fmt],
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quoted}"},
    )
