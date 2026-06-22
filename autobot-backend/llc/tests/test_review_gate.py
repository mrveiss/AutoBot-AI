# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for LLC human review gate — GH#8234.

Tests cover:
- ReviewGatePolicyService CRUD (create, get, list, update, delete)
- ReviewGatePolicyService.seed_defaults (bug → requires_human_review=True)
- ReviewGatePolicyService.requires_review
- WorkItemService.transition_to_done (no gate, gate blocks, gate passes, board override)
- HandoffService stub (agent_to_human transitions to IN_REVIEW)
- API routes (via FastAPI TestClient + mock service)
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import WorkItemStatus, WorkItemType
from llc.models.review_gate import LLCReviewGatePolicy
from llc.services.handoff import HandoffError, HandoffNotAllowed, HandoffService
from llc.services.review_gate import (
    ReviewGatePolicyConflictError,
    ReviewGatePolicyNotFoundError,
    ReviewGatePolicyService,
)
from llc.services.work_item_service import InvalidTransition, WorkItemService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_policy(
    *,
    policy_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    item_type: WorkItemType = WorkItemType.BUG,
    requires_human_review: bool = True,
    reviewer_role: str | None = None,
) -> MagicMock:
    p = MagicMock(spec=LLCReviewGatePolicy)
    p.id = policy_id or uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.item_type = item_type
    p.requires_human_review = requires_human_review
    p.reviewer_role = reviewer_role
    p.created_at = datetime.now(timezone.utc)
    p.updated_at = datetime.now(timezone.utc)
    return p


def _make_work_item(
    *,
    work_item_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    item_type: WorkItemType = WorkItemType.BUG,
    status: WorkItemStatus = WorkItemStatus.IN_PROGRESS,
) -> MagicMock:
    from llc.models.work_item import LLCWorkItem

    wi = MagicMock(spec=LLCWorkItem)
    wi.id = work_item_id or uuid.uuid4()
    wi.company_id = company_id or uuid.uuid4()
    wi.type = item_type.value
    wi.status = status.value
    wi.checkout_run_id = "some-run"
    wi.checkout_locked_at = datetime.now(timezone.utc)
    wi.completed_at = None
    wi.cancelled_at = None
    wi.started_at = None
    wi.version = 1
    wi.title = "Bug: crash on startup"
    return wi


def _make_session(scalar_result: Any = None, scalars_result: list | None = None) -> MagicMock:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_result
    if scalars_result is not None:
        scalars_obj = MagicMock()
        scalars_obj.all.return_value = scalars_result
        execute_result.scalars.return_value = scalars_obj
    session.execute = AsyncMock(return_value=execute_result)
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# ReviewGatePolicyService — CRUD
# ---------------------------------------------------------------------------


class TestReviewGatePolicyServiceCreate:
    @pytest.mark.asyncio
    async def test_review_gate_create_policy(self) -> None:
        """create_policy adds and flushes a new policy."""
        svc = ReviewGatePolicyService()
        session = _make_session()
        company_id = str(uuid.uuid4())

        result = await svc.create_policy(
            session,
            company_id,
            WorkItemType.BUG,
            requires_human_review=True,
            reviewer_role="admin",
        )

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert result.requires_human_review is True
        assert result.reviewer_role == "admin"

    @pytest.mark.asyncio
    async def test_review_gate_create_conflict_raises(self) -> None:
        """create_policy raises ReviewGatePolicyConflictError on IntegrityError."""
        from sqlalchemy.exc import IntegrityError

        svc = ReviewGatePolicyService()
        session = _make_session()
        session.flush = AsyncMock(side_effect=IntegrityError("dup", None, None))
        company_id = str(uuid.uuid4())

        with pytest.raises(ReviewGatePolicyConflictError):
            await svc.create_policy(session, company_id, WorkItemType.TASK)


class TestReviewGatePolicyServiceGet:
    @pytest.mark.asyncio
    async def test_review_gate_get_policy_found(self) -> None:
        policy = _make_policy(item_type=WorkItemType.BUG)
        session = _make_session(scalar_result=policy)
        svc = ReviewGatePolicyService()

        result = await svc.get_policy(session, str(policy.company_id), WorkItemType.BUG)

        assert result is policy

    @pytest.mark.asyncio
    async def test_review_gate_get_policy_not_found(self) -> None:
        session = _make_session(scalar_result=None)
        svc = ReviewGatePolicyService()

        result = await svc.get_policy(session, str(uuid.uuid4()), WorkItemType.TASK)

        assert result is None

    @pytest.mark.asyncio
    async def test_review_gate_list_policies(self) -> None:
        policies = [_make_policy(), _make_policy(item_type=WorkItemType.TASK, requires_human_review=False)]
        session = _make_session(scalars_result=policies)
        svc = ReviewGatePolicyService()

        result = await svc.list_policies(session, str(uuid.uuid4()))

        assert len(result) == 2


