# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A hire or a budget override is approved by someone other than the one who asked, unless they are the only admin (#8214, #18430)."""

# flake8: noqa: F811 -- fixtures imported from the support module are re-bound as parameters
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql

from llc.models.budget import LLCAgentBudget
from llc.models.enums import ApprovalStatus, ApprovalType
from llc.services.approval import ApprovalHookError, ApprovalService
from llc.services.authz import active_admin_ids
from llc.tests.approval_enforcement_support_test import _edges  # noqa: F401 -- autouse fixture
from llc.tests.approval_enforcement_support_test import activity  # noqa: F401 -- fixture
from llc.tests.approval_enforcement_support_test import session_factory  # noqa: F401 -- fixture
from llc.tests.approval_enforcement_support_test import _ORG, _board_app, _budget, _member, _post, _rows
from models.agent_org import AgentOrgNode
from models.approval import Approval
from testkit.fake_async_session import FakeAsyncSession
from user_management.models.user import User

ASKER = uuid.UUID("22222222-2222-2222-2222-222222222222")
OTHER = uuid.UUID("33333333-3333-3333-3333-333333333333")
_HIRE = {
    "agent_id": "newbie",
    "agent_name": "Newbie",
    "org_role": "worker",
    "adapter_config": {},
    "model": "m",
    "instructions_file_path": "/x",
}
_RAISE = {"agent_id": "a1", "budget_limit": "50"}
_KINDS = [(ApprovalType.HIRE, _HIRE), (ApprovalType.BUDGET_OVERRIDE, _RAISE)]


async def _ask(session_factory, gate, payload, requester):  # noqa: ANN001, ANN202
    async with session_factory() as session:
        approval = await ApprovalService().request_approval(
            session, company_id=_ORG, gate_type=gate, payload=payload, requested_by=str(requester)
        )
        await session.commit()
    return approval.id


async def _decide_as(session_factory, approval_id, decision, decider):  # noqa: ANN001, ANN202
    async with session_factory() as session:
        try:
            approval = await ApprovalService().decide(
                session, approval_id=approval_id, decision=decision, decided_by=decider
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return approval


async def _two_admins(session_factory) -> None:  # noqa: ANN001
    await _budget(session_factory, "10")
    await _member(session_factory, ASKER, "admin")
    await _member(session_factory, OTHER, "owner")


async def _applied(session_factory, gate) -> bool:  # noqa: ANN001
    if gate == ApprovalType.HIRE:
        return any(n.agent_id == "newbie" for n in await _rows(session_factory, AgentOrgNode))
    return Decimal(str((await _rows(session_factory, LLCAgentBudget))[0].budget_limit)) == Decimal("50")


async def _deactivated_user(session_factory, user_id) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(User(id=user_id, org_id=_ORG, email=f"{user_id}@e.test", username=str(user_id), is_active=False))
        await session.commit()


def _approved_rows(activity):  # noqa: ANN001, ANN202
    return [kw["after"] for event, kw in activity.rows if event == "approval.approved"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("gate", "payload"), _KINDS)
async def test_the_requester_cannot_approve_with_two_admins_and_it_stays_pending(
    session_factory, activity, gate, payload  # noqa: ANN001
) -> None:
    await _two_admins(session_factory)
    aid = await _ask(session_factory, gate, payload, ASKER)
    with pytest.raises(ApprovalHookError, match="different owner or admin"):
        await _decide_as(session_factory, aid, ApprovalStatus.APPROVED, ASKER)
    assert [a.status for a in await _rows(session_factory, Approval)] == [ApprovalStatus.PENDING.value]
    assert not await _applied(session_factory, gate)
    assert _approved_rows(activity) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("gate", "payload"), _KINDS)
async def test_another_admin_approves_and_it_is_not_flagged(
    session_factory, activity, gate, payload
) -> None:  # noqa: ANN001
    await _two_admins(session_factory)
    aid = await _ask(session_factory, gate, payload, ASKER)
    await _decide_as(session_factory, aid, ApprovalStatus.APPROVED, OTHER)
    assert await _applied(session_factory, gate)
    assert [a["self_approval"] for a in _approved_rows(activity)] == [False]


