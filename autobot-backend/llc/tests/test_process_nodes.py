# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Process nodes — the contextual entrance to the absorbed automation module (#13963).

Owner decision, option 3: automation is reached from inside Company OS through
the org chart, not through a sidebar entry. A process node is the link between
the role that owns the work and the workflow that performs it.

Derived from ``llc_role_workflows`` rather than stored again, so these tests
pin the projection: a role with no workflow produces no node, and a workflow
attached in another company never appears here. The second one matters most —
the endpoint joins two tables that each carry ``company_id``, and a scoping
predicate that silently matches nothing looks exactly like one that works.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.api.companies import get_process_nodes
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.models.role_workflow import LLCRoleWorkflow
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
    tables = [Role.__table__, LLCRoleWorkflow.__table__, LLCCompanyMembership.__table__]
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


async def _attach(session_factory, company_id: uuid.UUID, role_id: uuid.UUID, workflow_id: str) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(LLCRoleWorkflow(company_id=company_id, role_id=role_id, workflow_id=workflow_id))
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
        response = await get_process_nodes(company_id=company_id, session=session, _current_user={}, ctx=ctx)
    return [(n.role_id, n.role_name, n.workflow_id) for n in response.nodes]


@pytest.mark.asyncio
async def test_a_role_with_a_workflow_becomes_a_process_node(session_factory):  # noqa: ANN001
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "Head of Sales")
    await _attach(session_factory, company, role_id, "wf-quarterly")

    nodes = await _query(session_factory, company)

    assert nodes == [(str(role_id), "Head of Sales", "wf-quarterly")]


@pytest.mark.asyncio
async def test_a_role_without_a_workflow_produces_no_node(session_factory):  # noqa: ANN001
    """The join is inner on purpose — a role that runs nothing is not a process."""
    company = uuid.uuid4()
    await _seed_role(session_factory, company, "Head of Sales")

    assert await _query(session_factory, company) == []


@pytest.mark.asyncio
async def test_another_companys_process_never_appears(session_factory):  # noqa: ANN001
    """A whole company's processes stay in that company."""
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_b = await _seed_role(session_factory, company_b, "SRE")
    await _attach(session_factory, company_b, role_b, "wf-theirs")

    assert await _query(session_factory, company_a) == []
    assert len(await _query(session_factory, company_b)) == 1


@pytest.mark.asyncio
async def test_one_role_may_run_several_workflows(session_factory):  # noqa: ANN001
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    for workflow in ("wf-b", "wf-a"):
        await _attach(session_factory, company, role_id, workflow)

    nodes = await _query(session_factory, company)

    # Sorted by role then workflow, so the canvas order is stable between reads.
    assert [wf for _, _, wf in nodes] == ["wf-a", "wf-b"]


@pytest.mark.asyncio
async def test_nodes_are_ordered_by_role_name(session_factory):  # noqa: ANN001
    company = uuid.uuid4()
    for name in ("Team Lead", "Head of Sales"):
        role_id = await _seed_role(session_factory, company, name)
        await _attach(session_factory, company, role_id, f"wf-{name.split()[0].lower()}")

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
    await _attach(session_factory, company_b, role_b, "wf-theirs")

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
    what stops one corrupt row leaking a workflow into another company's canvas.
    """
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_b = await _seed_role(session_factory, company_b, "SRE")
    await _grant_admin(session_factory, company_a)

    # Cross-wired: the attachment claims company A, the role belongs to B.
    await _attach(session_factory, company_a, role_b, "wf-crosswired")

    assert await _query(session_factory, company_a) == []


@pytest.mark.asyncio
async def test_an_attachment_claiming_another_company_is_excluded(session_factory):  # noqa: ANN001
    """The mirror of the case above, and the one the *attachment* predicate owns.

    Cross-wiring has two directions, and each predicate catches exactly one:

    * role in B, attachment claims A  -> caught by ``Role.org_id``
    * role in A, attachment claims B  -> caught by ``LLCRoleWorkflow.company_id``

    Testing only the first left the second predicate free to be deleted with
    every test still green — found by mutating it away and seeing nothing fail.
    """
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_a = await _seed_role(session_factory, company_a, "SRE")

    # Cross-wired the other way: the role belongs to A, the attachment claims B.
    await _attach(session_factory, company_b, role_a, "wf-crosswired")

    assert await _query(session_factory, company_a) == []
