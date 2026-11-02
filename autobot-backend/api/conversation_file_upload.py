# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Conversation-file upload body checks, split out of ``api.conversation_files`` (#20133).

The filename policy (``security.upload_filename_policy``) and the size cap are unchanged; they moved
here so ``conversation_files.py`` stays under its size ceiling while it gains the owner gate.
"""

from fastapi import HTTPException, UploadFile

from security.upload_filename_policy import is_safe_file
from utils.catalog_http_exceptions import raise_invalid_input

# Maximum file size (50MB) - consistent with general file API
MAX_FILE_SIZE = 50 * 1024 * 1024

_CHUNK_BYTES = 1024 * 1024


async def _read_within(file: UploadFile, limit: int, detail: str) -> bytes:
    """Read *file* in chunks; HTTP 413 (*detail*) the moment it passes *limit*, so no oversize body is buffered."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK_BYTES):
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=detail)
        chunks.append(chunk)
    return b"".join(chunks)


async def validate_and_read_upload_file(file: UploadFile, quota_remaining: int | None = None) -> bytes:
    """Validate the name, then read the body under the size cap and the caller's remaining quota (#20217).

    ``quota_remaining`` is what the uploading user may still store (``None`` = no quota). The stricter of the
    two limits ends the read early, each with its own message.

    Raises:
        HTTPException: 400 for a bad name, 413 for an oversize file or an exhausted quota
    """
    if not file.filename:
        raise_invalid_input("filename", "required")
    if not is_safe_file(file.filename):
        raise_invalid_input("filename", f"file type not allowed: {file.filename}")
    if quota_remaining is not None and quota_remaining < MAX_FILE_SIZE:
        detail = f"Upload quota exceeded: {max(quota_remaining, 0)} bytes of storage left for this user"
        return await _read_within(file, max(quota_remaining, 0), detail)
    return await _read_within(file, MAX_FILE_SIZE, f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB")
