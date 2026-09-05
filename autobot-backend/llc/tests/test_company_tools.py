# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The tool catalogue: registry identity plus one company's own facts (#14852).

The tests that carry the weight, because each one covers a way the catalogue
could look right while being wrong:

``test_a_tool_with_no_overlay_still_appears`` — the catalogue is driven by the
registry, not by the overlay table. An inner join would hide exactly the tools
someone opened the catalogue to fill in, and would do it silently: the page
would render, just short.

``test_usage_of_an_unused_tool_issues_one_query`` — ``usage`` skips the
workflow lookup when no role carries the tool. Asserting the *result* proves
nothing here: SQLAlchemy renders ``in_([])`` as an empty set, so an empty
answer comes back whether the short-circuit exists or not. Mutation testing
caught that — removing the short-circuit left the result assertion green. So
this counts the queries instead, which is the only thing the short-circuit
actually changes.

``test_the_catalogue_does_not_leak_another_company`` — overlay, attachment and
count are all company-scoped. A dropped ``WHERE`` on any one of the three shows
up as another company's URL, or as a role count borrowed from next door.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Fully-qualified, matching the service (#14373): the bare ``tool_sdk`` path
# resolves to a different singleton than the one under test, so patching it
# there would be a no-op against production behaviour.
from autobot_shared.tool_sdk.registry import get_tool_registry
from llc.models.company_tool import LLCCompanyTool
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.models.role_tool import LLCRoleTool
from llc.models.role_workflow import LLCRoleWorkflow
from llc.services.authz import NotAuthorisedError
from llc.services.company_tool import CompanyToolService
from llc.services.role import RoleService
from llc.services.role_tool import RoleToolService

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.role import Role

_ADMIN_USER = uuid.uuid4()
_OUTSIDER = uuid.uuid4()
_TOOL = "llc.company_tool_fixture"
_OTHER_TOOL = "llc.company_tool_other"


class _FakeMeta:
    """Carries the three fields the catalogue reads, unlike the name-only fake
    in ``test_role_tools`` — that one exercises validation, which deliberately
    reads ``name`` and nothing else."""

    def __init__(self, name: str, description: str = "", tags: tuple = ()) -> None:
        self.name = name
        self.description = description
        self.tags = list(tags)


