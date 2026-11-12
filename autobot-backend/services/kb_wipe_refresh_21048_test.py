# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Re-proposing a pending knowledge wipe is recorded, keeps the requester and counts the refresher (#21048).

Fakes only: no database is touched.
"""

import types
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.approval_four_eyes import FourEyesError
from services import kb_wipe_action as action
from services.approval_execution import set_verified_decider


def _pending(requester: str, channel: str):
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        requested_by_agent=f"kb-wipe:{requester}",
        context={
            "action": action.ACTION,
            "requested_by": requester,
            "channel": channel,
            "plan": {"total_keys": 5, "total_vectors": 2},
        },
    )


def _session(pending):
    found = MagicMock()
    found.scalars.return_value.first.return_value = pending
    return MagicMock(execute=AsyncMock(return_value=found), commit=AsyncMock(), add=MagicMock())


def _admins(*ids):
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(ids)
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_a_refresh_is_recorded_in_a_comment_and_a_durable_audit_entry_naming_who_and_what_changed(monkeypatch):
    audit = AsyncMock(return_value=True)
    monkeypatch.setattr(action, "audit_log", audit)
    requester, refresher = str(uuid.uuid4()), str(uuid.uuid4())
    pending = _pending(requester, action.CHANNEL_API)
    session = _session(pending)

    await action.propose_kb_wipe(session, refresher, {"total_keys": 9, "total_vectors": 2})

    kwargs = audit.await_args.kwargs
    assert kwargs["durable"] is True and kwargs["user_id"] == refresher
    assert kwargs["details"]["phase"] == "plan_refresh" and kwargs["details"]["refreshed_by"] == refresher
    assert kwargs["details"]["counts"] == {"total_keys": [5, 9], "total_vectors": [2, 2]}
    comment = session.add.call_args.args[0]
    assert comment.author == "system" and refresher in comment.body and "5" in comment.body and "9" in comment.body
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_a_refresh_keeps_the_original_requester_and_channel(monkeypatch):
    monkeypatch.setattr(action, "audit_log", AsyncMock(return_value=True))
    pending = _pending("operator", action.CHANNEL_OPERATOR)
    refresher = str(uuid.uuid4())
    await action.propose_kb_wipe(_session(pending), refresher, {"total_keys": 1, "total_vectors": 1})
    assert pending.requested_by_agent == "kb-wipe:operator"
    assert pending.context["requested_by"] == "operator" and pending.context["channel"] == action.CHANNEL_OPERATOR
    assert pending.context["refreshed_by"] == [refresher]


@pytest.mark.asyncio
async def test_a_refresh_whose_audit_entry_is_lost_leaves_the_plan_unchanged(monkeypatch):
    monkeypatch.setattr(action, "audit_log", AsyncMock(return_value=False))
    pending = _pending(str(uuid.uuid4()), action.CHANNEL_API)
    session = _session(pending)
    with pytest.raises(RuntimeError, match="plan unchanged"):
        await action.propose_kb_wipe(session, str(uuid.uuid4()), {"total_keys": 9})
    assert pending.context["plan"] == {"total_keys": 5, "total_vectors": 2} and "refreshed_by" not in pending.context
    session.commit.assert_not_awaited()


def test_only_the_plan_and_the_refresher_list_are_exempt_from_the_resubmit_freeze():
    context = {"action": action.ACTION, "channel": "api", "plan": {}, "refreshed_by": ["x"], "databases": ["knowledge"]}
    assert action._reviewed_fields(context) == {"action": action.ACTION, "channel": "api", "databases": ["knowledge"]}


@pytest.mark.asyncio
async def test_an_admin_who_refreshed_an_operator_proposal_cannot_approve_it_unflagged_with_a_second_admin(monkeypatch):
    monkeypatch.setattr(action, "audit_log", AsyncMock(return_value=True))
    me, other = uuid.uuid4(), uuid.uuid4()
    pending = _pending("operator", action.CHANNEL_OPERATOR)
    await action.propose_kb_wipe(_session(pending), str(me), {"total_keys": 1})
    set_verified_decider(pending, me)
    with pytest.raises(FourEyesError):
        await action._review_kb_wipe(pending, _admins(me, other))
    set_verified_decider(pending, other)
    assert await action._review_kb_wipe(pending, _admins(me, other)) is False
    set_verified_decider(pending, me)
    assert await action._review_kb_wipe(pending, _admins(me)) is True  # the only admin: flagged, not refused


@pytest.mark.asyncio
async def test_a_second_admin_who_refreshed_an_api_proposal_cannot_approve_it(monkeypatch):
    monkeypatch.setattr(action, "audit_log", AsyncMock(return_value=True))
    first, second = uuid.uuid4(), uuid.uuid4()
    pending = _pending(str(first), action.CHANNEL_API)
    await action.propose_kb_wipe(_session(pending), str(second), {"total_keys": 1})
    set_verified_decider(pending, second)
    with pytest.raises(FourEyesError):
        await action._review_kb_wipe(pending, _admins(first, second, uuid.uuid4()))


def test_the_description_says_the_wipe_is_platform_wide():
    assert "Platform-wide" in action.PROPOSAL_DESCRIPTION and "every organisation" in action.PROPOSAL_DESCRIPTION
    assert action.PLATFORM_WIDE_NOTE in action.PROPOSAL_DESCRIPTION
