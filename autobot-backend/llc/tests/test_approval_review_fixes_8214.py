# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Review findings on the #8214 approval enforcement.

* a decision re-reads the row it locks, so a stale ``pending`` copy cannot overwrite a committed decision;
* only a company owner/admin changes ``require_approval_for_hires``;
* a hire's ``reports_to`` must be an agent of the same company;
* the sprint close is attributed to the authenticated caller, not to the request body.
"""

# flake8: noqa: F811 -- fixtures imported from the support module are re-bound as parameters
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from llc.api import sprints
from llc.models.company import CompanyCreate, CompanyUpdate
from llc.models.enums import ApprovalStatus, MembershipRole
from llc.services.approval import ApprovalService, ApprovalStateError
from llc.services.authz import NotAuthorisedError
from llc.services.company import CompanyService
from llc.services.membership_service import MembershipService
from llc.tests import test_llc_org_chart as _org_chart_harness
from llc.tests.approval_enforcement_support_test import _edges  # noqa: F401 -- autouse fixture
from llc.tests.approval_enforcement_support_test import activity  # noqa: F401 -- fixture
from llc.tests.approval_enforcement_support_test import _BOARD, _ORG, _app, _decide, _hire, _rows
from llc.tests.approval_enforcement_support_test import session_factory as approval_session_factory  # noqa: F401
from models.agent_org import AgentOrgNode, OrgRole
from models.approval import Approval
from user_management.models.organization import Organization
from user_management.services import TenantContext

engine = _org_chart_harness.engine
session_factory = _org_chart_harness.session_factory

# --------------------------------------------------------------------------- stale locked read


@pytest.mark.asyncio
async def test_a_decider_holding_a_stale_pending_copy_cannot_overwrite_a_committed_reject(
    approval_session_factory, _edges  # noqa: ANN001
) -> None:
    """The route's tenant check loads the row first; a decider that then waits on the lock still holds it.

    Not a true concurrency test: SQLite has no row lock, so the waiting is played by loading the row
    in one session, committing the reject from another, and only then deciding. It fails without
    ``populate_existing`` for the same reason the lock-waiting decider would: the identity map's copy wins.
    """
    approval_id = uuid.UUID((await _hire(approval_session_factory)).json()["approval_id"])
    async with approval_session_factory() as stale:
        loaded = await stale.get(Approval, approval_id)  # what load_authorized does before the lock
        assert loaded.status == "pending"
        await _decide(approval_session_factory, approval_id, ApprovalStatus.REJECTED)  # the other decider wins
        with pytest.raises(ApprovalStateError):
            await ApprovalService().decide(
                stale, approval_id=approval_id, decision=ApprovalStatus.APPROVED, decided_by=_BOARD
            )
    assert await _rows(approval_session_factory, AgentOrgNode) == []
    (approval,) = await _rows(approval_session_factory, Approval)
    assert approval.status == "rejected"
    _edges.assert_not_awaited()


# --------------------------------------------------------------------------- the hire-approval switch


async def _org_with(session_factory, role):  # noqa: ANN001, ANN202
    actor = uuid.uuid4()
    async with session_factory() as session:
        org = await CompanyService(session).create(CompanyCreate(name="Acme", slug="acme"))
        await MembershipService().add_member(session, str(org.id), str(actor), role)
        await session.commit()
        return org.id, actor


async def _update(session_factory, org_id, actor, data, *, platform_admin=False):  # noqa: ANN001, ANN202
    async with session_factory() as session:
        await CompanyService(session).update(org_id, data, actor_user_id=actor, platform_admin=platform_admin)
        await session.commit()


async def _gate(session_factory, org_id) -> bool:  # noqa: ANN001
    async with session_factory() as session:
        return (await session.get(Organization, org_id)).require_approval_for_hires


@pytest.mark.asyncio
async def test_a_member_cannot_turn_the_hire_gate_off(session_factory) -> None:  # noqa: ANN001
    org_id, owner = await _org_with(session_factory, MembershipRole.OWNER)
    await _update(session_factory, org_id, owner, CompanyUpdate(require_approval_for_hires=True))
    member = uuid.uuid4()
    async with session_factory() as session:
        await MembershipService().add_member(session, str(org_id), str(member), MembershipRole.MEMBER)
        await session.commit()
    with pytest.raises(NotAuthorisedError):
        await _update(session_factory, org_id, member, CompanyUpdate(require_approval_for_hires=False))
    assert await _gate(session_factory, org_id) is True


@pytest.mark.asyncio
async def test_a_member_may_still_edit_other_fields_and_resend_the_same_gate_value(
    session_factory,
) -> None:  # noqa: ANN001
    org_id, actor = await _org_with(session_factory, MembershipRole.MEMBER)
    await _update(session_factory, org_id, actor, CompanyUpdate(description="new", require_approval_for_hires=False))
    async with session_factory() as session:
        assert (await session.get(Organization, org_id)).description == "new"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
async def test_an_owner_or_admin_may_change_the_hire_gate(session_factory, role) -> None:  # noqa: ANN001
    org_id, actor = await _org_with(session_factory, role)
    await _update(session_factory, org_id, actor, CompanyUpdate(require_approval_for_hires=True))
    assert await _gate(session_factory, org_id) is True


@pytest.mark.asyncio
async def test_a_platform_admin_without_membership_may_change_the_hire_gate(session_factory) -> None:  # noqa: ANN001
    org_id, _owner = await _org_with(session_factory, MembershipRole.OWNER)
    await _update(
        session_factory, org_id, uuid.uuid4(), CompanyUpdate(require_approval_for_hires=True), platform_admin=True
    )
    assert await _gate(session_factory, org_id) is True


# --------------------------------------------------------------------------- hire reports_to


async def _agent(approval_session_factory, agent_id: str, company_id: uuid.UUID) -> None:  # noqa: ANN001
    async with approval_session_factory() as session:
        session.add(
            AgentOrgNode(
                id=uuid.uuid4(), agent_id=agent_id, name=agent_id, org_role=OrgRole.WORKER.value, company_id=company_id
            )
        )
        await session.commit()


async def _hire_under(approval_session_factory, reports_to):  # noqa: ANN001, ANN202
    transport = httpx.ASGITransport(app=_app(approval_session_factory))
    with (
        patch("llc.api.agent_hires.adapter_unavailable_reason", return_value=None),
        patch("llc.api.agent_hires.registered_adapter_types", return_value=["claude_code"]),
    ):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                f"/api/llc/companies/{_ORG}/agent-hires", json={"agent_name": "Newbie", "reports_to": reports_to}
            )


@pytest.mark.asyncio
async def test_a_hire_cannot_report_to_another_companys_agent(approval_session_factory, _edges) -> None:  # noqa: ANN001
    await _agent(approval_session_factory, "their-manager", uuid.uuid4())
    resp = await _hire_under(approval_session_factory, "their-manager")
    assert resp.status_code == 422, resp.text
    assert await _rows(approval_session_factory, Approval) == []


@pytest.mark.asyncio
async def test_a_hire_cannot_report_to_an_unknown_agent(approval_session_factory, _edges) -> None:  # noqa: ANN001
    assert (await _hire_under(approval_session_factory, "nobody")).status_code == 422


@pytest.mark.asyncio
async def test_a_hire_may_report_to_an_agent_of_its_own_company(
    approval_session_factory, _edges
) -> None:  # noqa: ANN001
    await _agent(approval_session_factory, "my-manager", _ORG)
    resp = await _hire_under(approval_session_factory, "my-manager")
    assert resp.status_code == 202, resp.text
    (approval,) = await _rows(approval_session_factory, Approval)
    assert approval.context["reports_to"] == "my-manager"


# --------------------------------------------------------------------------- sprint close attribution


@pytest.mark.asyncio
async def test_sprint_close_is_attributed_to_the_caller_not_the_body() -> None:
    caller, forged, sprint_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    org = uuid.uuid4()
    found = MagicMock()
    found.scalar_one_or_none.return_value = SimpleNamespace(company_id=org)
    session = AsyncMock()
    session.execute.return_value = found
    body = sprints.SprintCloseRequest(approval_id=uuid.uuid4(), decided_by=forged)
    ctx = TenantContext(org_id=org, user_id=caller, is_platform_admin=False)
    with (
        patch.object(sprints._autoclose_svc, "execute_close", new_callable=AsyncMock) as close,
        patch.object(sprints._autoclose_svc, "schedule_closed_sprint_summary"),
    ):
        await sprints.close_sprint(sprint_id, body, session, {"id": str(caller)}, ctx)
    assert close.call_args.kwargs["decided_by"] == caller


def test_sprint_close_still_accepts_a_body_without_decided_by() -> None:
    assert sprints.SprintCloseRequest(approval_id=uuid.uuid4()).decided_by is None
