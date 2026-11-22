# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ``require_approval_for_budget_raises`` company setting: default, who changes it, and import (#8214)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from llc.api.companies import _to_read
from llc.models.company import CompanyCreate, CompanyUpdate
from llc.models.enums import MembershipRole
from llc.services.authz import NotAuthorisedError
from llc.services.company import CompanyService
from llc.services.membership_service import MembershipService
from llc.tests import test_llc_org_chart as _org_chart_harness
from user_management.models.organization import Organization

engine = _org_chart_harness.engine
session_factory = _org_chart_harness.session_factory


async def _org_with(session_factory, role, **create):  # noqa: ANN001, ANN202
    actor = uuid.uuid4()
    async with session_factory() as session:
        org = await CompanyService(session).create(CompanyCreate(name="Acme", slug="acme", **create))
        await MembershipService().add_member(session, str(org.id), str(actor), role)
        await session.commit()
        return org.id, actor


async def _update(session_factory, org_id, actor, data):  # noqa: ANN001, ANN202
    async with session_factory() as session:
        await CompanyService(session).update(org_id, data, actor_user_id=actor, platform_admin=False)
        await session.commit()


async def _flag(session_factory, org_id) -> bool:  # noqa: ANN001
    async with session_factory() as session:
        return (await session.get(Organization, org_id)).require_approval_for_budget_raises


@pytest.mark.asyncio
async def test_a_new_company_leaves_budget_raises_ungated_and_can_be_created_gated(
    session_factory,
) -> None:  # noqa: ANN001
    org_id, _ = await _org_with(session_factory, MembershipRole.OWNER)
    assert await _flag(session_factory, org_id) is False
    async with session_factory() as session:
        gated = await CompanyService(session).create(
            CompanyCreate(name="Gated", slug="gated", require_approval_for_budget_raises=True)
        )
        await session.commit()
    assert await _flag(session_factory, gated.id) is True


@pytest.mark.asyncio
async def test_a_member_cannot_turn_the_budget_gate_off_but_an_owner_can(session_factory) -> None:  # noqa: ANN001
    org_id, owner = await _org_with(session_factory, MembershipRole.OWNER, require_approval_for_budget_raises=True)
    member = uuid.uuid4()
    async with session_factory() as session:
        await MembershipService().add_member(session, str(org_id), str(member), MembershipRole.MEMBER)
        await session.commit()
    with pytest.raises(NotAuthorisedError):
        await _update(session_factory, org_id, member, CompanyUpdate(require_approval_for_budget_raises=False))
    assert await _flag(session_factory, org_id) is True
    await _update(session_factory, org_id, owner, CompanyUpdate(require_approval_for_budget_raises=False))
    assert await _flag(session_factory, org_id) is False


@pytest.mark.asyncio
async def test_a_member_may_resend_the_same_budget_gate_value_with_another_edit(
    session_factory,
) -> None:  # noqa: ANN001
    org_id, actor = await _org_with(session_factory, MembershipRole.MEMBER)
    await _update(
        session_factory, org_id, actor, CompanyUpdate(description="new", require_approval_for_budget_raises=False)
    )
    async with session_factory() as session:
        assert (await session.get(Organization, org_id)).description == "new"


@pytest.mark.asyncio
async def test_the_company_response_carries_the_setting(session_factory) -> None:  # noqa: ANN001
    org_id, _ = await _org_with(session_factory, MembershipRole.OWNER, require_approval_for_budget_raises=True)
    async with session_factory() as session:
        assert _to_read(await session.get(Organization, org_id)).require_approval_for_budget_raises is True


@pytest.mark.asyncio
async def test_an_import_carries_the_setting_over_and_an_option_overrides_it(session_factory) -> None:  # noqa: ANN001
    from llc.services.portability import PortabilityService

    template = {
        "schema_version": "1.0",
        "company": {"name": "Imp", "slug": "imp", "require_approval_for_budget_raises": True},
        "agents": [],
        "goals": [],
        "projects": [],
        "work_items": [],
    }
    with patch("llc.services.portability.settle_imported_ceo", new=AsyncMock()):
        async with session_factory() as session:
            await PortabilityService(session=session).execute_import(template)
            await PortabilityService(session=session).execute_import(
                {**template, "company": {**template["company"], "slug": "imp2"}},
                remapping_options={"require_approval_for_budget_raises": False},
            )
            await session.commit()
    async with session_factory() as session:
        rows = (await session.execute(select(Organization).where(Organization.slug.in_(["imp", "imp2"])))).scalars()
        assert {o.slug: o.require_approval_for_budget_raises for o in rows} == {"imp": True, "imp2": False}
