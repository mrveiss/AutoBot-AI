# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``GET /work-items?assignee_user_id=`` — the human half of the assignee
keyspace (#14192).

Before this, ``WorkItemService.list_by_project`` accepted ``assignee_agent_id``
but had no ``assignee_user_id`` parameter at all, so a human org-chart node's
assigned items could never be fetched through this endpoint even though the
column (``LLCWorkItem.assignee_user_id``, populated since #10532) was always
there and already read elsewhere (``llc/api/companies.py``'s
``_compose_human_nodes``, for the org-chart's own per-person item count).

Mounts the REAL ``work_items`` router over an in-memory SQLite database (the
same harness as ``test_llc_e2e_loop.py``) rather than mocking the session, so
the new ``WHERE`` clause is proven against real rows, not a shape nobody
writes. Covers:

  1. The filter returns only the named user's items, across a multi-row
     fixture with items for two different users AND an agent (no
     cross-assignee contamination).
  2. The pre-existing ``assignee`` (agent) filter is unchanged — behaviour
     preservation for the one line touched in ``list_by_project``.
  3. The filter is scoped by ``company_id`` as well as ``assignee_user_id``:
     the same user id assigned to a work item in a DIFFERENT company never
     leaks through a query scoped to the caller's own company (the SQL-level
     half of the tenant guard; the route-level half — ``assert_company_access``
     rejecting a mismatched ``company_id`` outright — is already covered by
     ``test_work_items_collection_authz.py``).
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator, Optional
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem

# Importing the harness registers the SQLite compile shims and all loop models
# on Base.metadata. Must happen before any model/table is touched.
from llc.tests import _e2e_harness as harness

_FIXED_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


# ---------------------------------------------------------------------------
# Fixtures (mirror test_llc_e2e_loop.py's minimal-mount harness, work-items only).
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
    from fastapi import FastAPI

    from llc.api import work_items as work_items_api
    from user_management.services import TenantContext

    application = FastAPI()
    application.include_router(work_items_api.router, prefix="/api/llc")

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[work_items_api.get_session] = _override_session

    holder = {"company_id": None}

    def _override_current_user() -> dict:
        return {
            "id": str(_FIXED_USER_ID),
            "user_id": str(_FIXED_USER_ID),
            "username": "admin",
            "role": "admin",
            "is_platform_admin": False,
        }

    def _override_tenant() -> TenantContext:
        org = uuid.UUID(holder["company_id"]) if holder["company_id"] else None
        return TenantContext(org_id=org, user_id=_FIXED_USER_ID, is_platform_admin=False)

    from api.user_management.dependencies import get_current_user, require_org_context

    application.dependency_overrides[get_current_user] = _override_current_user
    application.dependency_overrides[require_org_context] = _override_tenant

    application.state.tenant_holder = holder
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:  # noqa: ANN001
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Seed helper.
# ---------------------------------------------------------------------------

_item_counter = 0


async def _seed_work_item(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    *,
    assignee_user_id: Optional[uuid.UUID] = None,
    assignee_agent_id: Optional[uuid.UUID] = None,
    status: str = WorkItemStatus.IN_PROGRESS.value,
) -> str:
    global _item_counter
    _item_counter += 1
    item_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCWorkItem(
                id=item_id,
                company_id=company_id,
                identifier=f"WI-{_item_counter}",
                type=WorkItemType.TASK.value,
                title=f"Test item {_item_counter}",
                status=status,
                priority=WorkItemPriority.MEDIUM.value,
                version=1,
                labels=[],
                assignee_user_id=assignee_user_id,
                assignee_agent_id=assignee_agent_id,
            )
        )
        await session.commit()
    return str(item_id)


@pytest.fixture(autouse=True)
def _stub_kb_collections():
    """GET never touches the KB, but every other test module in this package
    stubs it — kept for parity in case a future test in this file creates one."""
    target = "llc.kb.collections.KbCollectionManager"
    with (
        patch(f"{target}.ensure_collection", new=AsyncMock(return_value="stub:collection")),
        patch(f"{target}.archive_collection", new=AsyncMock(return_value="stub:archived")),
    ):
        yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assignee_user_id_filter_returns_only_that_users_items(app, client, session_factory):  # noqa: ANN001
    """Multi-row fixture: items for two humans and one agent — the filter
    returns exactly the named user's items, nothing else."""
    company_id = uuid.uuid4()
    app.state.tenant_holder["company_id"] = str(company_id)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    agent_id = uuid.uuid4()

    item_a1 = await _seed_work_item(session_factory, company_id, assignee_user_id=user_a)
    item_a2 = await _seed_work_item(session_factory, company_id, assignee_user_id=user_a)
    await _seed_work_item(session_factory, company_id, assignee_user_id=user_b)
    await _seed_work_item(session_factory, company_id, assignee_agent_id=agent_id)

    resp = await client.get(
        "/api/llc/work-items", params={"company_id": str(company_id), "assignee_user_id": str(user_a)}
    )
    assert resp.status_code == 200, resp.text
    returned_ids = {i["id"] for i in resp.json()}
    assert returned_ids == {item_a1, item_a2}


@pytest.mark.asyncio
async def test_assignee_user_id_filter_no_cross_user_contamination(app, client, session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    app.state.tenant_holder["company_id"] = str(company_id)

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    await _seed_work_item(session_factory, company_id, assignee_user_id=user_a)
    item_b = await _seed_work_item(session_factory, company_id, assignee_user_id=user_b)

    resp = await client.get(
        "/api/llc/work-items", params={"company_id": str(company_id), "assignee_user_id": str(user_b)}
    )
    assert resp.status_code == 200, resp.text
    returned_ids = {i["id"] for i in resp.json()}
    assert returned_ids == {item_b}


@pytest.mark.asyncio
async def test_existing_assignee_agent_filter_is_unchanged(app, client, session_factory):  # noqa: ANN001
    """Behaviour preservation: the pre-existing agent filter (`assignee=`)
    still works exactly as before, unaffected by the new parameter."""
    company_id = uuid.uuid4()
    app.state.tenant_holder["company_id"] = str(company_id)

    agent_id = uuid.uuid4()
    other_agent_id = uuid.uuid4()
    user_id = uuid.uuid4()

    item_agent = await _seed_work_item(session_factory, company_id, assignee_agent_id=agent_id)
    await _seed_work_item(session_factory, company_id, assignee_agent_id=other_agent_id)
    await _seed_work_item(session_factory, company_id, assignee_user_id=user_id)

    resp = await client.get("/api/llc/work-items", params={"company_id": str(company_id), "assignee": str(agent_id)})
    assert resp.status_code == 200, resp.text
    returned_ids = {i["id"] for i in resp.json()}
    assert returned_ids == {item_agent}


@pytest.mark.asyncio
async def test_assignee_user_id_filter_is_scoped_by_company(app, client, session_factory):  # noqa: ANN001
    """The SAME user id assigned to a work item in a DIFFERENT company never
    leaks through a query scoped to the caller's own company — the SQL-level
    half of the tenant guard (company_id AND assignee_user_id, not OR)."""
    own_company = uuid.uuid4()
    other_company = uuid.uuid4()
    app.state.tenant_holder["company_id"] = str(own_company)

    shared_user = uuid.uuid4()
    own_item = await _seed_work_item(session_factory, own_company, assignee_user_id=shared_user)
    await _seed_work_item(session_factory, other_company, assignee_user_id=shared_user)

    resp = await client.get(
        "/api/llc/work-items", params={"company_id": str(own_company), "assignee_user_id": str(shared_user)}
    )
    assert resp.status_code == 200, resp.text
    returned_ids = {i["id"] for i in resp.json()}
    assert returned_ids == {own_item}
