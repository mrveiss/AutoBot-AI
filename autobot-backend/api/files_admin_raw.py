# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Raw byte download for the SLM admin file browser (#21029).

``GET /files/read`` decodes the file as text with replacement characters, which corrupts
binary files. This route serves the exact bytes. It lives beside ``api.files`` (whose
size ceiling is frozen) and mounts under the same ``/files`` prefix; the allowed roots and
path validation are ``api.files._validate_admin_path``, the same as ``/read``.
"""

import asyncio
import os
import stat
from typing import AsyncIterator, BinaryIO, Tuple
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from api.files import _validate_admin_path
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.error_constants import ERR_FILE_NOT_FOUND

logger = get_logger(__name__)

_DETAIL_NOT_A_FILE = "Path is not a file"
_DETAIL_PERMISSION_DENIED = "Permission denied"
_MEDIA_TYPE = "application/octet-stream"
_CHUNK_BYTES = int(os.getenv("AUTOBOT_ADMIN_RAW_CHUNK_BYTES", str(64 * 1024)))

# Admin-only: this serves whole files from the platform's config and log roots, so unlike the
# legacy inline ``/read`` it is not left open to the proxy.
router = APIRouter(dependencies=[Depends(check_admin_permission)])


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail=ERR_FILE_NOT_FOUND)


def _open_checked(target) -> Tuple[BinaryIO, int]:
    """Open the file and size it from the open handle; 404/400/403 are decided here, before any response."""
    try:
        handle = target.open("rb")
    except FileNotFoundError:
        raise _not_found()
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail=_DETAIL_NOT_A_FILE)
    except PermissionError:
        logger.warning("admin raw download refused: file not readable")
        raise HTTPException(status_code=403, detail=_DETAIL_PERMISSION_DENIED)
    try:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise HTTPException(status_code=400, detail=_DETAIL_NOT_A_FILE)
    except BaseException:
        handle.close()
        raise
    return handle, info.st_size


def _prepare_download(path: str):
    """Validate, check and open in one blocking unit (run via ``asyncio.to_thread``)."""
    target = _validate_admin_path(path)
    try:
        if not target.exists():
            raise _not_found()
        if not target.is_file():
            raise HTTPException(status_code=400, detail=_DETAIL_NOT_A_FILE)
    except FileNotFoundError:
        raise _not_found()
    handle, size = _open_checked(target)
    return handle, size, target.name


def _read_chunk(handle: BinaryIO) -> bytes:
    return handle.read(_CHUNK_BYTES)


async def _stream(handle: BinaryIO) -> AsyncIterator[bytes]:
    """Yield the open handle in threaded chunks; always close it (done, error or disconnect)."""
    try:
        while True:
            chunk = await asyncio.to_thread(_read_chunk, handle)
            if not chunk:
                break
            yield chunk
    finally:
        handle.close()


@router.get(
    "/raw",
    summary="Download file bytes for SLM admin file browser",
    response_class=StreamingResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="admin_download_file",
    error_code_prefix="FILES",
)
async def admin_download_file(path: str) -> StreamingResponse:
    """Stream the file at an absolute path unchanged from an already-open handle."""
    handle, size, name = await asyncio.to_thread(_prepare_download, path)
    headers = {
        "Content-Length": str(size),
        "Content-Disposition": f"attachment; filename*=utf-8''{quote(name)}",
    }
    return StreamingResponse(
        _stream(handle), media_type=_MEDIA_TYPE, headers=headers, background=BackgroundTask(handle.close)
    )
