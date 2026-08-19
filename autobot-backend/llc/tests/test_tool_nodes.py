# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tool nodes — which tools a company's roles depend on (#14597).

Derived from ``llc_role_tools`` rather than stored again, so these tests pin
the projection: a role with no tool produces no node, and a tool attached in
another company never appears here. The second one matters most — the
endpoint joins two tables that each carry ``company_id``, and a scoping
predicate that silently matches nothing looks exactly like one that works.

Mirrors ``test_process_nodes.py`` exactly (same fixture shape, same test
names translated to the tool vocabulary) — ``get_tool_nodes`` is the sibling
of ``get_process_nodes``, built the same way for the same reason.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.api.companies import get_tool_nodes
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.models.role_tool import LLCRoleTool
from llc.services.role import RoleService

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.role import Role
from user_management.services import TenantContext

_ADMIN_USER = uuid.uuid4()


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [Role.__table__, LLCRoleTool.__table__, LLCCompanyMembership.__table__]
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
        role = await RoleService().create(session, company_id=company_id, name=name, actor_user_id=_ADMIN_USER)
        await session.commit()
        return role.id


async def _attach(session_factory, company_id: uuid.UUID, role_id: uuid.UUID, tool_name: str) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(LLCRoleTool(company_id=company_id, role_id=role_id, tool_name=tool_name))
        await session.commit()


async def _query(session_factory, company_id: uuid.UUID, caller_org: uuid.UUID | None = None):  # noqa: ANN001, ANN201
    """Call the **real** endpoint, not a copy of its query.

    An earlier draft re-implemented the endpoint's select here. That passes
    forever regardless of what the endpoint actually does — the test and the
    code would have to drift apart before it noticed, which is the one thing it
    exists to notice. Calling the route function also exercises
    ``assert_company_access``, which a bare query never touches.
    """
    ctx = TenantContext(org_id=caller_org or company_id, user_id=_ADMIN_USER, is_platform_admin=False)
    async with session_factory() as session:
        response = await get_tool_nodes(company_id=company_id, session=session, _current_user={}, ctx=ctx)
    return [(n.role_id, n.role_name, n.tool_name) for n in response.nodes]


@pytest.mark.asyncio
async def test_a_role_with_a_tool_becomes_a_tool_node(session_factory):  # noqa: ANN001
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "Head of Sales")
    await _attach(session_factory, company, role_id, "web_search")

    nodes = await _query(session_factory, company)

    assert nodes == [(str(role_id), "Head of Sales", "web_search")]


@pytest.mark.asyncio
async def test_a_role_without_a_tool_produces_no_node(session_factory):  # noqa: ANN001
    """The join is inner on purpose — a role that carries nothing is not a tool node."""
    company = uuid.uuid4()
    await _seed_role(session_factory, company, "Head of Sales")

    assert await _query(session_factory, company) == []


@pytest.mark.asyncio
async def test_another_companys_tools_never_appear(session_factory):  # noqa: ANN001
    """A whole company's tools stay in that company."""
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_b = await _seed_role(session_factory, company_b, "SRE")
    await _attach(session_factory, company_b, role_b, "shell_exec")

    assert await _query(session_factory, company_a) == []
    assert len(await _query(session_factory, company_b)) == 1


@pytest.mark.asyncio
async def test_one_role_may_carry_several_tools(session_factory):  # noqa: ANN001
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    for tool in ("web_search", "shell_exec"):
        await _attach(session_factory, company, role_id, tool)

    nodes = await _query(session_factory, company)

    # Sorted by role then tool, so the canvas order is stable between reads.
    assert [tool for _, _, tool in nodes] == ["shell_exec", "web_search"]


@pytest.mark.asyncio
async def test_one_tool_may_be_carried_by_several_roles(session_factory):  # noqa: ANN001
    """The projection stays flat — grouping into one node per tool is the
    canvas builder's job (`buildToolCanvasNodes`), not this endpoint's."""
    company = uuid.uuid4()
    role_a = await _seed_role(session_factory, company, "Head of Sales")
    role_b = await _seed_role(session_factory, company, "SRE")
    await _attach(session_factory, company, role_a, "web_search")
    await _attach(session_factory, company, role_b, "web_search")

    nodes = await _query(session_factory, company)

    assert sorted(n[0] for n in nodes) == sorted([str(role_a), str(role_b)])
    assert all(n[2] == "web_search" for n in nodes)


@pytest.mark.asyncio
async def test_nodes_are_ordered_by_role_name(session_factory):  # noqa: ANN001
    company = uuid.uuid4()
    for name in ("Team Lead", "Head of Sales"):
        role_id = await _seed_role(session_factory, company, name)
        await _attach(session_factory, company, role_id, f"tool-{name.split()[0].lower()}")

    nodes = await _query(session_factory, company)

    assert [name for _, name, _ in nodes] == ["Head of Sales", "Team Lead"]


@pytest.mark.asyncio
async def test_a_caller_from_another_company_is_refused(session_factory):  # noqa: ANN001
    """404, not an empty list — "not mine" must not be distinguishable from "empty".

    Only reachable because this test calls the route rather than its query; a
    bare select would return [] here and look identical to a working guard.
    """
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_b = await _seed_role(session_factory, company_b, "SRE")
    await _attach(session_factory, company_b, role_b, "shell_exec")

    with pytest.raises(HTTPException) as excinfo:
        await _query(session_factory, company_b, caller_org=company_a)

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_a_cross_wired_attachment_is_excluded(session_factory):  # noqa: ANN001
    """The attachment's own company_id must be checked, not just the role's.

    Both predicates are only distinguishable when they disagree: an attachment
    row claiming company A against a role owned by company B. Every other test
    here seeds them equal, so dropping either predicate leaves those green —
    verified by mutation, which is how this gap was found rather than assumed.

    Such a row should not exist. That is the point: the redundant predicate is
    what stops one corrupt row leaking a tool into another company's canvas.
    """
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_b = await _seed_role(session_factory, company_b, "SRE")
    await _grant_admin(session_factory, company_a)

    # Cross-wired: the attachment claims company A, the role belongs to B.
    await _attach(session_factory, company_a, role_b, "crosswired-tool")

    assert await _query(session_factory, company_a) == []


@pytest.mark.asyncio
async def test_an_attachment_claiming_another_company_is_excluded(session_factory):  # noqa: ANN001
    """The mirror of the case above, and the one the *attachment* predicate owns.

    Cross-wiring has two directions, and each predicate catches exactly one:

    * role in B, attachment claims A  -> caught by ``Role.org_id``
    * role in A, attachment claims B  -> caught by ``LLCRoleTool.company_id``

    Testing only the first left the second predicate free to be deleted with
    every test still green — found by mutating it away and seeing nothing fail.
    """
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_a = await _seed_role(session_factory, company_a, "SRE")

    # Cross-wired the other way: the role belongs to A, the attachment claims B.
    await _attach(session_factory, company_b, role_a, "crosswired-tool")

    assert await _query(session_factory, company_a) == []
