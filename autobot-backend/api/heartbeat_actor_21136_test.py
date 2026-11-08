# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pause, resume and terminate record the verified principal id (#21136)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api import heartbeat
from api.schemas_system import AgentPauseRequest, AgentResumeRequest, AgentTerminateRequest
from models.heartbeat import HeartbeatStatus
from services.audit.audit import AuditAction

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
    monkeypatch.setattr(heartbeat, "audit_record", lambda **kw: audits.append(kw))
    monkeypatch.setattr(heartbeat, "_state_to_response", lambda state: state)
    session = MagicMock(commit=AsyncMock(), refresh=AsyncMock())
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
    assert audits[0]["action"] == AuditAction.AGENT_PAUSE
    assert audits[0]["resource_id"] == "a1"


@pytest.mark.asyncio
async def test_resume_emits_audit_event_naming_caller(harness):
    audits, session, scheduler, install = harness
    install(_state(HeartbeatStatus.PAUSED, paused_by="principal-1"))
    await heartbeat.resume_agent("a1", AgentResumeRequest(), session, scheduler, CALLER)
    assert audits[0]["user_id"] == "principal-7"
    assert audits[0]["action"] == AuditAction.AGENT_RESUME


@pytest.mark.asyncio
async def test_terminate_stores_principal_id_not_username(harness):
    audits, session, scheduler, install = harness
    state = _state(HeartbeatStatus.ACTIVE)
    install(state)
    await heartbeat.terminate_agent("a1", AgentTerminateRequest(reason="r"), session, scheduler, CALLER)
    assert state.paused_by == "principal-7"
    assert audits[0]["action"] == AuditAction.AGENT_TERMINATE


def test_actor_falls_back_to_username_without_principal_claim():
    assert heartbeat._actor_id({"username": "svc"}) == "svc"
