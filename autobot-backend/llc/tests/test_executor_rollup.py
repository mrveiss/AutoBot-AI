# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Behaviour lock for GET /api/llc/companies/{company_id}/work-items/executor-rollup (#13942, #14222).

Mounts the REAL companies router over the same minimal-mount harness as
``test_llc_org_chart.py`` (in-memory SQLite, dependency overrides for the
session/auth/tenant). Locks:

  1. Counts — the rollup's (executor_class, status) cells match the seeded
     work items exactly, not merely "some number > 0".
  2. Mis-typed discriminator (#13942 AC) — an ``assignee_type`` value the
     ``AssigneeType`` enum never emits ("bogus"), and a *correctly* typed
     "user"/"agent" row whose matching id column is NULL (a dangling
     write), both land in ``unassigned`` — never silently counted as a
     normal person/agent.
  3. The unassigned bucket is real, not a remainder: it is asserted directly
     against known-unassigned rows, not derived by subtracting the other two
     buckets from a total.
  4. Tenant gate — cross-tenant company_id is rejected; a platform admin or a
     matching org_id succeeds.
  5. Orphaned (#14222) — a work item typed/id-assigned to a user whose
     membership was deleted, or to an agent that was terminated, is counted
     as ``orphaned`` — the reproduction the issue asks for, not merely a
     check that ``assignee_type`` is unchanged. A paused agent, and a user
     who is a member of a *different* company, must NOT be orphaned.

Determinism: no network, no Postgres, no Redis — identical to the org-chart
harness this module borrows fixtures from.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import AssigneeType, LLCAgentStatus, WorkItemStatus, WorkItemType
from llc.models.membership import LLCCompanyMembership
from llc.models.work_item import LLCWorkItem
from models.agent_org import AgentOrgNode

# Importing the harness registers the SQLite compile shims and all loop models
# on Base.metadata (including LLCWorkItem).
from llc.tests import _e2e_harness as harness

_FIXED_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


# ---------------------------------------------------------------------------
# Fixtures (mirror test_llc_org_chart.py's harness).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )


@pytest_asyncio.fixture
async def app(session_factory):  # noqa: ANN001, ANN201
    """Minimal FastAPI mounting the REAL companies router under /api/llc."""
    from fastapi import FastAPI

    from llc.api import companies as companies_api
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    application = FastAPI()
    application.include_router(companies_api.router, prefix="/api/llc")

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_async_session] = _override_session

    tenant = {"org_id": None, "is_platform_admin": True}

    def _override_current_user() -> dict:
        return {
            "id": str(_FIXED_USER_ID),
            "user_id": str(_FIXED_USER_ID),
            "username": "admin",
            "role": "admin",
            "is_platform_admin": tenant["is_platform_admin"],
        }

    def _override_tenant() -> TenantContext:
        org = uuid.UUID(tenant["org_id"]) if tenant["org_id"] else None
        return TenantContext(
            org_id=org,
            user_id=_FIXED_USER_ID,
            is_platform_admin=tenant["is_platform_admin"],
        )

    from api.user_management.dependencies import (
        get_current_user,
        get_tenant_context,
        require_org_context,
    )

    application.dependency_overrides[get_current_user] = _override_current_user
    application.dependency_overrides[get_tenant_context] = _override_tenant
    application.dependency_overrides[require_org_context] = _override_tenant

    application.state.tenant = tenant
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:  # noqa: ANN001
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Seed helper — direct ORM insert, bypassing the service layer's AssigneeType
# validation (GH#13937 typed the *write path*; this test needs a row that
# skipped it, to prove the read path is defensive independently).
# ---------------------------------------------------------------------------


async def _seed_item(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    *,
    status: str,
    assignee_type: str | None = None,
    assignee_user_id: uuid.UUID | None = None,
    assignee_agent_id: uuid.UUID | None = None,
) -> None:
    async with session_factory() as session:
        session.add(
            LLCWorkItem(
                id=uuid.uuid4(),
                company_id=company_id,
                type=WorkItemType.TASK.value,
                identifier=f"ROLLUP-{uuid.uuid4().hex[:8]}",
                title="rollup fixture",
                labels=[],
                status=status,
                assignee_type=assignee_type,
                assignee_user_id=assignee_user_id,
                assignee_agent_id=assignee_agent_id,
            )
        )
        await session.commit()


async def _seed_membership(session_factory, company_id: uuid.UUID, user_id: uuid.UUID) -> None:  # noqa: ANN001
    """A live ``llc_company_memberships`` row — makes ``assignee_user_id`` resolve (#14222)."""
    async with session_factory() as session:
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company_id, user_id=user_id))
        await session.commit()


