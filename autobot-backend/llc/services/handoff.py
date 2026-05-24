# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC HandoffService — Human→Agent work item handoff (GH#8232).

Responsibilities:
  1. Validate the human holds the item (claimed or co-worker).
  2. Ingest human_notes + text attachments into the per-work-item KB collection.
  3. Transition the item: status=ready, assignee_type=agent, assignee_agent_id=target.
  4. Release the human claim.
  5. Write a context brief into review_brief JSONB.
  6. Publish a notification to ``llc:notifications:{company_id}`` so the agent's
     next heartbeat picks up the item.
  7. Record an activity log entry.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client

from ..models.enums import WorkItemStatus
from ..models.work_item import LLCWorkItem
from . import LLCServiceBase

logger = logging.getLogger(__name__)


class HandoffNotAuthorized(Exception):
    """Raised when the human does not hold the item or is not a co-worker."""


@dataclass
class HandoffAttachment:
    """Attachment submitted alongside human notes."""

    attachment_id: str
    filename: str
    content: str
    mime_type: Optional[str] = None


@dataclass
class HandoffResult:
    """Summary returned by HandoffService.human_to_agent()."""

    work_item_id: str
    target_agent_id: str
    kb_doc_ids: List[str] = field(default_factory=list)
    review_brief: Dict[str, Any] = field(default_factory=dict)


class HandoffService(LLCServiceBase):
    """Service for Human→Agent work item handoff."""

    async def human_to_agent(
        self,
        session: AsyncSession,
        *,
        work_item_id: str,
        target_agent_id: str,
        user_id: str,
        company_id: str,
        human_notes: str,
        user_display: str = "",
        attachments: Optional[List[HandoffAttachment]] = None,
    ) -> HandoffResult:
        """Hand off a work item from a human to an agent.

        Steps:
          1. Validate human holds the item.
          2. Ingest notes + text attachments into KB.
          3. Set status=ready, assignee_type=agent, assignee_agent_id.
          4. Release the human checkout key in Redis.
          5. Write review_brief JSONB.
          6. Publish Redis notification.
          7. Record activity log entry.

        Raises:
            HandoffNotAuthorized: when the human does not hold the item.
            ValueError: when the work item is not found.
        """
        item = await self._get_and_validate(session, work_item_id, user_id)

        kb_doc_ids = await self._ingest_kb(
            work_item_id=work_item_id,
            user_id=user_id,
            human_notes=human_notes,
            attachments=attachments or [],
        )

        review_brief: Dict[str, Any] = {
            "handed_off_by": user_display or user_id,
            "notes": human_notes,
            "kb_indexed": bool(kb_doc_ids),
        }

        item.status = WorkItemStatus.READY
        item.assignee_type = "agent"
        item.assignee_agent_id = uuid.UUID(target_agent_id)
        item.assignee_user_id = None
        item.checkout_run_id = None
        item.checkout_locked_at = None
        item.review_brief = review_brief
        item.version += 1
        await session.flush()

        await self._release_redis_key(work_item_id, user_id)
        await self._publish_notification(company_id, target_agent_id, work_item_id)
        await self._record_activity(
            session,
            company_id=company_id,
            user_id=user_id,
            work_item_id=work_item_id,
            target_agent_id=target_agent_id,
        )

        return HandoffResult(
            work_item_id=work_item_id,
            target_agent_id=target_agent_id,
            kb_doc_ids=kb_doc_ids,
            review_brief=review_brief,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_and_validate(
        self,
        session: AsyncSession,
        work_item_id: str,
        user_id: str,
    ) -> LLCWorkItem:
        result = await session.execute(
            select(LLCWorkItem)
            .where(LLCWorkItem.id == uuid.UUID(work_item_id))
            .with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")

        holder_user_id = str(item.assignee_user_id) if item.assignee_user_id else None
        if item.assignee_type != "user" or holder_user_id != user_id:
            raise HandoffNotAuthorized(
                f"User {user_id} does not hold work item {work_item_id} "
                f"(current holder: {holder_user_id!r}, type: {item.assignee_type!r})"
            )
        return item

    async def _ingest_kb(
        self,
        work_item_id: str,
        user_id: str,
        human_notes: str,
        attachments: List[HandoffAttachment],
    ) -> List[str]:
        from ..kb.work_item_kb import WorkItemKB

        kb = WorkItemKB()
        doc_ids: List[str] = []

        if human_notes.strip():
            doc_id = await kb.ingest_notes(
                work_item_id=work_item_id,
                notes=human_notes,
                source_user_id=user_id,
            )
            doc_ids.append(doc_id)

        for att in attachments:
            doc_id = await kb.ingest_attachment(
                work_item_id=work_item_id,
                attachment_id=att.attachment_id,
                filename=att.filename,
                content=att.content,
                mime_type=att.mime_type,
            )
            if doc_id:
                doc_ids.append(doc_id)

        return doc_ids

    async def _release_redis_key(self, work_item_id: str, user_id: str) -> None:
        redis = await get_async_redis_client()
        if redis is None:
            return
        key = f"llc:checkout:{work_item_id}"
        existing = await redis.get(key)
        if existing in (f"user:{user_id}", user_id):
            await redis.delete(key)

    async def _publish_notification(
        self,
        company_id: str,
        target_agent_id: str,
        work_item_id: str,
    ) -> None:
        payload = json.dumps(
            {
                "event": "work_item.handoff_ready",
                "work_item_id": work_item_id,
                "target_agent_id": target_agent_id,
                "has_human_handoff_context": True,
            }
        )
        channel = f"llc:notifications:{company_id}"
        try:
            redis = await get_async_redis_client()
            if redis is None:
                return
            await redis.publish(channel, payload)
        except Exception:
            logger.exception(
                "Failed to publish handoff notification for work_item %s — non-fatal",
                work_item_id,
            )

    async def _record_activity(
        self,
        session: AsyncSession,
        company_id: str,
        user_id: str,
        work_item_id: str,
        target_agent_id: str,
    ) -> None:
        if not self.activity_log:
            return
        try:
            from .activity_log import ActivityEventType

            await self.activity_log.record(
                session,
                company_id=company_id,
                actor_type="user",
                actor_id=user_id,
                event_type=ActivityEventType.WORK_ITEM_ASSIGNED,
                entity_type="work_item",
                entity_id=work_item_id,
                after={
                    "assignee_type": "agent",
                    "assignee_agent_id": target_agent_id,
                    "status": WorkItemStatus.READY.value,
                    "has_human_handoff_context": True,
                },
            )
        except Exception:
            logger.warning("Activity log failed for handoff work_item=%s", work_item_id)


__all__ = ["HandoffService", "HandoffAttachment", "HandoffResult", "HandoffNotAuthorized"]
