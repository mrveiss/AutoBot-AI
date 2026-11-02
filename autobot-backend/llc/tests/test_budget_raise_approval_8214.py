# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A company that gates budget raises answers 202 and moves nothing until the board approves (#8214)."""

# flake8: noqa: F811 -- fixtures imported from the support module are re-bound as parameters
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.budget import LLCAgentBudget
from llc.models.enums import ApprovalStatus
from llc.services.approval import ApprovalHookError
from llc.tests.approval_enforcement_support_test import _edges  # noqa: F401 -- autouse fixture
from llc.tests.approval_enforcement_support_test import activity  # noqa: F401 -- fixture
from llc.tests.approval_enforcement_support_test import session_factory  # noqa: F401 -- fixture
from llc.tests.approval_enforcement_support_test import _ORG, _member, _rows
from llc.tests.test_approval_four_eyes_8214 import ASKER, OTHER, _decide_as
from models.agent_org import AgentOrgNode, OrgRole
from models.approval import Approval
from user_management.models.organization import Organization

_URL = "/api/llc/budget/a1/limit"


def _app(session_factory, user_id: uuid.UUID):  # noqa: ANN001, ANN202
    from fastapi import FastAPI

    from api.user_management.dependencies import get_current_user, get_tenant_context, require_org_context
    from llc.api import budget as budget_api
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    app = FastAPI()
    app.include_router(budget_api.router, prefix="/api/llc")

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session
            await session.commit()

    ctx = TenantContext(org_id=_ORG, user_id=user_id, is_platform_admin=False)
    app.dependency_overrides[get_async_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user_id), "auth_method": "session"}
    app.dependency_overrides[get_tenant_context] = lambda: ctx
    app.dependency_overrides[require_org_context] = lambda: ctx
    return app


async def _call(session_factory, user, method, path, body):  # noqa: ANN001, ANN202
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(session_factory, user)), base_url="http://t"
    ) as c:
        return await c.request(method, path, json=body)


async def _setup(session_factory, *, gated: bool = True, **budget) -> None:  # noqa: ANN001
    async with session_factory() as session:
        await session.execute(update(Organization).values(require_approval_for_budget_raises=gated))
        session.add(
            AgentOrgNode(id=uuid.uuid4(), agent_id="a1", name="A", org_role=OrgRole.WORKER.value, company_id=_ORG)
        )
        session.add(LLCAgentBudget(company_id=str(_ORG), agent_id="a1", **{"budget_limit": Decimal("10"), **budget}))
        await session.commit()
    await _member(session_factory, ASKER, "admin")
    await _member(session_factory, OTHER, "owner")


async def _budget(session_factory) -> LLCAgentBudget:  # noqa: ANN001
    async with session_factory() as session:
        session.expire_all()
        return (await session.execute(select(LLCAgentBudget))).scalar_one()


async def _only_approval(session_factory) -> Approval:  # noqa: ANN001
    (approval,) = await _rows(session_factory, Approval)
    return approval


@pytest.mark.asyncio
async def test_a_company_without_the_setting_applies_a_raise_at_once(session_factory) -> None:  # noqa: ANN001
    await _setup(session_factory, gated=False)
    resp = await _call(session_factory, ASKER, "PATCH", _URL, {"budget_limit": "50"})
    assert resp.status_code == 200, resp.text
    assert (await _budget(session_factory)).budget_limit == Decimal("50")
    assert await _rows(session_factory, Approval) == []


@pytest.mark.asyncio
async def test_a_raise_is_202_pending_and_changes_nothing_then_another_admin_applies_it(
    session_factory,
) -> None:  # noqa: ANN001
    await _setup(session_factory)
    resp = await _call(session_factory, ASKER, "PATCH", _URL, {"budget_limit": "50"})
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "pending_approval"
    assert (await _budget(session_factory)).budget_limit == Decimal("10")
    approval = await _only_approval(session_factory)
    assert (approval.approval_type, approval.status) == ("budget_override", "pending")
    assert approval.requested_by_agent == str(ASKER)  # the verified caller
    with pytest.raises(ApprovalHookError, match="different owner or admin"):
        await _decide_as(session_factory, approval.id, ApprovalStatus.APPROVED, ASKER)
    assert (await _budget(session_factory)).budget_limit == Decimal("10")
    await _decide_as(session_factory, approval.id, ApprovalStatus.APPROVED, OTHER)
    assert (await _budget(session_factory)).budget_limit == Decimal("50")


@pytest.mark.asyncio
async def test_lowering_a_limit_is_immediate_even_in_a_gated_company(session_factory) -> None:  # noqa: ANN001
    await _setup(session_factory)
    resp = await _call(session_factory, ASKER, "PATCH", _URL, {"budget_limit": "5"})
    assert resp.status_code == 200, resp.text
    assert (await _budget(session_factory)).budget_limit == Decimal("5")
    assert await _rows(session_factory, Approval) == []


