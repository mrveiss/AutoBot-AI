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

from sqlalchemy import delete, select
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

    # #13920: collect the child ids BEFORE the bulk deletes — afterwards there is
    # nothing left to derive the collection names from, and the collections would
    # be stranded with no entity to trace them back to.
    child_work_items = (
        (await session.execute(select(LLCWorkItem.id).where(LLCWorkItem.project_id == project_id))).scalars().all()
    )
    child_sprints = (
        (await session.execute(select(LLCSprint.id).where(LLCSprint.project_id == project_id))).scalars().all()
    )

    await session.execute(delete(LLCWorkItem).where(LLCWorkItem.project_id == project_id))
    await session.execute(delete(LLCSprint).where(LLCSprint.project_id == project_id))
    await session.execute(delete(LLCProject).where(LLCProject.id == project_id))

    await _drop_kb_collections(project_id, child_work_items, child_sprints)

    if code_source_id:
        await _dispose_source(code_source_id)
    logger.info("Disposed project %s (source=%s)", project_id, code_source_id)


async def _drop_kb_collections(project_id, work_item_ids, sprint_ids) -> None:
    """Drop the KB collections belonging to a disposed project and its children (#13920).

    Never raises — a disposal must not fail because ChromaDB is unreachable.
    ``drop_collection`` already swallows and logs per collection; this only
    guards the import and the loop itself.
    """
    from llc.kb.collections import KbCollectionManager  # noqa: PLC0415

    manager = KbCollectionManager()
    targets = [(KbCollectionManager.PROJECT_PREFIX, project_id)]
    targets += [(KbCollectionManager.WORK_ITEM_PREFIX, wid) for wid in work_item_ids]
    targets += [(KbCollectionManager.SPRINT_PREFIX, sid) for sid in sprint_ids]

    for entity_type, entity_id in targets:
        try:
            await manager.drop_collection(entity_type, entity_id)
        except Exception:  # noqa: BLE001 - defensive; drop_collection does not raise
            logger.warning("Could not drop KB collection for %s %s", entity_type, entity_id, exc_info=True)


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
