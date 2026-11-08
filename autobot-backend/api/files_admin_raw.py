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

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.files import _validate_admin_path
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.error_constants import ERR_FILE_NOT_FOUND

logger = get_logger(__name__)

_DETAIL_NOT_A_FILE = "Path is not a file"
_DETAIL_PERMISSION_DENIED = "Permission denied"

# Admin-only: this serves whole files from the platform's config and log roots, so unlike the
# legacy inline ``/read`` it is not left open to the proxy.
router = APIRouter(dependencies=[Depends(check_admin_permission)])


def _require_readable(target) -> None:
    """403 before the response starts: a stream that fails to open mid-response cannot be a clean 403."""
    try:
        with target.open("rb"):
            pass
    except PermissionError:
        logger.warning("admin raw download refused: file not readable")
        raise HTTPException(status_code=403, detail=_DETAIL_PERMISSION_DENIED)


@router.get(
    "/raw",
    summary="Download file bytes for SLM admin file browser",
    response_class=FileResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="admin_download_file",
    error_code_prefix="FILES",
)
async def admin_download_file(path: str) -> FileResponse:
    """Stream the file at an absolute path unchanged; no inline size cap (served from disk)."""
    target = _validate_admin_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=ERR_FILE_NOT_FOUND)
    if not target.is_file():
        raise HTTPException(status_code=400, detail=_DETAIL_NOT_A_FILE)
    await asyncio.to_thread(_require_readable, target)
    return FileResponse(path=str(target), filename=target.name, media_type="application/octet-stream")
