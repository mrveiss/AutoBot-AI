# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""End-to-end proof of the AutoBot LLC core loop.

This single test drives the LLC loop over httpx against the REAL FastAPI
routers and REAL services, backed by an in-memory SQLite database with the
auth/tenant dependencies overridden. It is the operational definition of
"the LLC core loop works":

    create company
      → hire agent
        → create work item
          → record an agent run + a cost event
            → review-gate approve (agent hands off to human, human approves)
              → work item transitions to DONE
                → budget reflects the cost

Determinism: no network, no Postgres, no Redis. Redis client calls inside the
services degrade to no-ops (the async client returns ``None`` without a server)
and the SharedRuntimeBag budget cache swallows its own write errors, so the
DB row read back through ``GET /budget/{agent_id}`` is authoritative.

App path: this test uses the MINIMAL-MOUNT path — it builds a bare
``FastAPI()`` and mounts the real LLC routers under ``/api/llc``. The
production ``app_factory.create_app()`` cannot boot in-process here: its
lifespan hard-requires Postgres/Redis (and the dev venv lacks ~36 deps), which
would make the test non-deterministic. Mounting the real routers keeps the
HTTP surface, routing, request/response schemas, services and DB layer fully
real — only the process bootstrap is bypassed.

Steps seeded directly through the test session (no public endpoint exists that
works against a ``create_all`` schema):
  * hire agent — ``POST /companies/{id}/agent-hires`` INSERTs columns
    (model/adapter_config/heartbeat_*) that only exist via Alembic migrations,
    not on the ``AgentOrgNode`` ORM model, so they are absent from a
    ``create_all`` schema. We INSERT the ``AgentOrgNode`` row the loop needs.
  * per-agent budget row — there is no "create budget" endpoint; budgets are
    seeded out-of-band (e.g. on hire in production). We INSERT one
    ``LLCAgentBudget`` row so the cost-ingest endpoint has a row to update.
  * agent run record — there is no public POST to record a heartbeat run; the
    scheduler writes ``LLCHeartbeatRun`` rows directly. We INSERT one to prove
    "run recorded". Every other loop step goes through httpx.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.budget import LLCAgentBudget
from llc.models.enums import HeartbeatInvocationSource, LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun

# Importing the harness registers the SQLite compile shims and all loop models
# on Base.metadata. Must happen before any model/table is touched.
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode, OrgRole

