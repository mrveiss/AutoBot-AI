# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/routes/recordings.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Recording upload, list, delete, audio playback and waveform routes."""

import array
import mimetypes
import uuid
import wave
from pathlib import Path
from typing import AsyncIterator

import aiofiles
import numpy as np
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse

from autobot_shared.logging_manager import get_logger
from transcriber.database import Database
from transcriber.deps import DEFAULT_USER, can_access, get_db
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
    if not project or not can_access(project, _user_id(request)):
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
    logger.info(
        "Recording uploaded: recording_id=%s project_id=%s filename=%s",
        rid,
        project_id,
        file.filename,
    )
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
    if not project or not can_access(project, _user_id(request)):
        raise HTTPException(404, "Project not found")
    rows = await db.list_recordings(project_id, limit=limit, offset=offset)
    return [RecordingOut(**r) for r in rows]


@router.get("/recordings/{recording_id}", response_model=RecordingOut)
async def get_recording(recording_id: int, request: Request, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec or not can_access(rec, _user_id(request)):
        raise HTTPException(404, "Recording not found")
    return RecordingOut(**rec)


@router.delete("/recordings/{recording_id}", status_code=204)
async def delete_recording(recording_id: int, request: Request, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec or not can_access(rec, _user_id(request)):
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


# ── Audio path validation ─────────────────────────────────────────────────────

_CHUNK_SIZE = 65536


def _resolve_audio_path(filepath: str, upload_dir: Path) -> Path:
    """Resolve and validate an audio filepath is within the upload directory.

    Raises HTTPException(404) on path-traversal attempts, symlinks, or missing files.
    """
    resolved_upload = upload_dir.resolve()
    try:
        resolved_file = Path(filepath).resolve()
        resolved_file.relative_to(resolved_upload)  # raises ValueError on traversal
    except (ValueError, OSError):
        logger.warning("Path traversal or invalid path rejected: %r", filepath)
        raise HTTPException(404, "Audio file not found")
    if resolved_file.is_symlink():
        logger.warning("Symlink rejected: %r", str(resolved_file))
        raise HTTPException(404, "Audio file not found")
    if not resolved_file.is_file():
        raise HTTPException(404, "Audio file not found")
    return resolved_file


# ── Waveform generation ───────────────────────────────────────────────────────


def _wav_frames_to_peaks(frames: bytes, n_channels: int, sampwidth: int, width: int) -> list[float]:
    """Downsample raw PCM bytes from a WAV file into `width` peak values in [0,1]."""
    typecode = {1: "B", 2: "h", 4: "i"}.get(sampwidth)
    if not typecode:
        return []
    samples = array.array(typecode, frames)
    mono = samples[::n_channels] if n_channels > 1 else samples
    arr = np.frombuffer(bytes(mono), dtype=np.dtype(typecode))
    if arr.size == 0:
        return []
    max_val = float((1 << (sampwidth * 8 - 1)) if sampwidth > 1 else 255)
    normalized = np.abs(arr.astype(np.float32) / max_val)
    bucket_size = max(1, len(normalized) // width)
    n_buckets = min(width, len(normalized))
    peaks = [float(np.max(normalized[i * bucket_size : (i + 1) * bucket_size])) for i in range(n_buckets)]
    return peaks


def _generate_waveform(path: str, width: int) -> list[float]:
    """Read a WAV file and return up to `width` normalized peak amplitude values in [0,1].

    Returns an empty list for non-WAV files or on any read error (graceful fallback).
    """
    try:
        with wave.open(path, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())
        return _wav_frames_to_peaks(frames, n_channels, sampwidth, width)
    except Exception:
        logger.debug("Waveform generation skipped for non-WAV or unreadable file: %s", path)
        return []


# ── Streaming helpers ─────────────────────────────────────────────────────────


async def _file_iterator(path: Path) -> AsyncIterator[bytes]:
    """Yield file contents in fixed-size chunks."""
    async with aiofiles.open(path, "rb") as fh:
        while True:
            chunk = await fh.read(_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk


# ── Audio endpoints ───────────────────────────────────────────────────────────


@router.get("/recordings/{recording_id}/audio/chunks")
async def audio_chunks(recording_id: int, request: Request, db: Database = Depends(get_db)):
    """Stream audio file with HTTP Range support (RFC 7233)."""
    rec = await db.get_recording(recording_id)
    if not rec or not can_access(rec, _user_id(request)):
        raise HTTPException(404, "Recording not found")

    audio_path = _resolve_audio_path(rec["filepath"], _upload_dir(request))
    file_size = audio_path.stat().st_size
    content_type, _ = mimetypes.guess_type(str(audio_path))
    content_type = content_type or "application/octet-stream"

    range_header = request.headers.get("Range")
    if not range_header:
        return StreamingResponse(
            _file_iterator(audio_path),
            media_type=content_type,
            headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)},
        )

    return _handle_range_request(audio_path, range_header, file_size, content_type)


def _handle_range_request(audio_path: Path, range_header: str, file_size: int, content_type: str) -> Response:
    """Parse Range header and return 206 Partial Content or 416 on error."""
    try:
        unit, rng = range_header.split("=", 1)
        if unit.strip() != "bytes":
            raise ValueError("non-bytes range")
        start_str, end_str = rng.split("-", 1)
        start = int(start_str) if start_str.strip() else 0
        end = int(end_str) if end_str.strip() else file_size - 1
    except (ValueError, AttributeError):
        raise HTTPException(416, "Invalid Range header")

    if start < 0 or end >= file_size or start > end:
        raise HTTPException(
            416,
            "Range Not Satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    length = end - start + 1
    with audio_path.open("rb") as fh:
        fh.seek(start)
        data = fh.read(length)

    return Response(
        content=data,
        status_code=206,
        media_type=content_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        },
    )


@router.get("/recordings/{recording_id}/audio/waveform")
async def audio_waveform(
    recording_id: int,
    request: Request,
    db: Database = Depends(get_db),
    width: int = Query(1000, ge=1, le=10000),
):
    """Return waveform peak data and speaker segments for timeline visualization."""
    rec = await db.get_recording(recording_id)
    if not rec or not can_access(rec, _user_id(request)):
        raise HTTPException(404, "Recording not found")

    audio_path = _resolve_audio_path(rec["filepath"], _upload_dir(request))
    peaks = _generate_waveform(str(audio_path), width)
    segments_raw = await db.list_segments(recording_id)
    segments = [
        {"start_time": s["start_time"], "end_time": s["end_time"], "speaker_id": s.get("speaker_id")}
        for s in segments_raw
    ]

    return {
        "recording_id": recording_id,
        "duration": rec.get("duration"),
        "peaks": peaks,
        "width": len(peaks),
        "segments": segments,
    }
