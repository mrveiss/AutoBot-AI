# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Side effects that follow a work item's completion (MVA-1152, #20102)."""

import logging

logger = logging.getLogger(__name__)


async def release_workspace_for_task(work_item_id: str, session) -> None:
    """Release the per-task workspace; a failure is logged and never blocks the transition."""
    try:
        from services.task_workspace import release_for_task

        await release_for_task(work_item_id, session)
    except Exception:
        logger.warning("workspace release skipped for task=%s", work_item_id, exc_info=True)