@pytest.fixture
def registry(monkeypatch):  # noqa: ANN001, ANN201
    """Control what the registry reports, without registering real tools.

    Patches ``list_tools`` on the live singleton rather than swapping the
    accessor, so the service exercises the same object it uses in production.
    """
    live = get_tool_registry()
    metas = [
        _FakeMeta(_TOOL, "The fixture tool", ("crm", "sales")),
        _FakeMeta(_OTHER_TOOL, "Another fixture tool", ()),
    ]
    monkeypatch.setattr(live, "list_tools", lambda **_: list(metas))
    return metas


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = (
        create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
            "sqlite+aiosqlite:///:memory:"
        )
    )
    tables = [
        Role.__table__,
        LLCCompanyMembership.__table__,
        LLCRoleTool.__table__,
        LLCRoleWorkflow.__table__,
        LLCCompanyTool.__table__,
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


async def _grant_admin(session_factory, company_id: uuid.UUID) -> None:  # noqa: ANN001
    async with session_factory() as session:
        existing = await session.execute(
            sa.select(LLCCompanyMembership.id).where(
                LLCCompanyMembership.company_id == company_id,
                LLCCompanyMembership.user_id == _ADMIN_USER,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company_id,
                user_id=_ADMIN_USER,
                role=MembershipRole.ADMIN.value,
            )
        )
        await session.commit()


async def _seed_role(session_factory, company_id: uuid.UUID, name: str) -> uuid.UUID:  # noqa: ANN001
    await _grant_admin(session_factory, company_id)
    async with session_factory() as session:
        role = await RoleService().create(
            session, company_id=company_id, name=name, actor_user_id=_ADMIN_USER
        )
        await session.commit()
        return role.id


async def _attach(
    session_factory, company_id: uuid.UUID, role_id: uuid.UUID, tool: str
) -> None:  # noqa: ANN001
    async with session_factory() as session:
        await RoleToolService().attach(
            session,
            company_id=company_id,
            role_id=role_id,
            tool_name=tool,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()


def _by_name(entries) -> dict:  # noqa: ANN001
    return {entry.name: entry for entry in entries}


@pytest.mark.asyncio
async def test_a_tool_with_no_overlay_still_appears(session_factory, registry):  # noqa: ANN001
    """The registry drives the catalogue; the overlay only decorates it."""
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)

    async with session_factory() as session:
        entries = _by_name(await CompanyToolService().catalogue(session, company))

    assert set(entries) == {_TOOL, _OTHER_TOOL}
    assert entries[_TOOL].url is None
    assert entries[_TOOL].logo_url is None
    assert entries[_TOOL].role_count == 0
    # The grouping comes from the registry's tags, not from a column.
    assert entries[_TOOL].tags == ("crm", "sales")
    assert entries[_TOOL].description == "The fixture tool"


@pytest.mark.asyncio
async def test_an_overlay_supplies_url_and_logo(session_factory, registry):  # noqa: ANN001
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    service = CompanyToolService()

    async with session_factory() as session:
        await service.upsert(
            session,
            company_id=company,
            tool_name=_TOOL,
            url="https://example.invalid/crm",
            logo_url="https://example.invalid/crm.png",
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        entries = _by_name(await service.catalogue(session, company))

    assert entries[_TOOL].url == "https://example.invalid/crm"
    assert entries[_TOOL].logo_url == "https://example.invalid/crm.png"
    # The un-overlaid tool is untouched by its neighbour's row.
    assert entries[_OTHER_TOOL].url is None


@pytest.mark.asyncio
async def test_upsert_replaces_rather_than_duplicates(session_factory, registry):  # noqa: ANN001
    """Second write updates the same row — the unique constraint holds."""
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    service = CompanyToolService()

    for url in ("https://example.invalid/one", "https://example.invalid/two"):
        async with session_factory() as session:
            await service.upsert(
                session,
                company_id=company,
                tool_name=_TOOL,
                url=url,
                logo_url=None,
                actor_user_id=_ADMIN_USER,
            )
            await session.commit()

    async with session_factory() as session:
        rows = await session.execute(
            sa.select(sa.func.count())
            .select_from(LLCCompanyTool)
            .where(LLCCompanyTool.company_id == company)
        )
        assert rows.scalar_one() == 1
        entries = _by_name(await service.catalogue(session, company))
    assert entries[_TOOL].url == "https://example.invalid/two"


@pytest.mark.asyncio
async def test_an_unregistered_tool_cannot_be_overlaid(session_factory, registry):  # noqa: ANN001
    """An overlay for an unattachable name would be a row nothing ever reads."""
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)

    async with session_factory() as session:
        with pytest.raises(ValueError, match="unknown tool"):
            await CompanyToolService().upsert(
                session,
                company_id=company,
                tool_name="llc.nope",
                url="https://example.invalid",
                logo_url=None,
                actor_user_id=_ADMIN_USER,
            )


@pytest.mark.asyncio
async def test_a_non_admin_cannot_record_company_facts(session_factory, registry):  # noqa: ANN001
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)

    async with session_factory() as session:
        with pytest.raises(NotAuthorisedError):
            await CompanyToolService().upsert(
                session,
                company_id=company,
                tool_name=_TOOL,
                url="https://example.invalid",
                logo_url=None,
                actor_user_id=_OUTSIDER,
            )


@pytest.mark.asyncio
async def test_role_count_counts_distinct_roles(session_factory, registry):  # noqa: ANN001
    company = uuid.uuid4()
    first = await _seed_role(session_factory, company, "SRE")
    second = await _seed_role(session_factory, company, "Support")
    await _attach(session_factory, company, first, _TOOL)
    await _attach(session_factory, company, second, _TOOL)

    async with session_factory() as session:
        entries = _by_name(await CompanyToolService().catalogue(session, company))

    assert entries[_TOOL].role_count == 2
    assert entries[_OTHER_TOOL].role_count == 0


@pytest.mark.asyncio
async def test_usage_names_the_roles_and_their_workflows(session_factory, registry):  # noqa: ANN001
    """The question the issue said could only be answered by scanning roles."""
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    await _attach(session_factory, company, role_id, _TOOL)

    async with session_factory() as session:
        session.add(
            LLCRoleWorkflow(
                id=uuid.uuid4(),
                company_id=company,
                role_id=role_id,
                workflow_id="wf.onboarding",
            )
        )
        await session.commit()

    async with session_factory() as session:
        usage = await CompanyToolService().usage(session, company, _TOOL)

    assert usage["role_ids"] == [str(role_id)]
    assert usage["workflow_ids"] == ["wf.onboarding"]