@pytest.mark.asyncio
async def test_a_plain_member_is_still_refused_before_any_approval_is_filed(session_factory) -> None:  # noqa: ANN001
    await _setup(session_factory)
    member = uuid.uuid4()
    await _member(session_factory, member, "member")
    resp = await _call(session_factory, member, "PATCH", _URL, {"budget_limit": "50"})
    assert resp.status_code == 403, resp.text
    assert await _rows(session_factory, Approval) == []


@pytest.mark.asyncio
async def test_a_token_limit_raise_is_pending_and_the_approval_applies_it(session_factory) -> None:  # noqa: ANN001
    await _setup(session_factory, budget_mode="tokens", token_limit=1000)
    resp = await _call(session_factory, ASKER, "PATCH", _URL, {"token_limit": 5000})
    assert resp.status_code == 202, resp.text
    assert (await _budget(session_factory)).token_limit == 1000
    await _decide_as(session_factory, (await _only_approval(session_factory)).id, ApprovalStatus.APPROVED, OTHER)
    assert (await _budget(session_factory)).token_limit == 5000


@pytest.mark.asyncio
async def test_lowering_a_token_limit_is_immediate(session_factory) -> None:  # noqa: ANN001
    await _setup(session_factory, budget_mode="tokens", token_limit=1000)
    assert (await _call(session_factory, ASKER, "PATCH", _URL, {"token_limit": 10})).status_code == 200
    assert (await _budget(session_factory)).token_limit == 10


@pytest.mark.asyncio
async def test_a_dollar_raise_on_a_token_limited_budget_changes_nothing_enforced_so_applies_at_once(
    session_factory,  # noqa: ANN001
) -> None:
    await _setup(session_factory, budget_mode="tokens", token_limit=1000)
    resp = await _call(session_factory, ASKER, "PATCH", _URL, {"budget_limit": "99"})
    assert resp.status_code == 200, resp.text
    assert await _rows(session_factory, Approval) == []


@pytest.mark.asyncio
async def test_a_switch_to_a_token_limit_is_a_raise_and_the_approval_applies_the_switch(
    session_factory,
) -> None:  # noqa: ANN001
    await _setup(session_factory)
    resp = await _call(session_factory, ASKER, "PATCH", _URL, {"budget_mode": "tokens", "token_limit": 7000})
    assert resp.status_code == 202, resp.text
    assert (await _budget(session_factory)).budget_mode == "dollars"
    await _decide_as(session_factory, (await _only_approval(session_factory)).id, ApprovalStatus.APPROVED, OTHER)
    row = await _budget(session_factory)
    assert (row.budget_mode, row.token_limit) == ("tokens", 7000)


@pytest.mark.asyncio
async def test_the_alert_threshold_alone_is_not_a_raise(session_factory) -> None:  # noqa: ANN001
    await _setup(session_factory)
    assert (await _call(session_factory, ASKER, "PATCH", _URL, {"alert_threshold": 0.5})).status_code == 200


@pytest.mark.asyncio
async def test_a_first_limit_above_the_default_is_created_at_the_default_and_pends_the_rest(
    session_factory,
) -> None:  # noqa: ANN001
    from llc.config import DEFAULT_BUDGET_LIMIT

    await _setup(session_factory)
    async with session_factory() as session:
        await session.execute(LLCAgentBudget.__table__.delete())
        session.add(
            AgentOrgNode(id=uuid.uuid4(), agent_id="a2", name="B", org_role=OrgRole.WORKER.value, company_id=_ORG)
        )
        await session.commit()
    resp = await _call(session_factory, ASKER, "POST", "/api/llc/budget/a2", {"budget_limit": "500"})
    assert resp.status_code == 202, resp.text
    assert (await _budget(session_factory)).budget_limit == DEFAULT_BUDGET_LIMIT
    assert (await _only_approval(session_factory)).context["budget_limit"] == "500"


@pytest.mark.asyncio
async def test_a_first_limit_at_or_below_the_default_is_created_as_asked(session_factory) -> None:  # noqa: ANN001
    await _setup(session_factory)
    async with session_factory() as session:
        await session.execute(LLCAgentBudget.__table__.delete())
        await session.commit()
    resp = await _call(session_factory, ASKER, "POST", "/api/llc/budget/a1", {"budget_limit": "3"})
    assert resp.status_code == 201, resp.text
    assert (await _budget(session_factory)).budget_limit == Decimal("3")
    assert await _rows(session_factory, Approval) == []
