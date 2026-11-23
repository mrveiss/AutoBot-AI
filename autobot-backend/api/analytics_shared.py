# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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


NOT_A_GIT_REPOSITORY = "The source checkout is not a git repository"


async def resolve_source_git_root(source_id: str) -> Path | None:
    """The selected source's checkout when it is a git repository of its own, else None (#20513).

    A `.git` that is a symlink or a gitfile (a linked worktree/submodule) can point the miner at another
    source's history, so only a real `.git` directory qualifies. Every git-history read of a source goes here.
    """
    from api.codebase_analytics.endpoints.shared import resolve_scan_root

    repo_path = (await resolve_scan_root(source_id)).resolve()
    git_dir = repo_path / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        return None
    return repo_path


async def require_source_git_root(source_id: str) -> Path:
    """`resolve_source_git_root`, or a 400 when the checkout is not a repository of its own (#20513)."""
    from utils.catalog_http_exceptions import raise_invalid_input

    repo = await resolve_source_git_root(source_id)
    if repo is None:
        raise_invalid_input("source_id", NOT_A_GIT_REPOSITORY)
    return repo


def no_data_response(message: str, **extra_fields) -> dict:
    """Standardized no-data response envelope (Issue #543, extracted #12705).

    Every analytics endpoint returns ``status="no_data"`` plus a message when
    there is nothing to report. The empty result containers differ per
    endpoint (e.g. "issues"/"summary" vs "timeline"/"patterns"/"trends"), so
    callers supply those as keyword arguments.

    Args:
        message: Explanation for why there is no data.
        extra_fields: Endpoint-specific empty result containers merged into
            the response (e.g. ``issues=[], summary={}``).

    Returns:
        Dict with status="no_data", message, and the supplied extra fields.
    """
    return {"status": "no_data", "message": message, **extra_fields}


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
