# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A filed workflow-step approval is scoped to its owner and can be withdrawn (#20917).

Real migrated schema and the real service; the resume handler is a recorder, so a withdrawal that
wrongly resumed the workflow would show.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from services import approval_execution
from services.approval_gate_service import ApprovalGateService
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_PAGE = {"limit": 100, "offset": 0}


async def _none():
    return None


@pytest.fixture
async def env(fresh_db_url, monkeypatch):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, e, a: _none())
    resumed: list[str] = []

    async def handler(approval, session):
        resumed.append(approval.resume_ref)

    monkeypatch.setattr(approval_execution, "_RESUME_HANDLERS", {"workflow_step": handler})
    engine = create_async_engine(fresh_db_url)
    session = AsyncSession(engine, expire_on_commit=False)
    yield ApprovalGateService(session), resumed
    await session.close()
    await engine.dispose()


async def _file(svc):
    return await svc.create_approval(
        title="Workflow step waiting for approval", approval_type="workflow_gate", workflow_id="wf-1",
        workflow_step="s1", source="workflow_step", risk_tier="high", resume_ref="wf-1:s1", owner_user="alice",
    )  # fmt: skip


async def _seen(svc, viewer, is_admin=False):
    return {a.id for a in await svc.list_pending(viewer=viewer, is_admin=is_admin, **_PAGE)}


async def test_owner_and_admin_see_the_step_and_another_user_does_not(env):
    svc, _ = env
    approval = await _file(svc)
    assert await _seen(svc, "alice") == {approval.id}
    assert await _seen(svc, "admin", is_admin=True) == {approval.id}
    assert await _seen(svc, "bob") == set()  # control: not the owner


async def test_withdraw_removes_it_from_the_inbox_without_resuming_the_workflow(env):
    svc, resumed = env
    approval = await _file(svc)
    assert await svc.withdraw(approval.id) is True
    assert await _seen(svc, "alice") == set()
    assert resumed == []
    assert await svc.withdraw(approval.id) is False  # control: only a pending row can be withdrawn


async def test_a_decided_step_cannot_be_withdrawn(env):
    svc, resumed = env
    approval = await _file(svc)
    await svc.approve(approval.id, "alice", author_type="human")
    assert resumed == ["wf-1:s1"]
    assert await svc.withdraw(approval.id) is False