@pytest.mark.asyncio
async def test_usage_of_an_unused_tool_issues_one_query(session_factory, registry):  # noqa: ANN001
    """No role carries the tool, so the workflow lookup is never issued.

    The result is asserted too, but the result alone is not evidence: with the
    short-circuit removed, ``in_([])`` still returns nothing and the assertion
    still passes. The query count is what distinguishes the two.
    """
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        session.add(
            LLCRoleWorkflow(
                id=uuid.uuid4(),
                company_id=company,
                role_id=role_id,
                workflow_id="wf.unrelated",
            )
        )
        await session.commit()

    async with session_factory() as session:
        executed = []
        original = session.execute

        async def counting(statement, *args, **kwargs):  # noqa: ANN001, ANN202
            executed.append(statement)
            return await original(statement, *args, **kwargs)

        session.execute = counting  # type: ignore[method-assign]
        usage = await CompanyToolService().usage(session, company, _OTHER_TOOL)

    assert usage == {"role_ids": [], "workflow_ids": []}
    assert len(executed) == 1, (
        f"expected only the role lookup, saw {len(executed)} queries — "
        "the workflow lookup ran despite no role carrying the tool"
    )


@pytest.mark.asyncio
async def test_the_catalogue_does_not_leak_another_company(session_factory, registry):  # noqa: ANN001
    """Overlay, attachment and count are each company-scoped."""
    mine = uuid.uuid4()
    theirs = uuid.uuid4()
    await _grant_admin(session_factory, mine)
    their_role = await _seed_role(session_factory, theirs, "Their SRE")
    await _attach(session_factory, theirs, their_role, _TOOL)

    async with session_factory() as session:
        await CompanyToolService().upsert(
            session,
            company_id=theirs,
            tool_name=_TOOL,
            url="https://their.invalid/crm",
            logo_url=None,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        entries = _by_name(await CompanyToolService().catalogue(session, mine))
        usage = await CompanyToolService().usage(session, mine, _TOOL)

    assert entries[_TOOL].url is None, (
        "another company's overlay leaked into this catalogue"
    )
    assert entries[_TOOL].role_count == 0, (
        "another company's attachment was counted here"
    )
    assert usage["role_ids"] == []


@pytest.mark.asyncio
async def test_a_concurrent_insert_is_adopted_not_a_500(session_factory, registry):  # noqa: ANN001
    """Two writers race for the same (company, tool); the loser adopts the winner.

    ``upsert`` reads before it writes, so another request can insert the row in
    between. The unique index then rejects the second insert, and without the
    savepoint that ``IntegrityError`` reaches the client as a 500 on a ``PUT``
    — an operation a double-click or a retry genuinely issues twice.

    The race is simulated deterministically rather than with real concurrency:
    the row is created first, and ``get`` is stubbed to return None **once**, so
    the service takes exactly the branch it would take having read before the
    other writer committed. A timing-based test would pass or fail by luck.
    """
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    service = CompanyToolService()

    async with session_factory() as session:
        await service.upsert(
            session,
            company_id=company,
            tool_name=_TOOL,
            url="https://winner.invalid",
            logo_url=None,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    real_get = service.get
    calls = {"n": 0}

    async def get_blind_once(session, company_id, tool_name):  # noqa: ANN001, ANN202
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # the row the other writer has already committed
        return await real_get(session, company_id, tool_name)

    async with session_factory() as session:
        service.get = get_blind_once  # type: ignore[method-assign]
        try:
            result = await service.upsert(
                session,
                company_id=company,
                tool_name=_TOOL,
                url="https://loser.invalid",
                logo_url=None,
                actor_user_id=_ADMIN_USER,
            )
            await session.commit()
        finally:
            service.get = real_get  # type: ignore[method-assign]

    assert result is not None, "the conflicting writer got no row back"

    async with session_factory() as session:
        rows = await session.execute(
            sa.select(sa.func.count())
            .select_from(LLCCompanyTool)
            .where(LLCCompanyTool.company_id == company)
        )
        # One row, not two: the loser adopted rather than duplicating.
        assert rows.scalar_one() == 1
        entries = _by_name(await service.catalogue(session, company))
    assert entries[_TOOL].url == "https://loser.invalid"
