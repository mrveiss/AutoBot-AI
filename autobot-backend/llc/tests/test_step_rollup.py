# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Totalling the operation, and refusing to overstate what is known (GH#14599).

The rule under test is the arithmetic form of one this area has already broken
three times (#14064, #13617, #14556): silence must not read as zero. A step
nobody measured is excluded from the sum and counted in ``not_costable`` — it
is never folded in as costing nothing, which would make a partial total
indistinguishable from a complete one.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.role_rate import LLCRoleRate
from llc.models.role_tool import LLCRoleTool
from llc.models.role_workflow import LLCRoleWorkflow
from llc.services.step_rollup import StepRollupService, _scoped_tool_rows
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.role import Role


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Only the tables this test touches — the pattern test_role_workflows.py sets.

    Not ``harness.create_loop_schema``: that builds an explicit list of *loop*
    models, and none of these are in it.
    """
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [
        Role.__table__,
        LLCRoleWorkflow.__table__,
        LLCRoleRate.__table__,
        LLCRoleTool.__table__,
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed(session: AsyncSession, company_id: uuid.UUID) -> uuid.UUID:
    """One role, a rate, two workflows — one measured, one not — and a tool."""
    role_id = uuid.uuid4()
    session.add(Role(id=role_id, org_id=company_id, name="Head of Sales"))
    session.add(
        LLCRoleRate(
            id=uuid.uuid4(),
            company_id=company_id,
            role_id=role_id,
            hourly_rate=Decimal("120"),
            currency="EUR",
        )
    )
    session.add(
        LLCRoleWorkflow(
            id=uuid.uuid4(),
            company_id=company_id,
            role_id=role_id,
            workflow_id="wf-measured",
            estimated_minutes=30,
            runs_per_month=10,
        )
    )
    session.add(
        LLCRoleWorkflow(
            id=uuid.uuid4(),
            company_id=company_id,
            role_id=role_id,
            workflow_id="wf-unmeasured",
            estimated_minutes=None,
            runs_per_month=None,
        )
    )
    session.add(LLCRoleTool(id=uuid.uuid4(), company_id=company_id, role_id=role_id, tool_name="crm"))
    await session.flush()
    return role_id


@pytest.mark.asyncio
async def test_the_total_excludes_what_nobody_measured(session: AsyncSession) -> None:
    company_id = uuid.uuid4()
    await _seed(session, company_id)

    result = await StepRollupService().rollup(session, company_id)
    role = result["by_role"][0]

    # 30 minutes at 120/hour, ten times a month.
    assert role.per_month == Decimal("600")
    assert role.costed == 1
    # The unmeasured step is counted, not summed as zero.
    assert role.not_costable == 1
    assert role.total_steps == 2


@pytest.mark.asyncio
async def test_a_partial_total_never_claims_to_be_complete(session: AsyncSession) -> None:
    """The assertion that makes the total safe to read."""
    company_id = uuid.uuid4()
    await _seed(session, company_id)

    role = (await StepRollupService().rollup(session, company_id))["by_role"][0]

    assert role.is_complete is False
    # And it is not merely "no error": a real figure IS reported alongside.
    assert role.per_month > 0


@pytest.mark.asyncio
async def test_a_tool_carries_the_cost_of_the_steps_its_role_runs(session: AsyncSession) -> None:
    company_id = uuid.uuid4()
    await _seed(session, company_id)

    result = await StepRollupService().rollup(session, company_id)
    tool = result["by_tool"][0]

    assert tool.label == "crm"
    assert tool.per_month == Decimal("600")
    assert tool.not_costable == 1


@pytest.mark.asyncio
async def test_another_company_contributes_nothing(session: AsyncSession) -> None:
    """Scope is pinned on both sides of the join, so neither predicate alone widens it."""
    mine = uuid.uuid4()
    theirs = uuid.uuid4()
    await _seed(session, mine)
    await _seed(session, theirs)

    result = await StepRollupService().rollup(session, mine)

    assert len(result["by_role"]) == 1
    assert result["by_role"][0].per_month == Decimal("600")


async def _seed_role(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    attach_company: uuid.UUID,
    name: str,
    currency: str = "EUR",
    rate: str = "120",
    tool: str | None = "crm",
    tool_company: uuid.UUID | None = None,
) -> uuid.UUID:
    """One role in ``org_id`` with a measured step; the row company ids are explicit.

    Passing ``attach_company`` / ``tool_company`` different from ``org_id``
    builds the cross-wired rows the symmetric ``_seed`` cannot.
    """
    role_id = uuid.uuid4()
    session.add(Role(id=role_id, org_id=org_id, name=name))
    session.add(
        LLCRoleRate(id=uuid.uuid4(), company_id=org_id, role_id=role_id, hourly_rate=Decimal(rate), currency=currency)
    )
    session.add(
        LLCRoleWorkflow(
            id=uuid.uuid4(),
            company_id=attach_company,
            role_id=role_id,
            workflow_id=f"wf-{name}",
            estimated_minutes=30,
            runs_per_month=10,
        )
    )
    if tool:
        session.add(LLCRoleTool(id=uuid.uuid4(), company_id=tool_company or org_id, role_id=role_id, tool_name=tool))
    await session.flush()
    return role_id


@pytest.mark.asyncio
async def test_a_tool_spanning_two_currencies_has_no_blended_sum(session: AsyncSession) -> None:
    """#14670: EUR and USD on one tool are reported apart and never added."""
    company = uuid.uuid4()
    await _seed_role(session, org_id=company, attach_company=company, name="A", currency="EUR", rate="120")
    await _seed_role(session, org_id=company, attach_company=company, name="B", currency="USD", rate="60")

    tool = (await StepRollupService().rollup(session, company))["by_tool"][0]

    assert tool.is_mixed_currency is True
    assert tool.per_month is None
    # 30 min x 10 runs: EUR 120/h -> 600, USD 60/h -> 300.
    assert tool.amounts == {"EUR": Decimal("600"), "USD": Decimal("300")}
    assert tool.currencies == ["EUR", "USD"]
    assert tool.costed == 2


@pytest.mark.asyncio
async def test_two_roles_in_one_currency_still_sum(session: AsyncSession) -> None:
    company = uuid.uuid4()
    await _seed_role(session, org_id=company, attach_company=company, name="A", currency="EUR", rate="120")
    await _seed_role(session, org_id=company, attach_company=company, name="B", currency="EUR", rate="60")

    tool = (await StepRollupService().rollup(session, company))["by_tool"][0]

    assert tool.is_mixed_currency is False
    assert tool.per_month == Decimal("900")
    assert tool.amounts == {"EUR": Decimal("900")}


@pytest.mark.asyncio
async def test_an_empty_bucket_total_is_zero_not_absent(session: AsyncSession) -> None:
    """Only a mixed bucket has no total; a bucket with nothing costed keeps its 0."""
    from llc.services.step_rollup import RollupBucket

    bucket = RollupBucket(key="k", label="k")
    assert bucket.per_month == Decimal(0)
    assert bucket.currencies == []


@pytest.mark.asyncio
async def test_a_cross_wired_attachment_is_excluded(session: AsyncSession) -> None:
    """A role of another company carrying MY company id on its attachment (Role.org_id predicate)."""
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    await _seed(session, mine)
    await _seed_role(session, org_id=theirs, attach_company=mine, name="Intruder", tool="intruder-tool")

    result = await StepRollupService().rollup(session, mine)

    assert [b.label for b in result["by_role"]] == ["Head of Sales"]
    assert [b.label for b in result["by_tool"]] == ["crm"]


@pytest.mark.asyncio
async def test_an_attachment_claiming_another_company_is_excluded(session: AsyncSession) -> None:
    """MY role whose attachment row names another company (LLCRoleWorkflow.company_id predicate)."""
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    await _seed(session, mine)
    await _seed_role(session, org_id=mine, attach_company=theirs, name="Stray", tool="stray-tool")

    result = await StepRollupService().rollup(session, mine)

    assert [b.label for b in result["by_role"]] == ["Head of Sales"]
    assert [b.label for b in result["by_tool"]] == ["crm"]


@pytest.mark.asyncio
async def test_a_tool_row_claiming_another_company_is_excluded(session: AsyncSession) -> None:
    """MY role with a tool row stamped with another company (LLCRoleTool.company_id predicate)."""
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    await _seed_role(session, org_id=mine, attach_company=mine, name="A", tool="own-tool")
    await _seed_role(session, org_id=mine, attach_company=mine, name="B", tool="foreign-tool", tool_company=theirs)

    labels = [b.label for b in (await StepRollupService().rollup(session, mine))["by_tool"]]

    assert labels == ["own-tool"]


@pytest.mark.asyncio
async def test_tool_rows_pin_the_role_org_themselves(session: AsyncSession) -> None:
    """Role.org_id on the tool query: a foreign role's tool row stamped with my company id.

    Unobservable through ``rollup`` (its attachments query already drops that
    role), which is the implicit cross-query invariant #14670 asked to make
    explicit — so the query is asserted directly.
    """
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    own = await _seed_role(session, org_id=mine, attach_company=mine, name="A", tool="own-tool")
    await _seed_role(session, org_id=theirs, attach_company=theirs, name="B", tool="leak", tool_company=mine)

    rows = await _scoped_tool_rows(session, mine)

    assert [tuple(r) for r in rows] == [(own, "own-tool")]


@pytest.mark.asyncio
async def test_the_api_shape_omits_the_blend_and_keeps_single_currency(session: AsyncSession) -> None:
    """The wire shape: per_month is null when mixed; single-currency keeps its figure."""
    from llc.api.costs import _bucket_out

    company = uuid.uuid4()
    await _seed_role(
        session, org_id=company, attach_company=company, name="A", currency="EUR", rate="120", tool="mixed"
    )
    await _seed_role(session, org_id=company, attach_company=company, name="B", currency="USD", rate="60", tool="mixed")
    await _seed_role(session, org_id=company, attach_company=company, name="C", currency="EUR", rate="60", tool="solo")

    by_tool = {b.label: _bucket_out(b) for b in (await StepRollupService().rollup(session, company))["by_tool"]}

    assert by_tool["mixed"].per_month is None
    assert by_tool["mixed"].is_mixed_currency is True
    assert [(a.currency, a.per_month) for a in by_tool["mixed"].per_currency] == [
        ("EUR", Decimal("600")),
        ("USD", Decimal("300")),
    ]
    assert by_tool["solo"].per_month == Decimal("300")
    assert by_tool["solo"].currencies == ["EUR"]
    assert by_tool["solo"].is_mixed_currency is False
