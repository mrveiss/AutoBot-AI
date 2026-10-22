# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Type gate and byte cap on audio uploads, applied before any decode or ffmpeg work (#17778, #19088)."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

from autobot_shared.env_registry import env
from autobot_shared.security.upload_filename_policy import AUDIO_EXTENSIONS, require_safe_upload

_CHUNK_BYTES = 1024 * 1024


def max_upload_bytes() -> int:
    """The configured ``AUTOBOT_AUDIO_UPLOAD_MAX_BYTES``."""
    return int(env("AUTOBOT_AUDIO_UPLOAD_MAX_BYTES"))


def _checked_name(upload: UploadFile, mime: str | None) -> str | None:
    """The name to gate: the client's, or -- for a route that ignores it -- the client's plus the MIME's suffix.

    ``/voice/transcribe`` picks the temp-file suffix from the content type and never uses the filename, so a
    recorder Blob named ``blob`` (or unnamed) is a legitimate upload there. Its name is then completed with
    the MIME-mapped audio suffix and still goes through the full policy, so ``a/b``, ``..\\x`` or a bidi
    override are refused exactly as before. A name that already has an extension is never completed.
    """
    name = upload.filename or ""
    if mime is None or Path(name).suffix:
        return upload.filename
    from media.audio.pipeline import suffix_for_mime  # noqa: PLC0415 -- the media chain is not inert

    return f"{name or 'upload'}{suffix_for_mime(mime.split(';')[0].strip())}"


async def read_capped_audio(upload: UploadFile, *, name_from_mime: str | None = None) -> bytes:
    """Read *upload* fully: HTTP 400 for a name outside the audio allow-list, 413 once it passes the cap.

    *name_from_mime*: the content type, for a route whose handling is MIME-driven (see ``_checked_name``).
    """
    require_safe_upload(_checked_name(upload, name_from_mime), AUDIO_EXTENSIONS)  # #19088: every audio route
    cap = max_upload_bytes()
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(_CHUNK_BYTES):
        total += len(chunk)
        if total > cap:
            raise HTTPException(status_code=413, detail=f"Audio upload exceeds the {cap}-byte limit")
        chunks.append(chunk)
    return b"".join(chunks)