async def _seed_agent_node(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    agent_node_id: uuid.UUID,
    *,
    status: str = LLCAgentStatus.AVAILABLE.value,
) -> None:
    """An ``AgentOrgNode`` row — makes ``assignee_agent_id`` resolve (#14222)."""
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=agent_node_id,
                agent_id=f"agent-{agent_node_id.hex[:8]}",
                name="rollup fixture agent",
                company_id=company_id,
                status=status,
            )
        )
        await session.commit()


def _cell_map(cells: list[dict]) -> dict[tuple[str, str], int]:
    return {(c["executor_class"], c["status"]): c["count"] for c in cells}


# ---------------------------------------------------------------------------
# 1. Exact counts, including the defensive unassigned cases.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_rollup_counts_by_class_and_status(app, client, session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    user_id = uuid.uuid4()
    agent_node_id = uuid.uuid4()
    # (#14222) "cleanly assigned" now also means the assignee resolves: a live
    # membership row for the user, a non-terminated AgentOrgNode for the agent.
    await _seed_membership(session_factory, company_id, user_id)
    await _seed_agent_node(session_factory, company_id, agent_node_id)

    # Two cleanly person-assigned items.
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.BACKLOG.value,
        assignee_type=AssigneeType.USER.value,
        assignee_user_id=user_id,
    )
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.DONE.value,
        assignee_type=AssigneeType.USER.value,
        assignee_user_id=user_id,
    )
    # Three cleanly agent-assigned items (two DONE, one IN_PROGRESS).
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.IN_PROGRESS.value,
        assignee_type=AssigneeType.AGENT.value,
        assignee_agent_id=agent_node_id,
    )
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.DONE.value,
        assignee_type=AssigneeType.AGENT.value,
        assignee_agent_id=agent_node_id,
    )
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.DONE.value,
        assignee_type=AssigneeType.AGENT.value,
        assignee_agent_id=agent_node_id,
    )
    # Two genuinely unassigned items (assignee_type is None — the ordinary case).
    await _seed_item(session_factory, company_id, status=WorkItemStatus.BACKLOG.value)
    await _seed_item(session_factory, company_id, status=WorkItemStatus.READY.value)
    # A mis-typed discriminator: not an AssigneeType member at all.
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.BACKLOG.value,
        assignee_type="bogus",
    )
    # A dangling write: typed "user" but the id column that should back it is
    # NULL — the AC's "does not silently land in a bucket" case.
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.READY.value,
        assignee_type=AssigneeType.USER.value,
        assignee_user_id=None,
    )
    # Same for "agent".
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.READY.value,
        assignee_type=AssigneeType.AGENT.value,
        assignee_agent_id=None,
    )

    resp = await client.get(f"/api/llc/companies/{company_id}/work-items/executor-rollup")
    assert resp.status_code == 200, resp.text
    cells = _cell_map(resp.json()["cells"])

    # Person bucket: exactly the two cleanly-assigned items, nothing more.
    assert cells[(AssigneeType.USER.value, WorkItemStatus.BACKLOG.value)] == 1
    assert cells[(AssigneeType.USER.value, WorkItemStatus.DONE.value)] == 1
    assert (
        cells.get((AssigneeType.USER.value, WorkItemStatus.READY.value), 0) == 0
    ), "the dangling user-typed/NULL-id row must not count as a person"

    # Agent bucket: exactly the three cleanly-assigned items.
    assert cells[(AssigneeType.AGENT.value, WorkItemStatus.IN_PROGRESS.value)] == 1
    assert cells[(AssigneeType.AGENT.value, WorkItemStatus.DONE.value)] == 2
    assert (
        cells.get((AssigneeType.AGENT.value, WorkItemStatus.READY.value), 0) == 0
    ), "the dangling agent-typed/NULL-id row must not count as an agent"

    # Unassigned bucket: the two genuine nulls + the mistyped row + the two
    # dangling rows = 5. Asserted directly, not as a remainder.
    assert (
        cells[("unassigned", WorkItemStatus.BACKLOG.value)] == 2
    ), "one genuine null + one mistyped 'bogus' row, both BACKLOG"
    assert (
        cells[("unassigned", WorkItemStatus.READY.value)] == 3
    ), "one genuine null + the two dangling user/agent rows, all READY"

    total = sum(cells.values())
    assert total == 10, "every seeded item must be counted exactly once"


