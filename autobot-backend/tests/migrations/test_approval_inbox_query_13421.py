# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The approval inbox and its decisions against a real migrated schema (#13421 S1, #18413, #18412)."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from autobot_shared.time_utils import now_utc
from models.approval import Approval
from services import approval_execution
from services.approval_gate_service import ApprovalGateService
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_PAGE = {"limit": 100, "offset": 0}  # larger than any row count seeded here


async def _none():
    return None


@pytest.fixture
async def env(fresh_db_url, monkeypatch):
    """A migrated database, a session factory, and a recording resume handler for agent_tool."""
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, e, a: _none())
    resumed: list[tuple[str, str]] = []

    async def handler(approval, session):
        resumed.append((approval.status, approval.resume_ref))

    monkeypatch.setattr(approval_execution, "_RESUME_HANDLERS", {"agent_tool": handler})
    engine = create_async_engine(fresh_db_url)
    sessions: list[AsyncSession] = []

    def service() -> ApprovalGateService:
        session = AsyncSession(engine, expire_on_commit=False)
        sessions.append(session)
        return ApprovalGateService(session)

    yield service, resumed
    for session in sessions:
        await session.close()
    await engine.dispose()


async def _tool(svc, owner="alice", **over):
    fields = dict(
        title="tool", approval_type="destructive_action", source="agent_tool", risk_tier="high",
        resume_ref="call-1", owner_user=owner,
    )  # fmt: skip
    return await svc.create_approval(**{**fields, **over})


async def _pending(svc, viewer="alice", is_admin=False, **kw):
    return {a.id for a in await svc.list_pending(viewer=viewer, is_admin=is_admin, **_PAGE, **kw)}


async def test_pending_spans_sources_and_excludes_decided_and_company_rows(env):
    service, _ = env
    svc = service()
    legacy = await svc.create_approval(title="legacy", approval_type="workflow_gate")
    tool = await _tool(svc, risk_tier="critical", resume_ref=None)
    plugin = await svc.create_approval(
        title="p", approval_type="resource_request", source="plugin_capability", risk_tier="low", owner_user="alice"
    )
    done = await _tool(svc, resume_ref=None)
    await svc.reject(done.id, "alice", author_type="human")
    svc.session.add(Approval(title="llc", approval_type="hire", status="pending", company_id=uuid.uuid4()))
    await svc.session.commit()

    assert await _pending(svc) == {legacy.id, tool.id, plugin.id}
    assert await _pending(svc, source="agent_tool") == {tool.id}
    assert await _pending(svc, risk_tier="low") == {plugin.id}
    assert await _pending(svc, source="agent_tool", risk_tier="low") == set()


async def test_a_user_sees_only_their_own_sourced_approvals_and_an_admin_sees_all(env):
    """#18413 AC1: the cross-user case."""
    service, _ = env
    svc = service()
    legacy = await svc.create_approval(title="legacy", approval_type="workflow_gate")
    alices = await _tool(svc, owner="alice", resume_ref=None)
    bobs = await _tool(svc, owner="bob", resume_ref=None)

    assert await _pending(svc, viewer="alice") == {legacy.id, alices.id}
    assert await _pending(svc, viewer="bob") == {legacy.id, bobs.id}
    assert await _pending(svc, viewer="mallory") == {legacy.id}
    assert await _pending(svc, viewer=None) == {legacy.id}
    assert await _pending(svc, viewer="root", is_admin=True) == {legacy.id, alices.id, bobs.id}


async def test_a_sourced_row_with_no_owner_is_visible_to_nobody_but_an_admin(env):
    service, _ = env
    svc = service()
    orphan = await _tool(svc, resume_ref=None)
    await svc.session.execute(update(Approval).where(Approval.id == orphan.id).values(owner_user=None))
    await svc.session.commit()
    assert await _pending(svc, viewer="alice") == set()
    assert await _pending(svc, viewer="root", is_admin=True) == {orphan.id}


@pytest.mark.parametrize("method,final", [("approve", "approved"), ("reject", "rejected")])
async def test_every_decision_resumes_the_source_with_the_final_status(env, method, final):
    service, resumed = env
    svc = service()
    row = await _tool(svc, resume_ref="call-9")
    await getattr(svc, method)(row.id, "alice", author_type="human")
    assert resumed == [(final, "call-9")]


