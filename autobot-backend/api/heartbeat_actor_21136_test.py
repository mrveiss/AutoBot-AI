# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pause, resume and terminate record the verified principal id (#21136)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api import heartbeat
from api.schemas_heartbeat import AgentPauseRequest, AgentResumeRequest, AgentTerminateRequest
from models.heartbeat import HeartbeatStatus
from services.audit.taxonomy import AuditAction, action_name

CALLER = {"id": "principal-7", "username": "alice", "role": "admin"}


def _state(status, paused_by=None):
    return SimpleNamespace(
        status=status.value,
        paused_by=paused_by,
        paused_reason=None,
        paused_at=None,
        heartbeat_interval_seconds=60,
    )


@pytest.fixture
def harness(monkeypatch):
    audits = []

    async def _record(event):
        audits.append({"user_id": event.actor_id, "action": event.action, "resource_id": event.resource_id})
        return True

    monkeypatch.setattr(heartbeat, "record_committed", _record)
    monkeypatch.setattr(heartbeat, "_state_to_response", lambda state, *a: state)
    session = MagicMock(commit=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(heartbeat, "_paused_by_name", AsyncMock(return_value=None))
    scheduler = MagicMock(disable_agent=AsyncMock(), enable_agent=AsyncMock())

    def install(state):
        monkeypatch.setattr(heartbeat, "_get_or_create_state", AsyncMock(return_value=state))

    return audits, session, scheduler, install


@pytest.mark.asyncio
async def test_pause_records_principal_and_ignores_forged_body_actor(harness):
    audits, session, scheduler, install = harness
    state = _state(HeartbeatStatus.ACTIVE)
    install(state)
    body = AgentPauseRequest(reason="r", paused_by="system:forged")
    await heartbeat.pause_agent("a1", body, session, scheduler, CALLER)
    assert state.paused_by == "principal-7"
    assert audits[0]["user_id"] == "principal-7"
    assert audits[0]["action"] == action_name(AuditAction.AGENT_PAUSE)
    assert audits[0]["resource_id"] == "a1"


@pytest.mark.asyncio
async def test_resume_emits_audit_event_naming_caller(harness):
    audits, session, scheduler, install = harness
    install(_state(HeartbeatStatus.PAUSED, paused_by="principal-1"))
    await heartbeat.resume_agent("a1", AgentResumeRequest(), session, scheduler, CALLER)
    assert audits[0]["user_id"] == "principal-7"
    assert audits[0]["action"] == action_name(AuditAction.AGENT_RESUME)


@pytest.mark.asyncio
async def test_terminate_stores_principal_id_not_username(harness):
    audits, session, scheduler, install = harness
    state = _state(HeartbeatStatus.ACTIVE)
    install(state)
    await heartbeat.terminate_agent("a1", AgentTerminateRequest(reason="r"), session, scheduler, CALLER)
    assert state.paused_by == "principal-7"
    assert audits[0]["action"] == action_name(AuditAction.AGENT_TERMINATE)


def test_actor_falls_back_to_username_without_principal_claim():
    assert heartbeat._actor_id({"username": "svc"}) == "svc"


@pytest.mark.asyncio
async def test_event_is_written_after_the_commit(harness):
    audits, session, scheduler, install = harness
    install(_state(HeartbeatStatus.ACTIVE))
    session.commit.side_effect = lambda: audits.append("commit")
    await heartbeat.pause_agent("a1", AgentPauseRequest(reason="r"), session, scheduler, CALLER)
    assert audits[0] == "commit"
    assert audits[1]["action"] == action_name(AuditAction.AGENT_PAUSE)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["pause", "resume", "terminate"])
async def test_failed_commit_emits_no_event(harness, route):
    audits, session, scheduler, install = harness
    paused = HeartbeatStatus.PAUSED if route == "resume" else HeartbeatStatus.ACTIVE
    install(_state(paused, paused_by="principal-1"))
    session.commit.side_effect = RuntimeError("db down")
    bodies = {"pause": AgentPauseRequest(), "resume": AgentResumeRequest(), "terminate": AgentTerminateRequest()}
    handler = getattr(heartbeat, f"{route}_agent")
    with pytest.raises(HTTPException):
        await handler("a1", bodies[route], session, scheduler, CALLER)
    assert audits == []


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", [None, "system:budget", "alice-legacy"])
async def test_paused_by_name_is_none_without_a_user_id(actor):
    session = MagicMock(execute=AsyncMock())
    assert await heartbeat._paused_by_name(session, actor) is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_paused_by_name_resolves_from_the_user_record():
    row = SimpleNamespace(display_name="Alice A", username="alice")
    session = MagicMock(execute=AsyncMock(return_value=MagicMock(one_or_none=lambda: row)))
    uid = "11111111-1111-1111-1111-111111111111"
    assert await heartbeat._paused_by_name(session, uid) == "Alice A"