# ---------------------------------------------------------------------------
# 2. Tenant gate.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_rollup_counts_only_the_requested_company(app, client, session_factory):  # noqa: ANN001
    """The row-level company filter, pinned independently of the route guard.

    The tenant-gate test below only varies `org_id`; it never seeds a *second*
    company, so deleting `.where(LLCWorkItem.company_id == company_id)` would
    leave every assertion in this file green — the in-memory DB holds one
    company's rows and nothing else to leak. That is the same gap #13936's
    review found on the org chart and #13969's on contacts, so it gets its own
    two-company case here rather than a third recurrence.
    """
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    app.state.tenant["is_platform_admin"] = True

    company_a_user_id = uuid.uuid4()
    await _seed_membership(session_factory, company_a, company_a_user_id)
    await _seed_item(
        session_factory,
        company_a,
        status=WorkItemStatus.BACKLOG.value,
        assignee_type=AssigneeType.USER.value,
        assignee_user_id=company_a_user_id,
    )
    # Three items in the other company, deliberately spread across buckets so a
    # leak would be visible in the totals AND in more than one cell.
    for assignee_type, agent_id, user_id in (
        (AssigneeType.AGENT.value, uuid.uuid4(), None),
        (AssigneeType.USER.value, None, uuid.uuid4()),
        (None, None, None),
    ):
        await _seed_item(
            session_factory,
            company_b,
            status=WorkItemStatus.BACKLOG.value,
            assignee_type=assignee_type,
            assignee_agent_id=agent_id,
            assignee_user_id=user_id,
        )

    resp = await client.get(f"/api/llc/companies/{company_a}/work-items/executor-rollup")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert (
        sum(cell["count"] for cell in body["cells"]) == 1
    ), f"company B's work items leaked into company A's rollup: {body}"
    # And specifically: none of company B's three buckets appear at all.
    assert {cell["executor_class"] for cell in body["cells"] if cell["count"]} == {AssigneeType.USER.value}


@pytest.mark.asyncio
async def test_executor_rollup_legacy_untyped_assignee_counts_as_unassigned(
    app, client, session_factory
):  # noqa: ANN001
    """The pre-#13937 row shape: an assignee id with no discriminator.

    `WorkItemService.create()` set no `assignee_type` before #13937, so rows
    exist with a real `assignee_user_id`/`assignee_agent_id` and a NULL
    discriminator. They must land in exactly one bucket and must not vanish
    from the total.
    """
    company_id = uuid.uuid4()
    app.state.tenant["is_platform_admin"] = True

    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.BACKLOG.value,
        assignee_type=None,
        assignee_user_id=uuid.uuid4(),
    )
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.BACKLOG.value,
        assignee_type=None,
        assignee_agent_id=uuid.uuid4(),
    )

    resp = await client.get(f"/api/llc/companies/{company_id}/work-items/executor-rollup")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert sum(cell["count"] for cell in body["cells"]) == 2, f"a legacy row fell out of every bucket: {body}"
    counted = _cell_map(body["cells"])
    assert counted[("unassigned", WorkItemStatus.BACKLOG.value)] == 2


@pytest.mark.asyncio
async def test_executor_rollup_tenant_gate(app, client, session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    other_company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(other_company_id)
    app.state.tenant["is_platform_admin"] = False

    tenant_gate_user_id = uuid.uuid4()
    await _seed_membership(session_factory, company_id, tenant_gate_user_id)
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.BACKLOG.value,
        assignee_type=AssigneeType.USER.value,
        assignee_user_id=tenant_gate_user_id,
    )

    resp = await client.get(f"/api/llc/companies/{company_id}/work-items/executor-rollup")
    assert resp.status_code == 404, "a caller whose org_id does not match company_id must not see the rollup"

    app.state.tenant["is_platform_admin"] = True
    resp = await client.get(f"/api/llc/companies/{company_id}/work-items/executor-rollup")
    assert resp.status_code == 200, "a platform admin may read any company's rollup"
    cells = _cell_map(resp.json()["cells"])
    assert cells[(AssigneeType.USER.value, WorkItemStatus.BACKLOG.value)] == 1


# ---------------------------------------------------------------------------
# 3. An empty company reports an empty rollup, not an error.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_rollup_empty_company(app, client):  # noqa: ANN001
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    resp = await client.get(f"/api/llc/companies/{company_id}/work-items/executor-rollup")
    assert resp.status_code == 200, resp.text
    assert resp.json()["cells"] == []