class TestReviewGatePolicyServiceUpdate:
    @pytest.mark.asyncio
    async def test_review_gate_update_policy(self) -> None:
        policy = _make_policy(requires_human_review=False)
        session = _make_session(scalar_result=policy)
        svc = ReviewGatePolicyService()

        updated = await svc.update_policy(session, str(policy.id), requires_human_review=True)

        assert updated.requires_human_review is True
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_review_gate_update_not_found_raises(self) -> None:
        session = _make_session(scalar_result=None)
        svc = ReviewGatePolicyService()

        with pytest.raises(ReviewGatePolicyNotFoundError):
            await svc.update_policy(session, str(uuid.uuid4()), requires_human_review=True)


class TestReviewGatePolicyServiceDelete:
    @pytest.mark.asyncio
    async def test_review_gate_delete_policy_found(self) -> None:
        policy_id = uuid.uuid4()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = policy_id
        session = AsyncMock()
        session.execute = AsyncMock(return_value=execute_result)
        session.flush = AsyncMock()
        svc = ReviewGatePolicyService()

        deleted = await svc.delete_policy(session, str(policy_id))

        assert deleted is True

    @pytest.mark.asyncio
    async def test_review_gate_delete_policy_not_found(self) -> None:
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session = AsyncMock()
        session.execute = AsyncMock(return_value=execute_result)
        session.flush = AsyncMock()
        svc = ReviewGatePolicyService()

        deleted = await svc.delete_policy(session, str(uuid.uuid4()))

        assert deleted is False


# ---------------------------------------------------------------------------
# ReviewGatePolicyService — seed_defaults
# ---------------------------------------------------------------------------


class TestReviewGateSeedDefaults:
    @pytest.mark.asyncio
    async def test_review_gate_seed_defaults_creates_all_types(self) -> None:
        """seed_defaults creates one policy per WorkItemType."""
        svc = ReviewGatePolicyService()
        session = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        # Simulate no existing policies
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)
        company_id = str(uuid.uuid4())

        created = await svc.seed_defaults(session, company_id)

        assert len(created) == len(WorkItemType)

    @pytest.mark.asyncio
    async def test_review_gate_seed_defaults_bug_requires_review(self) -> None:
        """seed_defaults sets requires_human_review=True for bug type."""
        svc = ReviewGatePolicyService()
        session = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)
        company_id = str(uuid.uuid4())

        created = await svc.seed_defaults(session, company_id)

        bug_policy = next(p for p in created if p.item_type == WorkItemType.BUG)
        assert bug_policy.requires_human_review is True
        other_policies = [p for p in created if p.item_type != WorkItemType.BUG]
        assert all(not p.requires_human_review for p in other_policies)

    @pytest.mark.asyncio
    async def test_review_gate_seed_defaults_idempotent(self) -> None:
        """seed_defaults skips types that already have a policy."""
        svc = ReviewGatePolicyService()
        existing = _make_policy()
        session = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=execute_result)

        created = await svc.seed_defaults(session, str(uuid.uuid4()))

        assert len(created) == 0
        session.add.assert_not_called()


# ---------------------------------------------------------------------------
# ReviewGatePolicyService — requires_review
# ---------------------------------------------------------------------------


class TestReviewGateRequiresReview:
    @pytest.mark.asyncio
    async def test_review_gate_requires_review_true(self) -> None:
        policy = _make_policy(requires_human_review=True, reviewer_role="admin")
        session = _make_session(scalar_result=policy)
        svc = ReviewGatePolicyService()

        req, role = await svc.requires_review(session, str(uuid.uuid4()), WorkItemType.BUG)

        assert req is True
        assert role == "admin"

    @pytest.mark.asyncio
    async def test_review_gate_requires_review_false_no_policy(self) -> None:
        session = _make_session(scalar_result=None)
        svc = ReviewGatePolicyService()

        req, role = await svc.requires_review(session, str(uuid.uuid4()), WorkItemType.TASK)

        assert req is False
        assert role is None


