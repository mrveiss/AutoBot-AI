# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC WorkItemService — CRUD, atomic checkout, and status transitions (GH#8213, GH#8230).

Checkout strategy:
  1. Redis SET NX EX 1800 as fast-path fence (prevents DB round-trips for obvious conflicts).
  2. SELECT … FOR UPDATE on the row as the authoritative lock.
  3. Write ``checkout_run_id`` / ``checkout_locked_at`` + bump ``version``.

Status transitions:
  Only the edges defined in _ALLOWED_TRANSITIONS are accepted. Any other
  transition raises ``InvalidTransition``.

Identifier generation:
  PostgreSQL advisory lock on the company's numeric hash, then RETURNING on an
  UPDATE to ``llc_companies.issue_counter`` — producing ``<prefix>-<counter>``.
  Falls back to a UUID-based placeholder when the companies table is absent
  (unit-test environments without full schema).

Co-working (GH#8230):
  enable_coworking / disable_coworking manage the secondary co-worker slot.
  Callers must hold board-level or lead permission (owner/admin/lead role).
  Atomic checkout invariants are unchanged — only the primary assignee holds
  the checkout lock. Co-workers may read, comment, and create subtasks freely.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client

from ..models.enums import ActivityEventType, CoWorkerType, WorkItemPriority, WorkItemStatus, WorkItemType
from ..models.label import LLCWorkItemLabel
from ..models.membership import LLCCompanyMembership
from ..models.work_item import LLCWorkItem, LLCWorkItemComment
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

# Module-level set that holds references to fire-and-forget background tasks
# so the GC cannot collect them before they complete.  Each task removes itself
# via add_done_callback.  (GH#9532)
_bg_tasks: set = set()

_CHECKOUT_TTL = 1800  # seconds

# Allowed status transitions: from → {to, ...}
_ALLOWED_TRANSITIONS: Dict[WorkItemStatus, set] = {
    WorkItemStatus.BACKLOG: {WorkItemStatus.READY, WorkItemStatus.BLOCKED, WorkItemStatus.CANCELLED},
    WorkItemStatus.READY: {WorkItemStatus.IN_PROGRESS, WorkItemStatus.BLOCKED, WorkItemStatus.CANCELLED},
    WorkItemStatus.IN_PROGRESS: {
        WorkItemStatus.IN_REVIEW,
        WorkItemStatus.BLOCKED,
        WorkItemStatus.DONE,
        WorkItemStatus.CANCELLED,
    },
    WorkItemStatus.IN_REVIEW: {
        WorkItemStatus.IN_PROGRESS,
        WorkItemStatus.DONE,
        WorkItemStatus.BLOCKED,
        WorkItemStatus.CANCELLED,
    },
    WorkItemStatus.BLOCKED: {WorkItemStatus.READY, WorkItemStatus.IN_PROGRESS, WorkItemStatus.CANCELLED},
    WorkItemStatus.DONE: set(),
    WorkItemStatus.CANCELLED: set(),
}


class CheckoutConflict(Exception):
    """Raised when a work item is already checked out by a different agent."""


class InvalidTransition(Exception):
    """Raised when a status transition is not permitted."""


class CoWorkingPermissionError(Exception):
    """Raised when the caller lacks board or lead permission for co-working ops."""


_COWORKING_ALLOWED_ROLES: frozenset = frozenset({"owner", "admin", "lead"})

_AGENT_ORG_ROLE_TO_COWORKER_ROLE: Dict[str, str] = {
    "manager": "admin",
    "coordinator": "lead",
    "specialist": "member",
    "worker": "member",
}


async def resolve_actor_role(session: AsyncSession, actor_id: Optional[str], company_id: str) -> str:
    """Resolve the effective coworker-permission role for actor_id (GH#8583).

    Tries LLCCompanyMembership first (human user identified by UUID), then
    AgentOrgNode (agent identified by string key).  Returns "member" when the
    actor is unknown — this is the safest default and will be rejected by
    enable_coworking / disable_coworking permission checks.
    """
    if not actor_id:
        return "member"

    # Human user path: actor_id must be a valid UUID.
    try:
        actor_uuid = uuid.UUID(actor_id)
        company_uuid = uuid.UUID(company_id)
        result = await session.execute(
            select(LLCCompanyMembership).where(
                LLCCompanyMembership.user_id == actor_uuid,
                LLCCompanyMembership.company_id == company_uuid,
            )
        )
        membership = result.scalar_one_or_none()
        if membership is not None:
            return membership.role.value if hasattr(membership.role, "value") else str(membership.role)
    except (ValueError, AttributeError):
        pass

    # Agent path: look up AgentOrgNode by string agent_id.
    try:
        from models.agent_org import AgentOrgNode

        company_uuid = uuid.UUID(company_id)
        result = await session.execute(
            select(AgentOrgNode).where(
                AgentOrgNode.agent_id == actor_id,
                AgentOrgNode.company_id == company_uuid,
            )
        )
        node = result.scalar_one_or_none()
        if node is not None:
            org_role = node.org_role.value if hasattr(node.org_role, "value") else str(node.org_role)
            return _AGENT_ORG_ROLE_TO_COWORKER_ROLE.get(org_role, "member")
    except ImportError as exc:
        logger.warning("AgentOrgNode model unavailable; defaulting actor_role to member: %s", exc)
    except (ValueError, AttributeError):
        pass

    return "member"


async def _run_intent_similarity(work_intent: str, item_title: str, work_item_id: str) -> None:
    """Fire-and-forget similarity check — never raises (GH#9532).

    Accepts plain strings only; no session reference is passed so this coroutine
    is safe to run after the request-scoped session has been closed.
    """
    try:
        from .work_intent_similarity import check_similarity

        await check_similarity(work_intent, item_title, work_item_id)
    except Exception as exc:
        logger.debug("_run_intent_similarity: non-critical failure: %s", exc)


def _schedule_intent_similarity(work_intent: str, item_title: str, work_item_id: str) -> None:
    """Schedule *_run_intent_similarity* as a background asyncio task (GH#9532).

    The task is anchored in the module-level ``_bg_tasks`` set so the GC cannot
    collect it before it completes.  The task MUST NOT receive a request-scoped
    session — only plain strings are passed.
    """
    task = asyncio.create_task(_run_intent_similarity(work_intent, item_title, work_item_id))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _post_checkout_comment(
    session: AsyncSession,
    item: LLCWorkItem,
    work_intent: str,
    agent_id: str,
    service: Optional["WorkItemService"] = None,
) -> None:
    """Add the audit comment 'Starting <id>: <intent>' — never raises (GH#9532).

    A flush failure inside the SAVEPOINT rolls back only the nested transaction;
    the outer checkout transaction is unaffected.  CommentWakeService is
    intentionally not triggered here — the "Starting …" note is a self-authored
    audit entry, not a human-initiated comment.
    """
    try:
        comment_body = f"Starting {item.identifier}: {work_intent}"
        async with session.begin_nested():
            # Reuse WorkItemService.add_comment to avoid re-implementing comment
            # insertion logic.  add_comment calls session.flush() internally;
            # wrapping the whole block in begin_nested() ensures a flush failure
            # rolls back only this savepoint and leaves the session committable.
            if service is not None:
                await service.add_comment(
                    session,
                    str(item.id),
                    str(item.company_id),
                    comment_body,
                    author_agent_id=agent_id,
                )
            else:
                comment = LLCWorkItemComment(
                    id=uuid.uuid4(),
                    company_id=item.company_id,
                    work_item_id=item.id,
                    body=comment_body,
                    author_agent_id=uuid.UUID(agent_id) if agent_id else None,
                    author_user_id=None,
                )
                session.add(comment)
                await session.flush()
        logger.debug(
            "_post_checkout_comment: posted comment for work_item=%s agent=%s",
            item.id,
            agent_id,
        )
    except Exception as exc:
        logger.warning("_post_checkout_comment: failed (non-critical): %s", exc)


class WorkItemService(LLCServiceBase):
    """Service for LLC work item lifecycle management."""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        session: AsyncSession,
        company_id: str,
        type: WorkItemType,
        title: str,
        *,
        description: Optional[str] = None,
        acceptance_criteria: Optional[List[str]] = None,
        priority: WorkItemPriority = WorkItemPriority.MEDIUM,
        story_points: Optional[int] = None,
        parent_id: Optional[str] = None,
        project_id: Optional[str] = None,
        sprint_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        assignee_agent_id: Optional[str] = None,
        assignee_user_id: Optional[str] = None,
        created_by_agent_id: Optional[str] = None,
        created_by_user_id: Optional[str] = None,
        labels: Optional[List[str]] = None,
        requires_approval_before: Optional[List[str]] = None,
    ) -> LLCWorkItem:
        # GH#6469: inherit goal_id from parent when not explicitly provided
        resolved_goal_id: Optional[uuid.UUID] = uuid.UUID(goal_id) if goal_id else None
        if resolved_goal_id is None and parent_id is not None:
            parent = await self.get(session, parent_id)
            if parent is not None and parent.goal_id is not None:
                resolved_goal_id = parent.goal_id

        identifier = await self._next_identifier(session, company_id)
        item = LLCWorkItem(
            id=uuid.uuid4(),
            company_id=uuid.UUID(company_id),
            type=type,
            title=title,
            description=description,
            acceptance_criteria=acceptance_criteria,
            priority=priority,
            story_points=story_points,
            identifier=identifier,
            parent_id=uuid.UUID(parent_id) if parent_id else None,
            project_id=uuid.UUID(project_id) if project_id else None,
            sprint_id=uuid.UUID(sprint_id) if sprint_id else None,
            goal_id=resolved_goal_id,
            assignee_agent_id=uuid.UUID(assignee_agent_id) if assignee_agent_id else None,
            assignee_user_id=uuid.UUID(assignee_user_id) if assignee_user_id else None,
            created_by_agent_id=uuid.UUID(created_by_agent_id) if created_by_agent_id else None,
            created_by_user_id=uuid.UUID(created_by_user_id) if created_by_user_id else None,
            labels=labels or [],
            requires_approval_before=requires_approval_before or [],
        )
        session.add(item)
        await session.flush()
        return item

    async def get(self, session: AsyncSession, work_item_id: str) -> Optional[LLCWorkItem]:
        result = await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)))
        return result.scalar_one_or_none()

    async def update(
        self,
        session: AsyncSession,
        work_item_id: str,
        **fields: Any,
    ) -> Optional[LLCWorkItem]:
        item = await self.get(session, work_item_id)
        if item is None:
            return None
        allowed = {
            "title",
            "description",
            "acceptance_criteria",
            "priority",
            "story_points",
            "labels",
            "requires_approval_before",
            "parent_id",
            "sprint_id",
            "goal_id",
            "assignee_agent_id",
            "assignee_user_id",
            "assignee_type",
            "scheduled_start",
            "scheduled_end",
        }
        # Single-assignee invariant (#10532, FR-HYBRID-01): assigning to one
        # party clears the other and fixes assignee_type.
        if fields.get("assignee_user_id"):
            item.assignee_agent_id = None
            fields.setdefault("assignee_type", "user")
        elif fields.get("assignee_agent_id"):
            item.assignee_user_id = None
            fields.setdefault("assignee_type", "agent")
        for key, val in fields.items():
            if key not in allowed:
                raise ValueError(f"Field '{key}' is not updatable via WorkItemService.update()")
            setattr(item, key, val)
        await session.flush()
        return item

    async def list_by_project(
        self,
        session: AsyncSession,
        company_id: str,
        *,
        project_id: Optional[str] = None,
        type: Optional[WorkItemType] = None,
        status: Optional[WorkItemStatus] = None,
        assignee_agent_id: Optional[str] = None,
        reviewer_user_id: Optional[str] = None,
        sprint_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        top_level_only: bool = False,
        co_worker_agent_id: Optional[str] = None,
        co_worker_user_id: Optional[str] = None,
        label_ids: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[LLCWorkItem]:
        q = select(LLCWorkItem).where(LLCWorkItem.company_id == uuid.UUID(company_id))
        if project_id:
            q = q.where(LLCWorkItem.project_id == uuid.UUID(project_id))
        if type:
            q = q.where(LLCWorkItem.type == type)
        if status:
            q = q.where(LLCWorkItem.status == status)
        if assignee_agent_id:
            q = q.where(LLCWorkItem.assignee_agent_id == uuid.UUID(assignee_agent_id))
        if reviewer_user_id:
            # Review inbox (#10533): items routed to a specific human reviewer.
            q = q.where(LLCWorkItem.reviewer_user_id == uuid.UUID(reviewer_user_id))
        if sprint_id:
            q = q.where(LLCWorkItem.sprint_id == uuid.UUID(sprint_id))
        if top_level_only:
            q = q.where(LLCWorkItem.parent_id.is_(None))
        elif parent_id:
            q = q.where(LLCWorkItem.parent_id == uuid.UUID(parent_id))
        if co_worker_agent_id:
            q = q.where(LLCWorkItem.co_worker_agent_id == uuid.UUID(co_worker_agent_id))
        if co_worker_user_id:
            q = q.where(LLCWorkItem.co_worker_user_id == uuid.UUID(co_worker_user_id))
        if label_ids:
            label_uuids = [uuid.UUID(lid) for lid in label_ids]
            q = q.where(
                LLCWorkItem.id.in_(
                    select(LLCWorkItemLabel.work_item_id).where(LLCWorkItemLabel.label_id.in_(label_uuids))
                )
            )
        q = q.order_by(LLCWorkItem.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(q)
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Atomic checkout
    # ------------------------------------------------------------------

    async def checkout(
        self,
        session: AsyncSession,
        work_item_id: str,
        agent_id: str,
        run_id: Optional[str] = None,
        work_intent: Optional[str] = None,
    ) -> LLCWorkItem:
        """Atomically claim a work item for an agent.

        Step 1: Redis SET NX EX as fast-path fence.
        Step 2: SELECT FOR UPDATE to prevent race across DB workers.
        Step 3: Write checkout fields + transition to IN_PROGRESS.
        Step 4: (non-blocking) intent similarity check vs. title.
        Step 5: Auto-post audit comment when work_intent is supplied.

        Raises CheckoutConflict if another agent holds the lock.
        The work_intent parameter is optional; omitting it preserves existing behaviour exactly.
        """
        redis_key = f"llc:checkout:{work_item_id}"
        redis = await get_async_redis_client()

        if redis is not None:
            acquired = await redis.set(redis_key, agent_id, nx=True, ex=_CHECKOUT_TTL)
            if not acquired:
                existing = await redis.get(redis_key)
                if existing and existing != agent_id:
                    raise CheckoutConflict(f"Work item {work_item_id} already checked out by agent {existing}")

        # DB-level lock
        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            if redis is not None:
                await redis.delete(redis_key)
            raise ValueError(f"Work item {work_item_id} not found")

        if item.checkout_run_id is not None and str(item.assignee_agent_id) != agent_id:
            if redis is not None:
                await redis.delete(redis_key)
            raise CheckoutConflict(f"Work item {work_item_id} already checked out by agent {item.assignee_agent_id}")

        item.checkout_run_id = run_id or str(uuid.uuid4())
        item.checkout_locked_at = datetime.now(timezone.utc)
        item.assignee_agent_id = uuid.UUID(agent_id)
        item.assignee_type = "agent"
        # GH#9532 — persist intent for audit trail.  Clearing prior intent when
        # work_intent is absent is deliberate: stale intent must not survive a
        # new checkout.
        item.checkout_intent = work_intent
        item.version += 1
        if item.status in (WorkItemStatus.BACKLOG, WorkItemStatus.READY):
            item.status = WorkItemStatus.IN_PROGRESS
            item.started_at = item.started_at or datetime.now(timezone.utc)

        await session.flush()

        # GH#9532: non-blocking advisory checks — never block or fail the checkout.
        # Similarity runs as a fire-and-forget background task (no row lock held).
        # Comment uses a SAVEPOINT so a flush failure cannot poison the outer txn.
        if work_intent:
            try:
                _schedule_intent_similarity(work_intent, item.title, work_item_id)
            except Exception as _exc:
                logger.debug("checkout: similarity schedule skipped (non-critical): %s", _exc)
            try:
                await _post_checkout_comment(session, item, work_intent, agent_id, service=self)
            except Exception as _exc:
                logger.debug("checkout: comment post skipped (non-critical): %s", _exc)

        return item

    async def release(
        self,
        session: AsyncSession,
        work_item_id: str,
        agent_id: str,
    ) -> LLCWorkItem:
        """Release the checkout lock held by agent_id.

        Raises ValueError if the caller does not hold the lock.
        """
        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")
        if item.assignee_agent_id and str(item.assignee_agent_id) != agent_id:
            raise ValueError(f"Agent {agent_id} does not hold checkout for work item {work_item_id}")
        item.checkout_run_id = None
        item.checkout_locked_at = None
        item.version += 1
        await session.flush()
        return item

    # ------------------------------------------------------------------
    # Human claim / unclaim
    # ------------------------------------------------------------------

    async def claim_human(
        self,
        session: AsyncSession,
        work_item_id: str,
        user_id: str,
        company_id: str,
    ) -> LLCWorkItem:
        """Atomically claim a work item for a human user.

        Redis key stores ``user:{user_id}`` (not bare UUID) so the NX check
        is mutually exclusive with agent checkout which stores a bare UUID.

        Raises CheckoutConflict if the item is already held by anyone else.
        Raises ValueError if the item is not found.
        """
        redis_key = f"llc:checkout:{work_item_id}"
        redis_value = f"user:{user_id}"
        redis = await get_async_redis_client()

        if redis is not None:
            acquired = await redis.set(redis_key, redis_value, nx=True, ex=_CHECKOUT_TTL)
            if not acquired:
                existing = await redis.get(redis_key)
                if existing and existing != redis_value:
                    raise CheckoutConflict(f"Work item {work_item_id} is already claimed (held by {existing})")

        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            if redis is not None:
                await redis.delete(redis_key)
            raise ValueError(f"Work item {work_item_id} not found")

        # DB-level conflict guard — reject if already held by a different user
        if item.assignee_user_id is not None and str(item.assignee_user_id) != user_id:
            if redis is not None:
                await redis.delete(redis_key)
            raise CheckoutConflict(f"Work item {work_item_id} is already claimed by user {item.assignee_user_id}")

        item.assignee_user_id = uuid.UUID(user_id)
        item.assignee_agent_id = None
        item.assignee_type = "user"
        item.checkout_run_id = None
        item.checkout_locked_at = datetime.now(timezone.utc)
        item.version += 1
        if item.status in (WorkItemStatus.BACKLOG, WorkItemStatus.READY):
            item.status = WorkItemStatus.IN_PROGRESS
            item.started_at = item.started_at or datetime.now(timezone.utc)

        await session.flush()

        if self.activity_log:
            try:
                await self.activity_log.record(
                    session,
                    company_id=company_id,
                    actor_id=user_id,
                    event_type=ActivityEventType.WORK_ITEM_ASSIGNED,
                    entity_type="work_item",
                    entity_id=work_item_id,
                    after={"assignee_user_id": user_id, "assignee_type": "user"},
                )
            except Exception:
                logger.warning("Activity log failed for claim_human %s", work_item_id)

        return item

    async def unclaim_human(
        self,
        session: AsyncSession,
        work_item_id: str,
        user_id: str,
        company_id: str,
    ) -> LLCWorkItem:
        """Release a human claim on a work item, returning it to READY.

        Bypasses the state machine (same privilege as checkout → IN_PROGRESS).
        Raises ValueError if the item is not found or the caller does not hold the claim.
        """
        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")
        if item.assignee_user_id is None or str(item.assignee_user_id) != user_id:
            raise ValueError(f"User {user_id} does not hold claim for work item {work_item_id}")

        item.assignee_user_id = None
        item.assignee_type = None
        item.checkout_run_id = None
        item.checkout_locked_at = None
        item.status = WorkItemStatus.READY
        item.version += 1
        await session.flush()

        redis = await get_async_redis_client()
        if redis is not None:
            await redis.delete(f"llc:checkout:{work_item_id}")

        if self.activity_log:
            try:
                await self.activity_log.record(
                    session,
                    company_id=company_id,
                    actor_id=user_id,
                    event_type=ActivityEventType.WORK_ITEM_STATUS_CHANGED,
                    entity_type="work_item",
                    entity_id=work_item_id,
                    before={"assignee_user_id": user_id},
                    after={"assignee_user_id": None, "status": WorkItemStatus.READY.value},
                )
            except Exception:
                logger.warning("Activity log failed for unclaim_human %s", work_item_id)

        return item

    # ------------------------------------------------------------------
    # Co-working (GH#8230)
    # ------------------------------------------------------------------

    async def enable_coworking(
        self,
        session: AsyncSession,
        work_item_id: str,
        co_worker_type: str,
        company_id: str,
        *,
        co_worker_agent_id: Optional[str] = None,
        co_worker_user_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_type: str = "agent",
        caller_role: str = "member",
    ) -> LLCWorkItem:
        """Set co-worker fields and enable co-working mode.

        Requires board or lead permission (caller_role must be owner/admin/lead).
        Primary assignee checkout invariants are not changed.

        Raises CoWorkingPermissionError if caller_role is insufficient.
        Raises ValueError if work_item_id not found or co-worker identity is missing.
        """
        if caller_role not in _COWORKING_ALLOWED_ROLES:
            raise CoWorkingPermissionError(
                f"Role {caller_role!r} does not have permission to manage co-working. "
                f"Required: {sorted(_COWORKING_ALLOWED_ROLES)}"
            )
        co_type = CoWorkerType(co_worker_type)
        if co_type == CoWorkerType.AGENT and not co_worker_agent_id:
            raise ValueError("co_worker_agent_id required when co_worker_type is 'agent'")
        if co_type == CoWorkerType.HUMAN and not co_worker_user_id:
            raise ValueError("co_worker_user_id required when co_worker_type is 'human'")

        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")

        before = {
            "co_worker_type": item.co_worker_type,
            "co_worker_agent_id": str(item.co_worker_agent_id) if item.co_worker_agent_id else None,
            "co_worker_user_id": str(item.co_worker_user_id) if item.co_worker_user_id else None,
            "co_working_enabled": item.co_working_enabled,
        }

        item.co_worker_type = co_type.value
        item.co_worker_agent_id = uuid.UUID(co_worker_agent_id) if co_worker_agent_id else None
        item.co_worker_user_id = uuid.UUID(co_worker_user_id) if co_worker_user_id else None
        item.co_working_enabled = True
        item.version += 1
        await session.flush()

        if self.activity_log:
            try:
                await self.activity_log.record(
                    session,
                    company_id=company_id,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_type=ActivityEventType.WORK_ITEM_COWORKER_SET,
                    entity_type="work_item",
                    entity_id=work_item_id,
                    before=before,
                    after={
                        "co_worker_type": item.co_worker_type,
                        "co_worker_agent_id": str(item.co_worker_agent_id) if item.co_worker_agent_id else None,
                        "co_worker_user_id": str(item.co_worker_user_id) if item.co_worker_user_id else None,
                        "co_working_enabled": True,
                    },
                )
            except Exception:
                logger.warning("Activity log failed for enable_coworking %s", work_item_id)

        return item

    async def disable_coworking(
        self,
        session: AsyncSession,
        work_item_id: str,
        company_id: str,
        *,
        actor_id: Optional[str] = None,
        actor_type: str = "agent",
        caller_role: str = "member",
    ) -> LLCWorkItem:
        """Clear co-worker fields and disable co-working mode.

        Raises CoWorkingPermissionError if caller_role is insufficient.
        Raises ValueError if work_item_id not found.
        """
        if caller_role not in _COWORKING_ALLOWED_ROLES:
            raise CoWorkingPermissionError(
                f"Role {caller_role!r} does not have permission to manage co-working. "
                f"Required: {sorted(_COWORKING_ALLOWED_ROLES)}"
            )

        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")

        before = {
            "co_worker_type": item.co_worker_type,
            "co_worker_agent_id": str(item.co_worker_agent_id) if item.co_worker_agent_id else None,
            "co_worker_user_id": str(item.co_worker_user_id) if item.co_worker_user_id else None,
            "co_working_enabled": item.co_working_enabled,
        }

        item.co_worker_type = None
        item.co_worker_agent_id = None
        item.co_worker_user_id = None
        item.co_working_enabled = False
        item.version += 1
        await session.flush()

        if self.activity_log:
            try:
                await self.activity_log.record(
                    session,
                    company_id=company_id,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    event_type=ActivityEventType.WORK_ITEM_COWORKER_CLEARED,
                    entity_type="work_item",
                    entity_id=work_item_id,
                    before=before,
                    after={"co_working_enabled": False},
                )
            except Exception:
                logger.warning("Activity log failed for disable_coworking %s", work_item_id)

        return item

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    async def transition_status(
        self,
        session: AsyncSession,
        work_item_id: str,
        new_status: WorkItemStatus,
        company_id: Optional[str] = None,
        relation_svc: Optional[Any] = None,
    ) -> LLCWorkItem:
        """Transition a work item to a new status, enforcing the state machine."""
        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")

        current = WorkItemStatus(item.status)
        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise InvalidTransition(
                f"Cannot transition from {current.value!r} to {new_status.value!r}. "
                f"Allowed: {[s.value for s in allowed]}"
            )

        # GH#8252: block BLOCKED→IN_PROGRESS while unresolved blockers remain
        if (
            current == WorkItemStatus.BLOCKED
            and new_status == WorkItemStatus.IN_PROGRESS
            and relation_svc is not None
            and company_id is not None
        ):
            cid = company_id or str(item.company_id)
            if await relation_svc.has_unresolved_blockers(session, work_item_id, cid):
                raise InvalidTransition("Cannot move to in_progress: item has unresolved blocked_by relations")

        item.status = new_status
        now = datetime.now(timezone.utc)
        if new_status == WorkItemStatus.IN_PROGRESS and item.started_at is None:
            item.started_at = now
        elif new_status == WorkItemStatus.DONE:
            item.completed_at = now
            item.checkout_run_id = None
            item.checkout_locked_at = None
        elif new_status == WorkItemStatus.CANCELLED:
            item.cancelled_at = now
        item.version += 1
        await session.flush()

        if new_status == WorkItemStatus.DONE:
            await self._trigger_artifact_ingest(session, item)

        # Release per-task workspace on terminal transitions (MVA-1152)
        if new_status in {WorkItemStatus.DONE, WorkItemStatus.CANCELLED}:
            try:
                from services.task_workspace import release_for_task

                await release_for_task(work_item_id, session)
            except Exception:
                logger.warning(
                    "workspace release skipped for task=%s new_status=%s",
                    work_item_id,
                    new_status.value,
                    exc_info=True,
                )

        return item

    # ------------------------------------------------------------------
    # Gated done transition (GH#8234)
    # ------------------------------------------------------------------

    async def transition_to_done(
        self,
        session: AsyncSession,
        work_item_id: str,
        company_id: str,
        *,
        actor_agent_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
        is_board_override: bool = False,
        review_gate_svc: Optional[Any] = None,
        handoff_svc: Optional[Any] = None,
        reviewer_user_id: Optional[str] = None,
    ) -> "LLCWorkItem":
        """Transition a work item to DONE, enforcing human review gate policy.

        If the gate requires human review and actor is an agent:
        - Blocks the DONE transition.
        - Calls HandoffService.agent_to_human to move item to IN_REVIEW.
        - Returns the item in IN_REVIEW state (not DONE).

        If actor is human (actor_user_id set) or is_board_override is True:
        - Allows DONE transition directly.
        - Board override is logged in the activity log.

        Raises InvalidTransition if the current state does not permit DONE.
        """
        result = await session.execute(
            select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)).with_for_update()
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Work item {work_item_id} not found")

        current = WorkItemStatus(item.status)
        allowed = _ALLOWED_TRANSITIONS.get(current, set())
        if WorkItemStatus.DONE not in allowed:
            raise InvalidTransition(
                f"Cannot transition from {current.value!r} to 'done'. " f"Allowed: {[s.value for s in allowed]}"
            )

        actor_is_agent = actor_agent_id is not None and actor_user_id is None

        if not is_board_override and actor_is_agent and review_gate_svc is not None:
            item_type = WorkItemType(item.type)
            requires, reviewer_role = await review_gate_svc.requires_review(session, company_id, item_type)
            if requires:
                if handoff_svc is not None:
                    return await handoff_svc.agent_to_human(
                        session,
                        work_item_id,
                        company_id,
                        reviewer_user_id=reviewer_user_id,
                        agent_notes=None,
                        actor_agent_id=actor_agent_id,
                    )
                raise InvalidTransition(
                    f"Work item {work_item_id} requires human review before it can be marked done. "
                    "No HandoffService available to initiate handoff."
                )

        now = datetime.now(timezone.utc)
        item.status = WorkItemStatus.DONE
        item.completed_at = now
        item.checkout_run_id = None
        item.checkout_locked_at = None
        item.version += 1
        await session.flush()

        await self._trigger_artifact_ingest(session, item)

        # Release per-task workspace (MVA-1152)
        try:
            from services.task_workspace import release_for_task

            await release_for_task(work_item_id, session)
        except Exception:
            logger.warning("workspace release skipped for task=%s", work_item_id, exc_info=True)

        if self.activity_log:
            try:
                meta: dict = {}
                if is_board_override:
                    meta["board_override"] = True
                    meta["actor_user_id"] = actor_user_id

                await self.activity_log.record(
                    session,
                    company_id=company_id,
                    actor_id=actor_user_id or actor_agent_id or work_item_id,
                    event_type=ActivityEventType.WORK_ITEM_COMPLETED,
                    entity_type="work_item",
                    entity_id=work_item_id,
                    before={"status": current.value},
                    after={"status": WorkItemStatus.DONE.value, **meta},
                )
            except Exception:
                logger.warning("Activity log failed for transition_to_done %s", work_item_id)

        return item

    # ------------------------------------------------------------------
    # Comment helpers
    # ------------------------------------------------------------------

    async def add_comment(
        self,
        session: AsyncSession,
        work_item_id: str,
        company_id: str,
        body: str,
        author_agent_id: Optional[str] = None,
        author_user_id: Optional[str] = None,
    ) -> LLCWorkItemComment:
        comment = LLCWorkItemComment(
            id=uuid.uuid4(),
            company_id=uuid.UUID(company_id),
            work_item_id=uuid.UUID(work_item_id),
            body=body,
            author_agent_id=uuid.UUID(author_agent_id) if author_agent_id else None,
            author_user_id=uuid.UUID(author_user_id) if author_user_id else None,
        )
        session.add(comment)
        await session.flush()
        return comment

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _next_identifier(self, session: AsyncSession, company_id: str) -> str:
        """Generate the next ``<prefix>-<counter>`` identifier for this company.

        Uses PostgreSQL advisory lock + UPDATE RETURNING on ``llc_companies`` to
        ensure uniqueness under concurrent inserts. Falls back to a random
        identifier in test environments that lack the ``llc_companies`` table.
        """
        try:
            row = await session.execute(
                text("""
                    UPDATE llc_companies
                       SET issue_counter = issue_counter + 1
                     WHERE id = :company_id
                    RETURNING issue_prefix, issue_counter
                    """),
                {"company_id": company_id},
            )
            rec = row.fetchone()
            if rec:
                return f"{rec.issue_prefix}-{rec.issue_counter}"
        except Exception as exc:
            if isinstance(exc, (ProgrammingError, OperationalError)):
                logger.debug("llc_companies table not available — using UUID identifier fallback")
            else:
                logger.warning(
                    "Unexpected error generating identifier for company %s — using UUID fallback",
                    company_id,
                    exc_info=True,
                )
        return f"WI-{uuid.uuid4().hex[:8].upper()}"

    async def _trigger_artifact_ingest(
        self,
        session: AsyncSession,
        item: LLCWorkItem,
    ) -> None:
        """Non-fatally call ArtifactIngestor for all pending products on this item."""
        try:
            from ..kb.artifact_ingestor import ArtifactIngestor

            ingestor = ArtifactIngestor()
            await ingestor.ingest_all_pending(
                session,
                work_item_id=str(item.id),
                project_id=str(item.project_id) if item.project_id else None,
                work_item_identifier=item.identifier,
                company_id=str(item.company_id),
                completed_at=item.completed_at,
            )
        except Exception:
            logger.warning(
                "ArtifactIngestor failed for work item %s — transition still succeeds",
                item.id,
                exc_info=True,
            )
