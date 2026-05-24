# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC HandoffService — bi-directional work item handoff (GH#8231, GH#8232)."""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client

from ..models.enums import WorkItemStatus
from ..models.work_item import LLCWorkItem
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_CHECKOUT_REDIS_PREFIX = "llc:checkout:"
_NOTIFICATION_CHANNEL_PREFIX = "llc:notifications:"


class HandoffNotAuthorized(Exception):
    """Raised when the human does not hold the item."""


class HandoffNotAllowed(Exception):
    """Raised when the agent does not hold the checkout lock."""


@dataclass
class HandoffAttachment:
    attachment_id: str
    filename: str
    content: str
    mime_type: Optional[str] = None


@dataclass
class HandoffResult:
    work_item_id: str
    target_agent_id: str
    kb_doc_ids: List[str] = field(default_factory=list)
    review_brief: Dict[str, Any] = field(default_factory=dict)


class HandoffService(LLCServiceBase):
    """Bi-directional work item handoff (human↔agent)."""

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
        item = await self._get_and_validate_human(session, work_item_id, user_id)
        kb_doc_ids = await self._ingest_kb(work_item_id, user_id, human_notes, attachments or [])
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
        await self._publish_h2a_notification(company_id, target_agent_id, work_item_id)
        await self._record_h2a_activity(session, company_id, user_id, work_item_id, target_agent_id)
        return HandoffResult(
            work_item_id=work_item_id, target_agent_id=target_agent_id, kb_doc_ids=kb_doc_ids, review_brief=review_brief
        )

    async def agent_to_human(
        self,
        session: AsyncSession,
        work_item_id: str,
        agent_id: str,
        reviewer_user_id: str,
        company_id: str,
        agent_notes: Optional[str] = None,
    ) -> LLCWorkItem:
        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")
        if item.assignee_agent_id is None or str(item.assignee_agent_id) != agent_id:
            raise HandoffNotAllowed(f"Agent {agent_id} does not hold checkout for work item {work_item_id}")
        brief = self._generate_brief(item, agent_notes)
        item.status = WorkItemStatus.IN_REVIEW
        item.reviewer_user_id = uuid.UUID(reviewer_user_id)
        item.review_brief = brief
        item.assignee_type = "user"
        item.assignee_agent_id = None
        item.assignee_user_id = uuid.UUID(reviewer_user_id)
        item.checkout_run_id = None
        item.checkout_locked_at = None
        item.version += 1
        await session.flush()
        redis = await get_async_redis_client()
        if redis is not None:
            await redis.delete(f"{_CHECKOUT_REDIS_PREFIX}{work_item_id}")
        await self._publish_a2h_notification(company_id, work_item_id, reviewer_user_id, brief)
        if self.activity_log:
            try:
                from .activity_log import ActivityEventType
                from ..models.activity import ActorType

                await self.activity_log.record(
                    session,
                    company_id=company_id,
                    actor_type=ActorType.AGENT,
                    actor_id=agent_id,
                    event_type=ActivityEventType.WORK_ITEM_HANDOFF,
                    entity_type="work_item",
                    entity_id=work_item_id,
                    after={"status": WorkItemStatus.IN_REVIEW.value, "reviewer_user_id": reviewer_user_id},
                    metadata={"brief": brief},
                )
            except Exception:
                logger.warning("Activity log failed for agent_to_human %s", work_item_id)
        return item

    async def approve(
        self, session: AsyncSession, work_item_id: str, reviewer_user_id: str, company_id: str
    ) -> LLCWorkItem:
        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")
        self._assert_reviewer(item, reviewer_user_id)
        now = datetime.now(timezone.utc)
        item.status = WorkItemStatus.DONE
        item.completed_at = now
        item.assignee_user_id = None
        item.assignee_agent_id = None
        item.assignee_type = None
        item.checkout_run_id = None
        item.checkout_locked_at = None
        item.version += 1
        await session.flush()
        if self.activity_log:
            try:
                from .activity_log import ActivityEventType
                from ..models.activity import ActorType

                await self.activity_log.record(
                    session,
                    company_id=company_id,
                    actor_type=ActorType.USER,
                    actor_id=reviewer_user_id,
                    event_type=ActivityEventType.WORK_ITEM_REVIEW_APPROVED,
                    entity_type="work_item",
                    entity_id=work_item_id,
                    after={"status": WorkItemStatus.DONE.value, "completed_at": now.isoformat()},
                )
            except Exception:
                logger.warning("Activity log failed for approve %s", work_item_id)
        return item

    async def request_changes(
        self,
        session: AsyncSession,
        work_item_id: str,
        reviewer_user_id: str,
        company_id: str,
        change_request: str,
        return_to_agent_id: Optional[str] = None,
    ) -> LLCWorkItem:
        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")
        self._assert_reviewer(item, reviewer_user_id)
        item.status = WorkItemStatus.IN_PROGRESS
        item.reviewer_user_id = None
        item.review_brief = None
        item.assignee_type = "agent" if return_to_agent_id else None
        item.assignee_agent_id = uuid.UUID(return_to_agent_id) if return_to_agent_id else None
        item.assignee_user_id = None
        item.version += 1
        await session.flush()
        from ..models.work_item import LLCWorkItemComment

        comment = LLCWorkItemComment(
            id=uuid.uuid4(),
            company_id=uuid.UUID(company_id),
            work_item_id=uuid.UUID(work_item_id),
            body=change_request,
            author_user_id=uuid.UUID(reviewer_user_id),
        )
        session.add(comment)
        await session.flush()
        if self.activity_log:
            try:
                from .activity_log import ActivityEventType
                from ..models.activity import ActorType

                await self.activity_log.record(
                    session,
                    company_id=company_id,
                    actor_type=ActorType.USER,
                    actor_id=reviewer_user_id,
                    event_type=ActivityEventType.WORK_ITEM_REVIEW_CHANGES_REQUESTED,
                    entity_type="work_item",
                    entity_id=work_item_id,
                    after={"status": WorkItemStatus.IN_PROGRESS.value, "assignee_agent_id": return_to_agent_id},
                    metadata={"change_request": change_request},
                )
            except Exception:
                logger.warning("Activity log failed for request_changes %s", work_item_id)
        return item

    async def get_brief(self, session: AsyncSession, work_item_id: str) -> Optional[Dict[str, Any]]:
        result = await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)))
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")
        return item.review_brief

    async def _get_and_validate_human(self, session: AsyncSession, work_item_id: str, user_id: str) -> LLCWorkItem:
        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")
        holder_user_id = str(item.assignee_user_id) if item.assignee_user_id else None
        if item.assignee_type != "user" or holder_user_id != user_id:
            raise HandoffNotAuthorized(
                f"User {user_id} does not hold work item {work_item_id} (current holder: {holder_user_id!r}, type: {item.assignee_type!r})"
            )
        return item

    async def _ingest_kb(
        self, work_item_id: str, user_id: str, human_notes: str, attachments: List[HandoffAttachment]
    ) -> List[str]:
        from ..kb.work_item_kb import WorkItemKB

        kb = WorkItemKB()
        doc_ids: List[str] = []
        if human_notes.strip():
            doc_id = await kb.ingest_notes(work_item_id=work_item_id, notes=human_notes, source_user_id=user_id)
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
        key = f"{_CHECKOUT_REDIS_PREFIX}{work_item_id}"
        existing = await redis.get(key)
        if existing in (f"user:{user_id}", user_id):
            await redis.delete(key)

    async def _publish_h2a_notification(self, company_id: str, target_agent_id: str, work_item_id: str) -> None:
        payload = json.dumps(
            {
                "event": "work_item.handoff_ready",
                "work_item_id": work_item_id,
                "target_agent_id": target_agent_id,
                "has_human_handoff_context": True,
            }
        )
        channel = f"{_NOTIFICATION_CHANNEL_PREFIX}{company_id}"
        try:
            redis = await get_async_redis_client()
            if redis is None:
                return
            await redis.publish(channel, payload)
        except Exception:
            logger.exception("Failed to publish h2a handoff notification for work_item %s — non-fatal", work_item_id)

    async def _publish_a2h_notification(
        self, company_id: str, work_item_id: str, reviewer_user_id: str, brief: Dict[str, Any]
    ) -> None:
        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("HandoffService: Redis unavailable, dropping a2h notification")
            return
        try:
            channel = f"{_NOTIFICATION_CHANNEL_PREFIX}{company_id}"
            await redis.publish(
                channel,
                json.dumps(
                    {
                        "event_type": "work_item.handoff",
                        "work_item_id": work_item_id,
                        "reviewer_user_id": reviewer_user_id,
                        "brief_title": brief.get("title"),
                        "brief_identifier": brief.get("identifier"),
                    }
                ),
            )
        except Exception:
            logger.debug("HandoffService._publish_a2h_notification failed (swallowed)")

    async def _record_h2a_activity(
        self, session: AsyncSession, company_id: str, user_id: str, work_item_id: str, target_agent_id: str
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
            logger.warning("Activity log failed for h2a handoff work_item=%s", work_item_id)

    def _generate_brief(self, item: LLCWorkItem, agent_notes: Optional[str]) -> Dict[str, Any]:
        comment_excerpts = [
            {
                "author_agent_id": str(c.author_agent_id) if c.author_agent_id else None,
                "author_user_id": str(c.author_user_id) if c.author_user_id else None,
                "excerpt": c.body[:200],
            }
            for c in (item.comments or [])
        ]
        return {
            "work_item_id": str(item.id),
            "identifier": item.identifier,
            "title": item.title,
            "type": item.type.value if hasattr(item.type, "value") else item.type,
            "status_before_handoff": item.status.value if hasattr(item.status, "value") else item.status,
            "priority": item.priority.value if hasattr(item.priority, "value") else item.priority,
            "description_excerpt": (item.description or "")[:500],
            "acceptance_criteria": item.acceptance_criteria or [],
            "comment_count": len(item.comments or []),
            "recent_comments": comment_excerpts[-5:],
            "agent_notes": agent_notes,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "stub-phase4",
        }

    def _assert_reviewer(self, item: LLCWorkItem, reviewer_user_id: str) -> None:
        if item.reviewer_user_id is None or str(item.reviewer_user_id) != reviewer_user_id:
            raise HandoffNotAllowed(f"User {reviewer_user_id} is not the reviewer for work item {item.id}")


__all__ = ["HandoffService", "HandoffAttachment", "HandoffResult", "HandoffNotAuthorized", "HandoffNotAllowed"]

HandoffError = HandoffNotAllowed  # backward compat alias for GH#8234
