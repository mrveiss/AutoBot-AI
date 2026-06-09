# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Celery beat task: nightly cleanup of stale per-task git worktree workspaces (GH#6471).

Calls task_workspace.cleanup_stale() to evict worktrees older than max_age_days.
"""

from autobot_shared.logging_manager import get_logger
from celery_app import celery_app
from services import task_workspace

logger = get_logger(__name__)


@celery_app.task(bind=True, name="tasks.cleanup_stale_workspaces")
def cleanup_stale_workspaces(self, max_age_days: int = 7) -> dict:
    """Remove per-task git worktrees older than max_age_days (GH#6471)."""
    cleaned = task_workspace.cleanup_stale(max_age_days=max_age_days)
    logger.info("cleanup_stale_workspaces: removed %d stale worktrees", len(cleaned))
    return {"cleaned_task_ids": cleaned, "count": len(cleaned)}
