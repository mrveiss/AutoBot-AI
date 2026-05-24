# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Sprint KB summarizer — Phase 5 implementation (GH#8235).

Replaces the Phase 2 stub. On sprint close, merges the sprint KB collection
into the parent project KB (with summarize=True for LLM condensation, deferred
to GH#8238) then archives the sprint collection.
"""

import uuid

from autobot_shared.logging_manager import get_logger

from .collections import KbCollectionManager

logger = get_logger(__name__)

_kb_manager = KbCollectionManager()


class SprintKbSummarizer:
    """Merges and archives a closed sprint KB collection.

    Phase 5 implementation — calls KbCollectionManager instead of logging a stub.
    """

    def __init__(self, manager: KbCollectionManager | None = None) -> None:
        self._manager = manager or _kb_manager

    async def summarize_and_merge(
        self,
        sprint_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> None:
        """Merge sprint KB into project KB then archive the sprint collection.

        Args:
            sprint_id: UUID of the sprint that just closed.
            project_id: Parent project ID for merge destination.
                        If None, skips merge and only archives.
        """
        if project_id is not None:
            await self._manager.merge_collection(
                src_entity_type=KbCollectionManager.SPRINT_PREFIX,
                src_entity_id=sprint_id,
                dst_entity_type=KbCollectionManager.PROJECT_PREFIX,
                dst_entity_id=project_id,
                summarize=True,
            )

        await self._manager.archive_collection(
            entity_type=KbCollectionManager.SPRINT_PREFIX,
            entity_id=sprint_id,
        )
        logger.info(
            "Sprint KB merged and archived: sprint_id=%s project_id=%s",
            sprint_id,
            project_id,
        )


__all__ = ["SprintKbSummarizer"]
