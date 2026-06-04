# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared helpers for analytics API modules (Issue #3440).

Contains utilities reused across analytics_quality, analytics_evolution,
analytics_code_review, and analytics_code_generation.
"""

from pathlib import Path

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def resolve_source_or_404(source_id: str | None) -> None:
    """Raise HTTP 404 if source_id is provided but not found.

    Uses lazy imports of resolve_source_root and HTTPException to avoid
    loading the full codebase_analytics package at module import time.
    """
    if source_id is None:
        return
    from fastapi import HTTPException

    from api.codebase_analytics.endpoints.shared import resolve_source_root

    source_root = await resolve_source_root(source_id)
    if source_root is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")


async def resolve_source_root_or_404(source_id: str | None) -> Path | None:
    """Validate source_id and return its filesystem root path.

    Issue #3441: Phase 2 — callers need the resolved path to scope query
    results to the project directory.  Returns None when source_id is None
    (no scoping requested).  Raises HTTP 404 when source_id is provided but
    the source record does not exist or has no clone_path.

    Args:
        source_id: Source identifier supplied by the caller, or None.

    Returns:
        Path to the source clone directory, or None if source_id is None.
    """
    if source_id is None:
        return None
    from fastapi import HTTPException

    from api.codebase_analytics.endpoints.shared import resolve_source_root

    source_root = await resolve_source_root(source_id)
    if source_root is None:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")
    return source_root
