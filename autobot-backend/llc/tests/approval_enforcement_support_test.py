# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared fixtures and helpers for the #8214 approval-enforcement tests (SQLite harness, patched edges)."""

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

from llc.models.activity import ActorType  # noqa: F401 -- re-exported for the tests
from llc.models.budget import LLCAgentBudget
from llc.services.approval import ApprovalService
from llc.tests import _e2e_harness as harness
from models.approval import Approval
from user_management.models.organization import Organization

_ORG = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_BOARD = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest_asyncio.fixture
async def session_factory():  # noqa: ANN201
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    from user_management.models.base import Base

    tables = harness.loop_tables() + [Approval.__table__]
    harness._clientside_timestamps(Approval.__table__)
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        eng, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as session:
        session.add(Organization(id=_ORG, name="Co", slug="co", require_approval_for_hires=True))
        await session.commit()
    yield factory
    await eng.dispose()


class _ActivityRecorder:
    """Stands in for ``LLCActivityLogService``: the SQL write is covered by the activity-log tests (#20150)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def record(
        self, session, company_id, actor_type, actor_id, event_type, entity_type, entity_id, **kw
    ):  # noqa: ANN001, ANN201
        self.calls.append((event_type.value, actor_type, actor_id, entity_type, entity_id))


@pytest.fixture
def activity():  # noqa: ANN201
    recorder = _ActivityRecorder()
    with patch("llc.services.approval_hooks._activity", recorder):
        yield recorder


@pytest.fixture(autouse=True)
def _edges(activity):  # noqa: ANN001, ANN201
    """No Redis, no scheduler: the database effects are what these tests are about."""
    with (
        patch("llc.services.approval.get_async_redis_client", new=AsyncMock(return_value=None)),
        patch("llc.services.activity_log.get_async_redis_client", new=AsyncMock(return_value=None)),
        patch("llc.scheduler.schedule_entry.schedule_heartbeat", new_callable=AsyncMock) as sched,
    ):
        yield sched


def _app(session_factory, *, require: bool = True):  # noqa: ANN001, ANN201
    from fastapi import FastAPI

    from api.user_management.dependencies import get_current_user, require_org_context
    from llc.api import agent_hires
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    app = FastAPI()
    app.include_router(agent_hires.router, prefix="/api/llc")

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_BOARD), "auth_method": "session"}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG, user_id=_BOARD, is_platform_admin=False
    )
    return app


async def _hire(session_factory, name: str = "Newbie"):  # noqa: ANN001, ANN202
    transport = httpx.ASGITransport(app=_app(session_factory))
    with (
        patch("llc.api.agent_hires.adapter_unavailable_reason", return_value=None),
        patch("llc.api.agent_hires.registered_adapter_types", return_value=["claude_code"]),
    ):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                f"/api/llc/companies/{_ORG}/agent-hires",
                json={"agent_name": name, "heartbeat_enabled": True, "heartbeat_cron": "* * * * *"},
            )


async def _rows(session_factory, model):  # noqa: ANN001, ANN202
    async with session_factory() as session:
        return list((await session.execute(select(model))).scalars().all())


async def _decide(session_factory, approval_id, decision):  # noqa: ANN001, ANN202
    """What the decide route does: decide, then commit; roll back on any failure."""
    async with session_factory() as session:
        try:
            approval = await ApprovalService().decide(
                session, approval_id=approval_id, decision=decision, decided_by=_BOARD
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await ApprovalService().finish_decision(approval)
    return approval


async def _request(session_factory, gate, payload):  # noqa: ANN001, ANN202
    async with session_factory() as session:
        approval = await ApprovalService().request_approval(
            session, company_id=_ORG, gate_type=gate, payload=payload, requested_by="agent-x", actor_user_id=_BOARD
        )
        await session.commit()
    return approval.id


async def _budget(session_factory, limit: str) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(LLCAgentBudget(company_id=str(_ORG), agent_id="a1", budget_limit=Decimal(limit)))
        await session.commit()


def _board_app(session_factory, *, user_id: uuid.UUID):  # noqa: ANN001, ANN202
    """The approvals router with a real database and a real membership check."""
    from fastapi import FastAPI

    from api.user_management.dependencies import get_current_user, require_org_context
    from llc.api import approvals
    from llc.deps import get_session
    from user_management.services import TenantContext

    app = FastAPI()
    app.include_router(approvals.router, prefix="/api/llc")

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user_id), "auth_method": "session"}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG, user_id=user_id, is_platform_admin=False
    )
    return app


async def _post(app, path: str, body: dict):  # noqa: ANN001, ANN202
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, json=body)


async def _member(session_factory, user_id: uuid.UUID, role: str) -> None:  # noqa: ANN001
    from llc.models.membership import LLCCompanyMembership

    async with session_factory() as session:
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=_ORG, user_id=user_id, role=role))
        await session.commit()
