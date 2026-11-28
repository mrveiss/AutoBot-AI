# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""CommentWakeService — a comment on a work item wakes its assignee (GH#9624, #19582).

The comment-specific rules live here; the wake itself is the one dispatcher,
``llc.scheduler.event_wake.wake_agent``:

1. The work item has an agent assignee (in the comment's company).
2. The commenter is not that assignee (an agent's own comment never wakes it).
3. The wake carries the comment as context and ``work_item_commented`` as its reason.

Whether the agent is woken at all -- its status, an already active run, its adapter --
is the dispatcher's decision. #19582 removed the two gates this service had of its own:
``adapter_type == "claude_code"`` (which skipped every NULL-adapter, in-process agent)
and ``heartbeat_enabled`` (which gates only the periodic tick).
"""

import uuid
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..models.enums import HeartbeatInvocationSource
from ..models.work_item import LLCWorkItem, LLCWorkItemComment

logger = get_logger(__name__)


def _comment_context(comment: LLCWorkItemComment) -> Dict[str, Any]:
    return {
        "wake_comment_id": str(comment.id),
        "work_item_id": str(comment.work_item_id),
        "comment_body": comment.body,
        "comment_author_agent_id": str(comment.author_agent_id) if comment.author_agent_id else None,
        "comment_author_user_id": str(comment.author_user_id) if comment.author_user_id else None,
        "comment_created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


class CommentWakeService:
    """Wakes a work item's agent assignee when someone else comments on it."""

    async def trigger_comment_wake(
        self,
        session: AsyncSession,
        work_item_id: str,
        comment_id: str,
    ) -> Optional[uuid.UUID]:
        """Wake for the comment *comment_id*; the created run's id, or ``None``."""
        result = await session.execute(
            select(LLCWorkItemComment).where(
                LLCWorkItemComment.id == uuid.UUID(str(comment_id)),
                LLCWorkItemComment.work_item_id == uuid.UUID(str(work_item_id)),
            )
        )
        comment = result.scalar_one_or_none()
        if comment is None:
            logger.warning("Comment %s not found on work item %s — no comment wake", comment_id, work_item_id)
            return None
        return await self.wake_for_comment(session, comment)

    async def wake_for_comment(self, session: AsyncSession, comment: LLCWorkItemComment) -> Optional[uuid.UUID]:
        """Wake the assignee of *comment*'s work item unless it wrote the comment."""
        from ..scheduler.event_wake import wake_agent

        result = await session.execute(
            select(LLCWorkItem.assignee_agent_id).where(
                LLCWorkItem.id == comment.work_item_id, LLCWorkItem.company_id == comment.company_id
            )
        )
        assignee = result.scalar_one_or_none()
        if assignee is None:
            logger.debug("Work item %s has no agent assignee — no comment wake", comment.work_item_id)
            return None
        if comment.author_agent_id is not None and comment.author_agent_id == assignee:
            logger.debug("Comment %s is the assignee's own — no comment wake", comment.id)
            return None
        return await wake_agent(
            session,
            company_id=comment.company_id,
            agent_ref=assignee,
            reason=HeartbeatInvocationSource.WORK_ITEM_COMMENTED,
            context=_comment_context(comment),
        )
