# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Type gate and byte cap on audio uploads, applied before any decode or ffmpeg work (#17778, #19088)."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

from autobot_shared.env_registry import env
from autobot_shared.security.upload_filename_policy import AUDIO_EXTENSIONS, require_safe_upload

_CHUNK_BYTES = 1024 * 1024


def max_upload_bytes() -> int:
    """The configured ``AUTOBOT_AUDIO_UPLOAD_MAX_BYTES``."""
    return int(env("AUTOBOT_AUDIO_UPLOAD_MAX_BYTES"))


async def read_capped_audio(upload: UploadFile) -> bytes:
    """Read *upload* fully: HTTP 400 for a name outside the audio allow-list, 413 once it passes the cap."""
    require_safe_upload(upload.filename, AUDIO_EXTENSIONS)  # #19088: every audio upload route reads through here
    cap = max_upload_bytes()
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(_CHUNK_BYTES):
        total += len(chunk)
        if total > cap:
            raise HTTPException(status_code=413, detail=f"Audio upload exceeds the {cap}-byte limit")
        chunks.append(chunk)
    return b"".join(chunks)
