# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Type gate for image uploads, applied before the body is read (#19088)."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

from autobot_shared.security.upload_filename_policy import IMAGE_EXTENSIONS, require_safe_upload


def require_image_upload(upload: UploadFile) -> None:
    """HTTP 400 unless *upload* has a safe image name and an ``image/`` content type.

    One check for ``/process/image`` and ``/fusion/combine``, so the two cannot drift.
    """
    require_safe_upload(upload.filename, IMAGE_EXTENSIONS)
    if not upload.content_type or not upload.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
