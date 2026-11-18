# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Side effects that follow a work item's completion (MVA-1152, #20102)."""

import logging
from typing import Any, Optional

from autobot_shared.db_session import async_session_scope

logger = logging.getLogger(__name__)


async def release_workspace_for_task(work_item_id: str, session) -> None:
    """Release the per-task workspace; a failure is logged and never blocks the transition."""
    try:
        from services.task_workspace import release_for_task

        await release_for_task(work_item_id, session)
    except Exception:
        logger.warning("workspace release skipped for task=%s", work_item_id, exc_info=True)


async def index_artifacts_after_commit(
    work_item_id: str, project_id: Optional[str], identifier: str, company_id: str, completed_at: Any
) -> None:
    """Index the item's pending work products in a session of its own, once the completion has committed (#21586).

    Queued on the completing transaction, so a rolled-back completion (e.g. a later audit row failing) writes no
    chunk that claims the item completed. Takes ids and scalars only: the caller's session is gone by now.
    A failure is logged and never raised: the completion has already committed.
    """
    try:
        from user_management.database import get_async_session_factory

        from ..kb.artifact_ingestor import ArtifactIngestor

        async with async_session_scope(get_async_session_factory()) as session:
            await ArtifactIngestor().ingest_all_pending(
                session,
                work_item_id=work_item_id,
                project_id=project_id,
                work_item_identifier=identifier,
                company_id=company_id,
                completed_at=completed_at,
            )
    except Exception:
        logger.warning("artifact indexing skipped for task=%s", work_item_id, exc_info=True)
