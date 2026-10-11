# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Byte cap on audio uploads, applied before any decode or ffmpeg work (#17778)."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

from autobot_shared.env_registry import env

_CHUNK_BYTES = 1024 * 1024


def max_upload_bytes() -> int:
    """The configured ``AUTOBOT_AUDIO_UPLOAD_MAX_BYTES``."""
    return int(env("AUTOBOT_AUDIO_UPLOAD_MAX_BYTES"))


async def read_capped_audio(upload: UploadFile) -> bytes:
    """Read *upload* fully, raising HTTP 413 as soon as it passes the cap (never buffers more)."""
    cap = max_upload_bytes()
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(_CHUNK_BYTES):
        total += len(chunk)
        if total > cap:
            raise HTTPException(status_code=413, detail=f"Audio upload exceeds the {cap}-byte limit")
        chunks.append(chunk)
    return b"".join(chunks)