# A model present in MODEL_PRICING_PER_1M_TOKENS so the cost is non-zero.
_COST_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    """In-memory SQLite engine with the loop schema created."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def app(session_factory):  # noqa: ANN001, ANN201
    """Minimal FastAPI mounting the REAL LLC routers under /api/llc."""
    from fastapi import FastAPI

    from llc.api import budget as budget_api
    from llc.api import companies as companies_api
    from llc.api import work_items as work_items_api
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    application = FastAPI()
    application.include_router(companies_api.router, prefix="/api/llc")
    application.include_router(work_items_api.router, prefix="/api/llc")
    application.include_router(budget_api.router, prefix="/api/llc")

    async def _override_session() -> AsyncIterator[AsyncSession]:
        # Mirror the real user_management.database.get_async_session: commit on
        # successful exit, rollback on error. The budget/companies endpoints
        # rely on this dependency-level commit (they do not commit themselves);
        # the work_items endpoints commit explicitly, so the extra commit here
        # is a harmless no-op for them.
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # companies + budget routers depend on get_async_session;
    # work_items router uses its own get_session helper.
    application.dependency_overrides[get_async_session] = _override_session
    application.dependency_overrides[work_items_api.get_session] = _override_session

    # Auth + tenant overrides: a fixed admin user whose org context == company.
    # company_id is set on the holder so require_org_context returns it.
    holder = {"company_id": None}

    def _override_current_user() -> dict:
        return {
            "id": str(_FIXED_USER_ID),
            "user_id": str(_FIXED_USER_ID),
            "username": "admin",
            "role": "admin",
            "is_platform_admin": True,
        }

    def _override_tenant() -> TenantContext:
        org = uuid.UUID(holder["company_id"]) if holder["company_id"] else None
        return TenantContext(org_id=org, user_id=_FIXED_USER_ID, is_platform_admin=True)

    from api.user_management.dependencies import (
        get_current_user,
        get_tenant_context,
        require_org_context,
    )

    application.dependency_overrides[get_current_user] = _override_current_user
    application.dependency_overrides[get_tenant_context] = _override_tenant
    application.dependency_overrides[require_org_context] = _override_tenant

    # Hand the holder dict to the test via app state so it can set the company id.
    application.state.tenant_holder = holder
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:  # noqa: ANN001
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


_FIXED_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture(autouse=True)
def _stub_kb_collections():
    """Neutralise ChromaDB KB collection side effects on create/transition.

    Company-create and work-item lifecycle endpoints call out to a ChromaDB
    knowledge base to provision/archive a per-entity collection. ChromaDB is an
    external dependency unrelated to the LLC business loop under test, so its
    collection management is stubbed to async no-ops. The loop's persistence
    and state machine remain fully real.
    """
    target = "llc.kb.collections.KbCollectionManager"
    with (
        patch(f"{target}.ensure_collection", new=AsyncMock(return_value="stub:collection")),
        patch(f"{target}.archive_collection", new=AsyncMock(return_value="stub:archived")),
    ):
        yield


# ---------------------------------------------------------------------------
# Direct-seed helpers (documented in the module docstring)
# ---------------------------------------------------------------------------


async def _seed_agent(session_factory, company_id: str) -> str:  # noqa: ANN001
    """Seed an AgentOrgNode (the "hired" agent) and return its agent_id."""
    agent_id = str(uuid.uuid4())
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=uuid.uuid4(),
                agent_id=agent_id,
                name="Worker One",
                org_role=OrgRole.WORKER.value,
                title="Engineer",
                company_id=uuid.UUID(company_id),
            )
        )
        await session.commit()
    return agent_id


async def _seed_budget(session_factory, company_id: str, agent_id: str) -> None:  # noqa: ANN001
    """Seed a per-agent dollar budget row so cost-ingest has a row to update."""
    async with session_factory() as session:
        session.add(
            LLCAgentBudget(
                id=uuid.uuid4(),
                company_id=company_id,
                agent_id=agent_id,
                budget_mode="dollars",
                budget_limit=Decimal("100.000000"),
                budget_spent=Decimal("0.000000"),
                tokens_spent=0,
                alert_threshold=0.8,
            )
        )
        await session.commit()


async def _seed_run(session_factory, company_id: str, agent_id: str, work_item_id: str) -> str:  # noqa: ANN001
    """Seed an LLCHeartbeatRun row (proves an agent run was recorded)."""
    run_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCHeartbeatRun(
                id=run_id,
                company_id=uuid.UUID(company_id),
                agent_id=agent_id,
                invocation_source=HeartbeatInvocationSource.SCHEDULER.value,
                status=LLCRunStatus.COMPLETED.value,
                work_item_id=uuid.UUID(work_item_id),
            )
        )
        await session.commit()
    return str(run_id)


# ---------------------------------------------------------------------------
# The end-to-end loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llc_core_loop_end_to_end(app, client, session_factory):  # noqa: ANN001
    # ---- 1. create company (PUBLIC: POST /api/llc/companies/) --------------
    create_resp = await client.post(
        "/api/llc/companies/",
        json={"name": "Acme LLC", "slug": "acme-llc", "issue_prefix": "ACM"},
    )
    assert create_resp.status_code == 201, create_resp.text
    company = create_resp.json()
    company_id = company["id"]
    assert company["name"] == "Acme LLC"
    assert company["llc_status"] == "onboarding"

    # Wire the tenant context to this company (org_id IS the company id).
    app.state.tenant_holder["company_id"] = company_id

    # company is readable through the public GET
    get_resp = await client.get(f"/api/llc/companies/{company_id}")
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["id"] == company_id

    # ---- 2. hire agent (SEEDED — see module docstring) --------------------
    agent_id = await _seed_agent(session_factory, company_id)

    # ---- 3. create work item (PUBLIC: POST /api/llc/work-items) -----------
    wi_resp = await client.post(
        "/api/llc/work-items",
        json={
            "company_id": company_id,
            "type": "task",
            "title": "Ship the LLC loop",
            "description": "Prove the core loop end to end.",
            "priority": "high",
        },
    )
    assert wi_resp.status_code == 201, wi_resp.text
    work_item = wi_resp.json()
    work_item_id = work_item["id"]
    assert work_item["status"] == "backlog"
    assert work_item["title"] == "Ship the LLC loop"

    # ---- 4a. record an agent run (SEEDED — no public POST) ----------------
    run_id = await _seed_run(session_factory, company_id, agent_id, work_item_id)
    async with session_factory() as session:
        run_row = (
            await session.execute(select(LLCHeartbeatRun).where(LLCHeartbeatRun.id == uuid.UUID(run_id)))
        ).scalar_one()
        assert run_row.work_item_id == uuid.UUID(work_item_id)
        assert run_row.status == LLCRunStatus.COMPLETED.value

    # ---- 4b. record a cost event (PUBLIC: POST /budget/{id}/ingest) -------
    await _seed_budget(session_factory, company_id, agent_id)

    budget_before = await client.get(f"/api/llc/budget/{agent_id}")
    assert budget_before.status_code == 200, budget_before.text
    spent_before = Decimal(str(budget_before.json()["budget_spent"]))
    assert spent_before == Decimal("0")

    ingest_resp = await client.post(
        f"/api/llc/budget/{agent_id}/ingest",
        json={"tokens_in": 100_000, "tokens_out": 50_000, "model": _COST_MODEL},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    cost = Decimal(str(ingest_resp.json()["cost"]))
    # (100000 * 0.8 + 50000 * 4.0) / 1_000_000 = 0.28
    assert cost == Decimal("0.28"), cost

    # ---- 5. review-gate approve --------------------------------------------
    # 5a. agent checks the item out (PUBLIC) → IN_PROGRESS, assigned to agent.
    checkout_resp = await client.post(
        f"/api/llc/work-items/{work_item_id}/checkout",
        json={"agent_id": agent_id, "run_id": run_id},
    )
    assert checkout_resp.status_code == 200, checkout_resp.text
    assert checkout_resp.json()["status"] == "in_progress"
    assert checkout_resp.json()["assignee_agent_id"] == agent_id

    # 5b. agent hands off to a human reviewer (PUBLIC) → IN_REVIEW.
    handoff_resp = await client.post(
        f"/api/llc/work-items/{work_item_id}/handoff/to-human",
        json={
            "agent_id": agent_id,
            "reviewer_user_id": str(_FIXED_USER_ID),
            "company_id": company_id,
            "agent_notes": "Work complete, ready for review.",
        },
    )
    assert handoff_resp.status_code == 200, handoff_resp.text
    handoff = handoff_resp.json()
    assert handoff["status"] == "in_review"
    assert handoff["reviewer_user_id"] == str(_FIXED_USER_ID)

    # 5c. human reviewer approves (PUBLIC) → DONE.
    approve_resp = await client.post(
        f"/api/llc/work-items/{work_item_id}/review/approve",
        json={"reviewer_user_id": str(_FIXED_USER_ID), "company_id": company_id},
    )
    assert approve_resp.status_code == 200, approve_resp.text
    approved = approve_resp.json()

    # ---- 6. work item transitioned to DONE --------------------------------
    assert approved["status"] == "done", approved
    assert approved["completed_at"] is not None

    # Confirm via a fresh GET that the persisted state is DONE.
    final_get = await client.get(f"/api/llc/work-items/{work_item_id}")
    assert final_get.status_code == 200, final_get.text
    assert final_get.json()["status"] == "done"

    # ---- 7. budget reflects the cost --------------------------------------
    budget_after = await client.get(f"/api/llc/budget/{agent_id}")
    assert budget_after.status_code == 200, budget_after.text
    after = budget_after.json()
    spent_after = Decimal(str(after["budget_spent"]))
    assert spent_after == spent_before + cost == Decimal("0.28"), after
    assert after["tokens_spent"] == 150_000
    assert after["is_over_limit"] is False