@pytest.mark.asyncio
@pytest.mark.parametrize(("gate", "payload"), _KINDS)
async def test_the_only_admin_may_approve_their_own_request_and_it_is_flagged(
    session_factory, activity, gate, payload  # noqa: ANN001
) -> None:
    await _budget(session_factory, "10")
    await _member(session_factory, ASKER, "admin")
    aid = await _ask(session_factory, gate, payload, ASKER)
    await _decide_as(session_factory, aid, ApprovalStatus.APPROVED, ASKER)
    assert await _applied(session_factory, gate)
    assert [a["self_approval"] for a in _approved_rows(activity)] == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize(("gate", "payload"), _KINDS)
async def test_an_outsider_cannot_approve_their_own_request_beside_one_real_admin(
    session_factory, activity, gate, payload  # noqa: ANN001
) -> None:
    """A platform admin holds no membership, so they are not the company's single owner or admin."""
    await _budget(session_factory, "10")
    await _member(session_factory, OTHER, "owner")
    aid = await _ask(session_factory, gate, payload, ASKER)
    with pytest.raises(ApprovalHookError):
        await _decide_as(session_factory, aid, ApprovalStatus.APPROVED, ASKER)
    assert not await _applied(session_factory, gate)


@pytest.mark.asyncio
@pytest.mark.parametrize(("gate", "payload"), _KINDS)
async def test_a_deactivated_admin_does_not_count_so_the_active_one_may_self_approve(
    session_factory, activity, gate, payload  # noqa: ANN001
) -> None:
    await _two_admins(session_factory)
    await _deactivated_user(session_factory, OTHER)
    aid = await _ask(session_factory, gate, payload, ASKER)
    await _decide_as(session_factory, aid, ApprovalStatus.APPROVED, ASKER)
    assert await _applied(session_factory, gate)
    assert [a["self_approval"] for a in _approved_rows(activity)] == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize(("gate", "payload"), _KINDS)
async def test_the_requester_may_reject_their_own_request_with_two_admins(
    session_factory, activity, gate, payload  # noqa: ANN001
) -> None:
    await _two_admins(session_factory)
    aid = await _ask(session_factory, gate, payload, ASKER)
    approval = await _decide_as(session_factory, aid, ApprovalStatus.REJECTED, ASKER)
    assert approval.status == ApprovalStatus.REJECTED.value
    assert not await _applied(session_factory, gate)


@pytest.mark.asyncio
@pytest.mark.parametrize("requested_by", ["agent-x", "chat_agent", ""])
async def test_a_requester_that_names_no_person_does_not_strand_the_request(
    session_factory, activity, requested_by  # noqa: ANN001
) -> None:
    await _two_admins(session_factory)
    aid = await _ask(session_factory, ApprovalType.BUDGET_OVERRIDE, _RAISE, requested_by)
    await _decide_as(session_factory, aid, ApprovalStatus.APPROVED, ASKER)
    assert await _applied(session_factory, ApprovalType.BUDGET_OVERRIDE)
    assert [a["self_approval"] for a in _approved_rows(activity)] == [False]


@pytest.mark.asyncio
async def test_a_forged_requester_in_the_body_is_replaced_by_the_verified_caller(
    session_factory,
) -> None:  # noqa: ANN001
    await _two_admins(session_factory)
    body = {"company_id": str(_ORG), "type": "budget_override", "requested_by_agent_id": str(OTHER), "payload": _RAISE}
    resp = await _post(_board_app(session_factory, user_id=ASKER), "/api/llc/approvals", body)
    assert resp.status_code == 201
    assert resp.json()["requested_by_agent_id"] == str(ASKER)
    with pytest.raises(ApprovalHookError, match="different owner or admin"):
        await _decide_as(session_factory, uuid.UUID(resp.json()["id"]), ApprovalStatus.APPROVED, ASKER)
    assert [a.status for a in await _rows(session_factory, Approval)] == [ApprovalStatus.PENDING.value]


@pytest.mark.asyncio
async def test_the_admin_read_locks_the_memberships_until_the_decision_commits() -> None:
    """SQLite ignores row locks, so this reads the statement: a plain select let two decisions both pass."""
    session = FakeAsyncSession(results=[[]])
    await active_admin_ids(session, _ORG)
    statement = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE OF llc_company_memberships" in statement
