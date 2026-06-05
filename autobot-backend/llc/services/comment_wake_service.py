# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""CommentWakeService — triggers agent heartbeat runs on work item comments (GH#9624).

When a comment is added to a work item:
1. Check if assignee is a claude_code agent
2. Check if no run is currently active for that agent
3. Build wake payload with comment context
4. Create heartbeat run with WORK_ITEM_COMMENTED source
5. Dispatch adapter with wake_reason and wake_comment_id in context

Dedup guard: only trigger if no RUNNING or QUEUED run exists for the agent.
"""

import logging
import uuid
from datetime import timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import HeartbeatInvocationSource, LLCRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun
from ..models.work_item import LLCWorkItem, LLCWorkItemComment

logger = logging.getLogger(__name__)

_ACTIVE_RUN_STATUSES = {LLCRunStatus.QUEUED.value, LLCRunStatus.RUNNING.value}


class CommentWakeService:
    """Service to trigger agent wakes when work item comments are added."""

    async def trigger_comment_wake(
        self,
        session: AsyncSession,
        work_item_id: str,
        comment_id: str,
    ) -> Optional[uuid.UUID]:
        """Trigger a heartbeat run for the work item's assignee if applicable.

        Returns:
            The created run ID if a wake was triggered, None otherwise.
        """
        # Fetch work item and assignee info
        result = await session.execute(
            select(LLCWorkItem.assignee_agent_id, LLCWorkItem.company_id).where(
                LLCWorkItem.id == uuid.UUID(work_item_id)
            )
        )
        row = result.first()
        if not row or not row.assignee_agent_id:
            logger.debug("Work item %s has no agent assignee — skipping comment wake", work_item_id)
            return None

        assignee_agent_id = str(row.assignee_agent_id)
        company_id = row.company_id

        # Check if assignee is a claude_code agent
        agent_result = await session.execute(
            text("""
                SELECT aon.adapter_type, aon.adapter_config, aon.context_mode,
                       aon.heartbeat_enabled
                FROM agent_org_nodes aon
                WHERE aon.agent_id = :agent_id
            """),
            {"agent_id": assignee_agent_id},
        )
        agent_row = agent_result.mappings().first()
        if not agent_row:
            logger.debug("Agent %s not found — skipping comment wake", assignee_agent_id)
            return None

        adapter_type = agent_row.get("adapter_type")
        if adapter_type != "claude_code":
            logger.debug(
                "Agent %s adapter type is %s (not claude_code) — skipping comment wake",
                assignee_agent_id,
                adapter_type,
            )
            return None

        if not agent_row.get("heartbeat_enabled"):
            logger.debug("Agent %s heartbeat disabled — skipping comment wake", assignee_agent_id)
            return None

        # Dedup: check for active runs
        active_run = await self._find_active_run(session, assignee_agent_id)
        if active_run:
            logger.info(
                "Agent %s already has active run %s — queuing comment %s for next heartbeat",
                assignee_agent_id,
                active_run.id,
                comment_id,
            )
            # TODO: Queue comment for delivery at next heartbeat
            return None

        # Fetch comment body for context
        comment_result = await session.execute(
            select(LLCWorkItemComment).where(LLCWorkItemComment.id == uuid.UUID(comment_id))
        )
        comment = comment_result.scalar_one_or_none()
        if not comment:
            logger.warning("Comment %s not found — cannot build wake context", comment_id)
            return None

        # Build wake context
        context = {
            "wake_reason": "work_item_commented",
            "wake_comment_id": comment_id,
            "work_item_id": work_item_id,
            "comment_body": comment.body,
            "comment_author_agent_id": str(comment.author_agent_id) if comment.author_agent_id else None,
            "comment_author_user_id": str(comment.author_user_id) if comment.author_user_id else None,
            "comment_created_at": comment.created_at.isoformat() if comment.created_at else None,
        }

        # Create heartbeat run
        run = LLCHeartbeatRun(
            id=uuid.uuid4(),
            company_id=company_id,
            agent_id=assignee_agent_id,
            invocation_source=HeartbeatInvocationSource.WORK_ITEM_COMMENTED.value,
            status=LLCRunStatus.QUEUED.value,
            context_snapshot=context,
        )
        session.add(run)
        await session.flush()

        logger.info(
            "Created comment-triggered run %s for agent %s (work_item=%s, comment=%s)",
            run.id,
            assignee_agent_id,
            work_item_id,
            comment_id,
        )

        # Build agent config for dispatch
        agent_config = {
            "agent_id": assignee_agent_id,
            "adapter_type": adapter_type,
            "adapter_config": agent_row.get("adapter_config") or {},
            "context_mode": agent_row.get("context_mode"),
            "company_id": str(company_id),
        }

        return run.id, agent_config, context

    async def _find_active_run(self, session: AsyncSession, agent_id: str) -> Optional[LLCHeartbeatRun]:
        """Find any QUEUED or RUNNING run for the given agent."""
        result = await session.execute(
            select(LLCHeartbeatRun)
            .where(
                LLCHeartbeatRun.agent_id == agent_id,
                LLCHeartbeatRun.status.in_(_ACTIVE_RUN_STATUSES),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
