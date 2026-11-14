# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The review-gated done path hands off through the REAL ``HandoffService.agent_to_human`` (#21457).

A mock that accepts any arguments hid a call whose arguments did not match the function it calls. These tests
use a real ``HandoffService`` and stub only its outward effects (audit row, notification, Redis, brief task),
so a mismatch of the call against the declared signature raises ``TypeError`` and fails the test.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem
from llc.services.handoff import HandoffService
from llc.services.review_gate import ReviewGatePolicyService
from llc.services.work_item_service import InvalidTransition, WorkItemService

_AGENT = "b3c1e7a2-9d4f-4c68-a1f5-2e8d6b0c7a43"
_REVIEWER = "5799065e-4061-4af8-bee7-64e65f1a2b91"
_COMPANY = "0f1d7a52-3c88-4b6e-9a0d-61c2b7e4f905"


def _item() -> MagicMock:
    item = MagicMock(spec=LLCWorkItem)
    item.id = uuid.UUID("9c2e4b1a-7d35-4f08-8e6a-3b1d5c7a9e02")
    item.type = WorkItemType.BUG.value
    item.status = WorkItemStatus.IN_PROGRESS.value
    item.assignee_agent_id = uuid.UUID(_AGENT)
    item.project_id = None
    item.title, item.description = "A bug", ""
    item.version = 1
    item.checkout_locked_at = datetime.now(timezone.utc)
    return item


def _session(item: MagicMock) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=item)))
    session.flush = AsyncMock()
    return session


def _real_handoff() -> HandoffService:
    svc = HandoffService()
    svc._record_a2h_activity = AsyncMock()
    svc._publish_a2h_notification = AsyncMock()
    svc._generate_and_update_brief_async = AsyncMock()
    svc._generate_brief = MagicMock(return_value={})
    return svc


def _gate() -> AsyncMock:
    gate = AsyncMock(spec=ReviewGatePolicyService)
    gate.requires_review = AsyncMock(return_value=(True, "admin"))
    return gate


async def _done(item: MagicMock, handoff: HandoffService, reviewer):
    with patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=None)):
        return await WorkItemService().transition_to_done(
            _session(item),
            str(item.id),
            _COMPANY,
            actor_agent_id=_AGENT,
            review_gate_svc=_gate(),
            handoff_svc=handoff,
            reviewer_user_id=reviewer,
        )


async def test_gated_done_hands_the_item_to_the_reviewer_through_the_real_handoff_service():
    """Before: TypeError (unexpected keyword ``actor_agent_id``, ``agent_id`` missing). After: the item is in review."""
    item = _item()
    result = await _done(item, _real_handoff(), _REVIEWER)
    assert result.status == WorkItemStatus.IN_REVIEW
    assert result.reviewer_user_id == uuid.UUID(_REVIEWER)
    assert result.assignee_agent_id is None


async def test_gated_done_names_the_company_and_agent_to_the_audit_row():
    """The company and the agent reach the declared parameters, not each other's."""
    handoff = _real_handoff()
    await _done(_item(), handoff, _REVIEWER)
    args = handoff._record_a2h_activity.await_args.args
    assert args[1:4] == (_COMPANY, _AGENT, _REVIEWER)


@pytest.mark.parametrize("reviewer", [None, ""])
async def test_gated_done_without_a_reviewer_is_refused_and_the_item_is_left_alone(reviewer):
    item = _item()
    handoff = _real_handoff()
    with pytest.raises(InvalidTransition, match="reviewer is required"):
        await _done(item, handoff, reviewer)
    assert item.status == WorkItemStatus.IN_PROGRESS.value
    handoff._record_a2h_activity.assert_not_awaited()
