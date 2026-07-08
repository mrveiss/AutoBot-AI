# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Project disposal: cascade-delete AutoBot data + linked non-shared CodeSource (#11129 P2).

NEVER deletes the GitHub repo. A source shared with other users is unlinked, not deleted.

Import strategy: ``get_source`` and ``delete_source_and_cleanup`` are lazy-imported inside
``_dispose_source`` to avoid heavy/circular imports from codebase_analytics.  Tests patch
them at their source modules:
  patch("api.codebase_analytics.source_storage.get_source", ...)
  patch("api.codebase_analytics.source_service.delete_source_and_cleanup", ...)
"""

import logging

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.sprint import LLCProject, LLCSprint
from llc.models.work_item import LLCWorkItem

logger = logging.getLogger(__name__)


async def dispose(project: LLCProject, session: AsyncSession) -> None:
    """Delete the project's work-items, sprints, the project row, and — when the
    linked CodeSource is not shared with other users — that source's clone + index.
    Idempotent; caller owns the surrounding transaction/commit."""
    project_id = project.id
    code_source_id = project.code_source_id

    await session.execute(delete(LLCWorkItem).where(LLCWorkItem.project_id == project_id))
    await session.execute(delete(LLCSprint).where(LLCSprint.project_id == project_id))
    await session.execute(delete(LLCProject).where(LLCProject.id == project_id))

    if code_source_id:
        await _dispose_source(code_source_id)
    logger.info("Disposed project %s (source=%s)", project_id, code_source_id)


async def _dispose_source(code_source_id: str) -> None:
    """Delete the linked source's clone+index only when it is not shared with others."""
    from api.codebase_analytics.source_service import delete_source_and_cleanup  # noqa: PLC0415
    from api.codebase_analytics.source_storage import get_source  # noqa: PLC0415

    source = await get_source(code_source_id)
    if source is None:
        return
    if getattr(source, "shared_with", None):
        logger.info("Source %s is shared; unlinking only (not deleting)", code_source_id)
        return
    await delete_source_and_cleanup(code_source_id)
