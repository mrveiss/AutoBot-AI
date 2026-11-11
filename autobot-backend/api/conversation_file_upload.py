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


async def _read_under_quota(
    file: UploadFile, quota_manager, user_id: str | None, session_id: str | None
) -> tuple[bytes, str | None]:
    """Read under the user's remaining quota, but let an identical re-upload through (``add_file`` dedupes it).

    A body can only dedupe against a file the session already holds, so the read may run to that file's size; a body
    still past the quota afterwards is kept only if ``would_deduplicate`` (the storage rule) says it adds no bytes.
    Returns the body and, when the dedupe check hashed it, that SHA-256 so the caller need not hash it again.
    """
    remaining = max(await quota_manager.remaining_upload_quota(user_id), 0)
    if remaining >= MAX_FILE_SIZE:
        return await _read_within(file, MAX_FILE_SIZE, _too_large), None
    dedupable = 0 if session_id is None else await quota_manager.largest_live_session_file(session_id)

    async def refuse() -> HTTPException:
        return await quota_manager.upload_quota_refusal(user_id)

    content = await _read_within(file, min(max(remaining, dedupable), MAX_FILE_SIZE), refuse)
    if len(content) <= remaining:
        return content, None
    file_hash = await quota_manager.hash_content(content)
    if not await quota_manager.would_deduplicate(session_id, content, file_hash):
        raise await refuse()
    return content, file_hash


async def read_upload_file(
    file: UploadFile, quota_manager=None, user_id: str | None = None, session_id: str | None = None
) -> tuple[bytes, str | None]:
    """Validate the name, then read the body under the size cap and *user_id*'s remaining quota (#20217).

    ``quota_manager`` (the conversation file manager) says what the user may still store; ``None`` = no
    quota. The stricter limit ends the read early, each refusal with its own stable code. With *session_id*,
    bytes the session already holds are not charged again (#20722). Returns ``(body, sha256 or None)``; the
    hash is set only when the dedupe check already computed it.

    Raises:
        HTTPException: 400 for a bad name; 413 (``UploadRefused``) for an oversize file or an exhausted quota
    """
    if not file.filename:
        raise_invalid_input("filename", "required")
    if not is_safe_file(file.filename):
        raise_invalid_input("filename", f"file type not allowed: {file.filename}")
    if quota_manager is None:
        return await _read_within(file, MAX_FILE_SIZE, _too_large), None
    return await _read_under_quota(file, quota_manager, user_id, session_id)


async def validate_and_read_upload_file(
    file: UploadFile, quota_manager=None, user_id: str | None = None, session_id: str | None = None
) -> bytes:
    """``read_upload_file`` for callers that only need the body."""
    return (await read_upload_file(file, quota_manager, user_id, session_id))[0]
