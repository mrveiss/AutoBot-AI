# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Conversation-file upload body checks, split out of ``api.conversation_files`` (#20133).

The filename policy (``security.upload_filename_policy``) and the size cap are unchanged; they moved
here so ``conversation_files.py`` stays under its size ceiling while it gains the owner gate.
"""

from typing import Awaitable, Callable

from fastapi import HTTPException, UploadFile

from conversation_file_quota import file_too_large
from security.upload_filename_policy import is_safe_file
from utils.catalog_http_exceptions import raise_invalid_input

# Maximum file size (50MB) - consistent with general file API
MAX_FILE_SIZE = 50 * 1024 * 1024

_CHUNK_BYTES = 1024 * 1024


async def _read_within(file: UploadFile, limit: int, refuse: Callable[[], Awaitable[HTTPException]]) -> bytes:
    """Read *file* in chunks; raise ``await refuse()`` the moment it passes *limit*, so no oversize body is buffered."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK_BYTES):
        total += len(chunk)
        if total > limit:
            raise await refuse()
        chunks.append(chunk)
    return b"".join(chunks)


async def _too_large() -> HTTPException:
    return file_too_large(MAX_FILE_SIZE)


async def validate_and_read_upload_file(file: UploadFile, quota_manager=None, user_id: str | None = None) -> bytes:
    """Validate the name, then read the body under the size cap and *user_id*'s remaining quota (#20217).

    ``quota_manager`` (the conversation file manager) says what the user may still store; ``None`` = no
    quota. The stricter limit ends the read early, each refusal with its own stable code.

    Raises:
        HTTPException: 400 for a bad name; 413 (``UploadRefused``) for an oversize file or an exhausted quota
    """
    if not file.filename:
        raise_invalid_input("filename", "required")
    if not is_safe_file(file.filename):
        raise_invalid_input("filename", f"file type not allowed: {file.filename}")
    remaining = None if quota_manager is None else await quota_manager.remaining_upload_quota(user_id)
    if remaining is not None and remaining < MAX_FILE_SIZE:
        return await _read_within(file, max(remaining, 0), lambda: quota_manager.upload_quota_refusal(user_id))
    return await _read_within(file, MAX_FILE_SIZE, _too_large)