# ---------------------------------------------------------------------------
# 4. Orphaned (#14222) — the reproduction, not the predicate. Each test seeds
#    a work item that would have passed the OLD (id-presence-only) check,
#    then removes/terminates the assignee and asserts the rollup stops
#    reporting it as owned.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_rollup_reports_orphaned_when_membership_is_deleted(
    app, client, session_factory
):  # noqa: ANN001
    """The reproduction from #14222: seed a user-owned item, delete the membership.

    Mirrors what `membership_service.remove_member` actually does — deletes the
    `llc_company_memberships` row and reassigns nothing (#14221's finding) — by
    never seeding a membership row at all rather than seeding then deleting it;
    the resulting DB state is identical either way, and this is the shorter path
    to it. `assignee_type`/`assignee_user_id` are untouched, so a test that only
    checked those (the OLD bug) would still pass while this one catches it.
    """
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    departed_user_id = uuid.uuid4()
    # No _seed_membership call — the user has no membership row in this company,
    # exactly the state `membership_service` leaves behind after a removal.
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.IN_PROGRESS.value,
        assignee_type=AssigneeType.USER.value,
        assignee_user_id=departed_user_id,
    )

    resp = await client.get(f"/api/llc/companies/{company_id}/work-items/executor-rollup")
    assert resp.status_code == 200, resp.text
    cells = _cell_map(resp.json()["cells"])

    assert (
        cells.get((AssigneeType.USER.value, WorkItemStatus.IN_PROGRESS.value), 0) == 0
    ), "a work item whose assignee has no membership must not be reported as owned"
    assert cells[("orphaned", WorkItemStatus.IN_PROGRESS.value)] == 1


@pytest.mark.asyncio
async def test_executor_rollup_reports_orphaned_when_agent_is_terminated(
    app, client, session_factory
):  # noqa: ANN001
    """The agent-side reproduction: `controls_service.terminate` reassigns nothing (#14221)."""
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    terminated_agent_id = uuid.uuid4()
    await _seed_agent_node(
        session_factory, company_id, terminated_agent_id, status=LLCAgentStatus.TERMINATED.value
    )
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.IN_PROGRESS.value,
        assignee_type=AssigneeType.AGENT.value,
        assignee_agent_id=terminated_agent_id,
    )

    resp = await client.get(f"/api/llc/companies/{company_id}/work-items/executor-rollup")
    assert resp.status_code == 200, resp.text
    cells = _cell_map(resp.json()["cells"])

    assert (
        cells.get((AssigneeType.AGENT.value, WorkItemStatus.IN_PROGRESS.value), 0) == 0
    ), "a work item assigned to a terminated agent must not be reported as owned"
    assert cells[("orphaned", WorkItemStatus.IN_PROGRESS.value)] == 1


@pytest.mark.asyncio
async def test_executor_rollup_paused_agent_still_counts_as_owned(app, client, session_factory):  # noqa: ANN001
    """Paused is recoverable, not gone (#14222's paused-vs-terminated decision).

    A pause is a temporary, resumable state — the owner's framing ("gone" for
    this purpose) applies to termination, not a pause. A paused agent's work
    must still read as owned, not orphaned.
    """
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    paused_agent_id = uuid.uuid4()
    await _seed_agent_node(session_factory, company_id, paused_agent_id, status=LLCAgentStatus.PAUSED.value)
    await _seed_item(
        session_factory,
        company_id,
        status=WorkItemStatus.IN_PROGRESS.value,
        assignee_type=AssigneeType.AGENT.value,
        assignee_agent_id=paused_agent_id,
    )

    resp = await client.get(f"/api/llc/companies/{company_id}/work-items/executor-rollup")
    assert resp.status_code == 200, resp.text
    cells = _cell_map(resp.json()["cells"])

    assert cells[(AssigneeType.AGENT.value, WorkItemStatus.IN_PROGRESS.value)] == 1
    assert cells.get(("orphaned", WorkItemStatus.IN_PROGRESS.value), 0) == 0


@pytest.mark.asyncio
async def test_executor_rollup_membership_in_a_different_company_does_not_count(
    app, client, session_factory
):  # noqa: ANN001
    """Company-scoped existence (#14222): a member of company B is not valid in company A.

    Pinned independently a fourth time (after #13936, #13969, #13942) — the
    existence check this issue adds is exactly the kind of join that can leak
    across the row-level company boundary if it is not scoped.
    """
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_a)
    app.state.tenant["is_platform_admin"] = False

    cross_company_user_id = uuid.uuid4()
    # This user IS a member — just of the other company.
    await _seed_membership(session_factory, company_b, cross_company_user_id)
    await _seed_item(
        session_factory,
        company_a,
        status=WorkItemStatus.IN_PROGRESS.value,
        assignee_type=AssigneeType.USER.value,
        assignee_user_id=cross_company_user_id,
    )

    resp = await client.get(f"/api/llc/companies/{company_a}/work-items/executor-rollup")
    assert resp.status_code == 200, resp.text
    cells = _cell_map(resp.json()["cells"])

    assert (
        cells.get((AssigneeType.USER.value, WorkItemStatus.IN_PROGRESS.value), 0) == 0
    ), "membership in a different company must not make the assignee valid here"
    assert cells[("orphaned", WorkItemStatus.IN_PROGRESS.value)] == 1
