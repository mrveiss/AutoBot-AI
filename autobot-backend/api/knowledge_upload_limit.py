# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /api/knowledge_base/upload/limit, so the upload dialog never mirrors the limit (#19712)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from auth_middleware import check_admin_permission
from knowledge.upload_limit import MAX_FILE_SIZE_MB, KnowledgeUploadLimitResponse

router = APIRouter()


@router.get("/upload/limit", response_model=KnowledgeUploadLimitResponse)
async def get_upload_limit(admin_check: bool = Depends(check_admin_permission)) -> KnowledgeUploadLimitResponse:
    """The largest knowledge file the upload route accepts; the same permission as uploading."""
    return KnowledgeUploadLimitResponse(max_mb=MAX_FILE_SIZE_MB)
