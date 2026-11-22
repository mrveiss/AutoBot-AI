# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Existence checks for the caller-supplied paths the code-intelligence routes still take (#620).

Extracted from ``code_intelligence`` so that module does not grow when its evolution routes move to
a required ``source_id`` (#20513).
"""

import asyncio
import os

from utils.catalog_http_exceptions import raise_invalid_input


async def validate_path_exists(path: str) -> None:
    """
    Validate that a path exists on the filesystem.

    Raises HTTPException with 400 status if path does not exist.
    Issue #620.

    Args:
        path: Filesystem path to validate

    Raises:
        HTTPException: If path does not exist
    """
    path_exists = await asyncio.to_thread(os.path.exists, path)
    if not path_exists:
        raise_invalid_input("path", f"does not exist: {path}")


async def validate_path_is_directory(path: str) -> None:
    """
    Validate that a path is a directory.

    Raises HTTPException with 400 status if path is not a directory.
    Issue #620.

    Args:
        path: Filesystem path to validate

    Raises:
        HTTPException: If path is not a directory
    """
    is_dir = await asyncio.to_thread(os.path.isdir, path)
    if not is_dir:
        raise_invalid_input("path", f"not a directory: {path}")