# ---------------------------------------------------------------------------
# WorkItemService.transition_to_done
# ---------------------------------------------------------------------------


class TestTransitionToDone:
    def _make_wi_session(self, item: Any) -> MagicMock:
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = item
        session.execute = AsyncMock(return_value=execute_result)
        session.flush = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_review_gate_transition_no_gate(self) -> None:
        """transition_to_done with no review_gate_svc completes normally for human actor."""
        wi = _make_work_item(status=WorkItemStatus.IN_PROGRESS)
        session = self._make_wi_session(wi)
        svc = WorkItemService()
        company_id = str(uuid.uuid4())

        result = await svc.transition_to_done(session, str(wi.id), company_id, actor_user_id=str(uuid.uuid4()))

        assert result.status == WorkItemStatus.DONE
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_review_gate_transition_agent_gate_blocks_and_hands_off(self) -> None:
        """Agent actor with review gate triggers handoff, returns IN_REVIEW item."""
        wi = _make_work_item(status=WorkItemStatus.IN_PROGRESS)
        session = self._make_wi_session(wi)
        company_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())

        gate_svc = AsyncMock(spec=ReviewGatePolicyService)
        gate_svc.requires_review = AsyncMock(return_value=(True, "admin"))

        in_review_wi = _make_work_item(status=WorkItemStatus.IN_REVIEW)
        handoff_svc = AsyncMock(spec=HandoffService)
        handoff_svc.agent_to_human = AsyncMock(return_value=in_review_wi)

        svc = WorkItemService()
        result = await svc.transition_to_done(
            session,
            str(wi.id),
            company_id,
            actor_agent_id=agent_id,
            review_gate_svc=gate_svc,
            handoff_svc=handoff_svc,
        )

        handoff_svc.agent_to_human.assert_awaited_once()
        assert result.status == WorkItemStatus.IN_REVIEW

    @pytest.mark.asyncio
    async def test_review_gate_transition_agent_no_gate_required(self) -> None:
        """Agent actor when gate policy says no review — transitions to done."""
        wi = _make_work_item(status=WorkItemStatus.IN_PROGRESS)
        session = self._make_wi_session(wi)
        company_id = str(uuid.uuid4())

        gate_svc = AsyncMock(spec=ReviewGatePolicyService)
        gate_svc.requires_review = AsyncMock(return_value=(False, None))

        svc = WorkItemService()
        result = await svc.transition_to_done(
            session,
            str(wi.id),
            company_id,
            actor_agent_id=str(uuid.uuid4()),
            review_gate_svc=gate_svc,
        )

        assert result.status == WorkItemStatus.DONE

    @pytest.mark.asyncio
    async def test_review_gate_board_override_bypasses_gate(self) -> None:
        """Board override transitions to done regardless of gate policy."""
        wi = _make_work_item(status=WorkItemStatus.IN_REVIEW)
        session = self._make_wi_session(wi)
        company_id = str(uuid.uuid4())

        gate_svc = AsyncMock(spec=ReviewGatePolicyService)
        gate_svc.requires_review = AsyncMock(return_value=(True, "admin"))

        svc = WorkItemService()
        result = await svc.transition_to_done(
            session,
            str(wi.id),
            company_id,
            actor_user_id=str(uuid.uuid4()),
            is_board_override=True,
            review_gate_svc=gate_svc,
        )

        gate_svc.requires_review.assert_not_awaited()
        assert result.status == WorkItemStatus.DONE

    @pytest.mark.asyncio
    async def test_review_gate_transition_invalid_state_raises(self) -> None:
        """transition_to_done from DONE raises InvalidTransition."""
        wi = _make_work_item(status=WorkItemStatus.DONE)
        session = self._make_wi_session(wi)
        svc = WorkItemService()

        with pytest.raises(InvalidTransition):
            await svc.transition_to_done(session, str(wi.id), str(uuid.uuid4()), actor_user_id=str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_review_gate_transition_not_found_raises(self) -> None:
        session = self._make_wi_session(None)
        svc = WorkItemService()

        with pytest.raises(ValueError, match="not found"):
            await svc.transition_to_done(session, str(uuid.uuid4()), str(uuid.uuid4()), actor_user_id=str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_review_gate_board_override_logs_override(self) -> None:
        """Board override records board_override=True in the activity log."""
        wi = _make_work_item(status=WorkItemStatus.IN_PROGRESS)
        session = self._make_wi_session(wi)
        company_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        log_svc = AsyncMock()
        log_svc.record = AsyncMock()

        svc = WorkItemService(activity_log=log_svc)
        await svc.transition_to_done(
            session,
            str(wi.id),
            company_id,
            actor_user_id=user_id,
            is_board_override=True,
        )

        log_svc.record.assert_awaited_once()
        call_kwargs = log_svc.record.call_args.kwargs
        assert call_kwargs["after"]["board_override"] is True


# ---------------------------------------------------------------------------
# HandoffService stub
# ---------------------------------------------------------------------------


class TestHandoffService:
    @pytest.mark.asyncio
    async def test_review_gate_handoff_agent_to_human_transitions_to_in_review(self) -> None:
        """agent_to_human sets status to IN_REVIEW and clears checkout lock."""
        agent_id = str(uuid.uuid4())
        wi = _make_work_item(status=WorkItemStatus.IN_PROGRESS)
        wi.assignee_agent_id = uuid.UUID(agent_id)  # the agent holds the checkout
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = wi
        session.execute = AsyncMock(return_value=execute_result)
        session.flush = AsyncMock()

        with patch("llc.services.handoff.get_async_redis_client", new_callable=AsyncMock, return_value=None):
            svc = HandoffService()
            result = await svc.agent_to_human(
                session,
                str(wi.id),
                agent_id,
                reviewer_user_id=str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
                agent_notes="Ready for review",
            )

        assert result.status == WorkItemStatus.IN_REVIEW.value
        assert result.checkout_run_id is None
        session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_review_gate_handoff_not_found_raises(self) -> None:
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=execute_result)

        svc = HandoffService()
        # Missing work item now raises ValueError (not HandoffError).
        with pytest.raises(ValueError, match="not found"):
            await svc.agent_to_human(
                session, str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
            )

    @pytest.mark.asyncio
    async def test_review_gate_handoff_unauthorized_agent_raises(self) -> None:
        """An agent that does not hold the checkout cannot hand off (#10388)."""
        wi = _make_work_item(status=WorkItemStatus.IN_PROGRESS)
        wi.assignee_agent_id = uuid.uuid4()  # held by a DIFFERENT agent
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = wi
        session.execute = AsyncMock(return_value=execute_result)

        svc = HandoffService()
        with pytest.raises(HandoffNotAllowed, match="does not hold checkout"):
            await svc.agent_to_human(session, str(wi.id), str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# ReviewGatePolicyService — additional edge cases
# ---------------------------------------------------------------------------


class TestReviewGateEdgeCases:
    @pytest.mark.asyncio
    async def test_review_gate_requires_review_false_policy(self) -> None:
        """Policy with requires_human_review=False returns (False, None)."""
        policy = _make_policy(requires_human_review=False, reviewer_role=None)
        session = _make_session(scalar_result=policy)
        svc = ReviewGatePolicyService()

        req, role = await svc.requires_review(session, str(uuid.uuid4()), WorkItemType.TASK)

        assert req is False
        assert role is None

    @pytest.mark.asyncio
    async def test_review_gate_update_reviewer_role(self) -> None:
        policy = _make_policy(reviewer_role=None)
        session = _make_session(scalar_result=policy)
        svc = ReviewGatePolicyService()

        updated = await svc.update_policy(session, str(policy.id), reviewer_role="owner")

        assert updated.reviewer_role == "owner"

    @pytest.mark.asyncio
    async def test_review_gate_transition_agent_gate_no_handoff_raises(self) -> None:
        """Agent actor, gate required, no HandoffService — raises InvalidTransition."""
        wi = _make_work_item(status=WorkItemStatus.IN_PROGRESS)
        session = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = wi
        session.execute = AsyncMock(return_value=execute_result)
        session.flush = AsyncMock()

        gate_svc = AsyncMock(spec=ReviewGatePolicyService)
        gate_svc.requires_review = AsyncMock(return_value=(True, "admin"))

        svc = WorkItemService()
        with pytest.raises(InvalidTransition, match="HandoffService"):
            await svc.transition_to_done(
                session,
                str(wi.id),
                str(uuid.uuid4()),
                actor_agent_id=str(uuid.uuid4()),
                review_gate_svc=gate_svc,
                handoff_svc=None,
            )
