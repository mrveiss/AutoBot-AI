# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one limit on a knowledge file upload (#19712); the frontend reads it from the backend."""

from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel

from autobot_shared.env_utils import env_int
from knowledge.upload_rejections import UploadRejection, UploadRejectionCode

MAX_FILE_SIZE_MB: int = env_int("AUTOBOT_KB_UPLOAD_MAX_MB", 10)
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
#: Room for the multipart boundaries and the title, category and tags fields beside the file.
_MULTIPART_OVERHEAD_BYTES: int = 1024 * 1024


def _too_large() -> UploadRejection:
    return UploadRejection(
        UploadRejectionCode.TOO_LARGE,
        f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB",
        max_mb=MAX_FILE_SIZE_MB,
    )


def reject_oversize_request(headers: Mapping[str, str]) -> None:
    """Refuse before the form is parsed when the declared body cannot hold an allowed file.

    The size guard does not cover this route (#19712), so nothing else stops it spooling. A missing or
    malformed Content-Length is not refused here: the size check on the parsed file still applies.
    """
    declared = headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_FILE_SIZE_BYTES + _MULTIPART_OVERHEAD_BYTES:
        raise _too_large()


def reject_oversize_file(size: int | None) -> None:
    """Refuse on the parsed file's size, before its content is read into memory."""
    if size is not None and size > MAX_FILE_SIZE_BYTES:
        raise _too_large()


class KnowledgeUploadLimitResponse(BaseModel):
    max_mb: int