async def test_an_approval_without_a_resume_ref_resumes_nothing(env):
    service, resumed = env
    svc = service()
    row = await _tool(svc, resume_ref=None)
    await svc.reject(row.id, "alice", author_type="human")
    assert resumed == []


async def _raced(coro_fns):
    """Run the decisions so each is past its own setup and released together by a barrier."""
    barrier = asyncio.Barrier(len(coro_fns))

    async def go(fn):
        await barrier.wait()
        return await fn()

    return await asyncio.gather(*(go(fn) for fn in coro_fns), return_exceptions=True)


async def test_two_concurrent_approves_resume_exactly_once(env):
    """#18413 AC2: the loser matches no row, raises, and does not resume."""
    service, resumed = env
    row = await _tool(service(), resume_ref="call-race")
    a, b = service(), service()
    results = await _raced(
        [lambda: a.approve(row.id, "alice", author_type="human"), lambda: b.approve(row.id, "bob", author_type="human")]
    )
    assert sum(not isinstance(r, BaseException) for r in results) == 1, results
    assert sum(isinstance(r, ValueError) for r in results) == 1, results
    assert resumed == [("approved", "call-race")]


async def test_a_concurrent_approve_and_reject_decide_once(env):
    service, resumed = env
    row = await _tool(service(), resume_ref="call-race2")
    a, b = service(), service()
    results = await _raced(
        [lambda: a.approve(row.id, "alice", author_type="human"), lambda: b.reject(row.id, "bob", author_type="human")]
    )
    assert sum(not isinstance(r, BaseException) for r in results) == 1
    assert len(resumed) == 1


async def test_deciding_a_decided_approval_is_still_refused(env):
    service, resumed = env
    svc = service()
    row = await _tool(svc)
    await svc.approve(row.id, "alice", author_type="human")
    with pytest.raises(ValueError, match="Cannot transition"):
        await svc.reject(row.id, "alice", author_type="human")
    assert len(resumed) == 1


async def _backdate(svc, approval_id, delta):
    """Move expires_at relative to now; creation refuses a past expiry, as it should."""
    await svc.session.execute(update(Approval).where(Approval.id == approval_id).values(expires_at=now_utc() + delta))
    await svc.session.commit()


async def test_a_past_expiry_approve_is_refused_expired_and_resumed_as_expired(env):
    """#18412 AC1 and AC3 (refusal)."""
    service, resumed = env
    svc = service()
    row = await _tool(svc, expires_at=now_utc() + timedelta(hours=1), resume_ref="call-exp")
    await _backdate(svc, row.id, timedelta(seconds=-5))
    with pytest.raises(ValueError, match="expired"):
        await svc.approve(row.id, "alice", author_type="human")
    stored = await service().get(row.id)
    assert stored.status == "expired"
    assert resumed == [("expired", "call-exp")]


async def test_an_approve_just_before_expiry_succeeds(env):
    """#18412 AC3 (success side)."""
    service, resumed = env
    svc = service()
    row = await _tool(svc, expires_at=now_utc() + timedelta(hours=1), resume_ref="call-ok")
    await _backdate(svc, row.id, timedelta(minutes=5))
    assert (await svc.approve(row.id, "alice", author_type="human")).status == "approved"
    assert resumed == [("approved", "call-ok")]


async def test_expired_rows_leave_the_pending_list_and_the_sweeper_resumes_them_once(env):
    service, resumed = env
    svc = service()
    stale = await _tool(svc, expires_at=now_utc() + timedelta(hours=1), resume_ref="call-s")
    fresh = await _tool(svc, expires_at=now_utc() + timedelta(hours=1), resume_ref=None)
    await _backdate(svc, stale.id, timedelta(seconds=-5))

    assert await _pending(svc) == {fresh.id}, "hidden before any sweep"
    assert await svc.expire_stale() == 1
    assert await svc.expire_stale() == 0, "a second sweep claims nothing and resumes nothing"
    assert resumed == [("expired", "call-s")]
