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


async def validate_and_read_upload_file(
    file: UploadFile,
) -> bytes:
    """
    Validate and read uploaded file content.

    Issue #281: Extracted from upload_conversation_file to reduce function
    length and improve reusability of validation logic.

    Args:
        file: Uploaded file object

    Returns:
        File content as bytes

    Raises:
        HTTPException: If validation fails (400, 413)
    """
    # Validate filename
    if not file.filename:
        raise_invalid_input("filename", "required")

    if not is_safe_file(file.filename):
        raise_invalid_input("filename", f"file type not allowed: {file.filename}")

    # Read file content
    content = await file.read()

    # Check file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
        )

    return content
