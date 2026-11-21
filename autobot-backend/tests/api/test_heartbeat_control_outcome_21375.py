# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pause, resume and terminate never leave the audit trail claiming a change that did not happen (#21375)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from api import heartbeat
from api.heartbeat_controls import RECONCILE_FAILED, SCHEDULER_FAILED_DETAIL, SUPERSEDED
from api.heartbeat_scope import AgentScope
from api.schemas_heartbeat import AgentPauseRequest, AgentResumeRequest, AgentTerminateRequest
from models.heartbeat import HeartbeatStatus
from services.audit import outcome
from services.audit.outcome import OUTCOME_MISSING_MARKER
from services.heartbeat_scheduler import _get_or_create_state

CALLER = {"id": "principal-7", "username": "alice", "role": "admin"}
SCOPE = AgentScope(company_id=None, platform_admin=True)
ROUTES = ["pause", "resume", "terminate"]
BODIES = {"pause": AgentPauseRequest, "resume": AgentResumeRequest, "terminate": AgentTerminateRequest}


def _state(route: str):
    paused = route == "resume"
    return SimpleNamespace(
        agent_id="a1",
        status=(HeartbeatStatus.PAUSED if paused else HeartbeatStatus.ACTIVE).value,
        paused_by="principal-1" if paused else None,
        paused_reason="old" if paused else None,
        paused_at="then" if paused else None,
        heartbeat_interval_seconds=60,
    )


@pytest.fixture
def harness(monkeypatch):
    rows: list = []

    async def _record(event):
        rows.append(SimpleNamespace(id=event.id, action=event.action, outcome=event.outcome, meta=event.metadata))
        return True

    monkeypatch.setattr(outcome, "record_committed", _record)
    monkeypatch.setattr(heartbeat, "_state_to_response", lambda state, *a: state)
    monkeypatch.setattr(heartbeat, "_paused_by_name", AsyncMock(return_value=None))
    session = MagicMock(commit=AsyncMock(), refresh=AsyncMock(), rollback=AsyncMock())
    scheduler = MagicMock(disable_agent=AsyncMock(), enable_agent=AsyncMock())
    get_state = AsyncMock()
    monkeypatch.setattr(heartbeat, "_get_or_create_state", get_state)

    async def call(route, state):
        get_state.return_value = state
        handler = getattr(heartbeat, f"{route}_agent")
        return await handler("a1", BODIES[route](), session, scheduler, SCOPE, CALLER)

    return SimpleNamespace(rows=rows, session=session, scheduler=scheduler, get_state=get_state, call=call)


def _outcomes(harness) -> list[str]:
    return [r.outcome for r in harness.rows]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_success_leaves_an_attempt_and_a_linked_success_row(harness, route):
    await harness.call(route, _state(route))
    assert _outcomes(harness) == ["attempted", "success"]
    assert harness.rows[1].meta["attempt_id"] == harness.rows[0].id
    assert harness.rows[1].id != harness.rows[0].id


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_a_failed_state_commit_leaves_a_failed_row_not_a_success(harness, route):
    harness.session.commit.side_effect = ConnectionError("db down")
    with pytest.raises(HTTPException) as exc:  # with_error_handling answers an unexpected error as a 500
        await harness.call(route, _state(route))
    assert exc.value.status_code == 500
    assert _outcomes(harness) == ["attempted", "failed"]
    assert harness.rows[1].meta["failure"] == "ConnectionError"
    harness.session.rollback.assert_awaited_once()
    harness.scheduler.disable_agent.assert_not_called()
    harness.scheduler.enable_agent.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_a_scheduler_failure_is_surfaced_and_the_row_is_restored(harness, route):
    harness.scheduler.disable_agent.side_effect = RuntimeError("loop gone")
    harness.scheduler.enable_agent.side_effect = RuntimeError("loop gone")
    state = _state(route)
    before = dict(vars(state))
    with pytest.raises(HTTPException) as exc:
        await harness.call(route, state)
    assert (exc.value.status_code, exc.value.detail) == (503, SCHEDULER_FAILED_DETAIL)
    assert vars(state) == before  # the row matches the loop, which did not change
    assert _outcomes(harness) == ["attempted", "failed"]
    assert harness.rows[1].meta["failure"] == "RuntimeError"


@pytest.mark.asyncio
async def test_a_failed_restore_is_recorded_as_a_reconcile_failure(harness):
    harness.scheduler.disable_agent.side_effect = RuntimeError("loop gone")
    harness.session.commit.side_effect = [None, ConnectionError("db down")]
    with pytest.raises(HTTPException) as exc:
        await harness.call("pause", _state("pause"))
    assert exc.value.status_code == 503
    assert harness.rows[-1].meta["failure"] == RECONCILE_FAILED
    harness.session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failed_scheduler_call_does_not_overwrite_a_newer_control(harness):
    harness.scheduler.disable_agent.side_effect = RuntimeError("loop gone")
    state = _state("pause")

    calls = []

    async def _newer_control_committed(obj, **kwargs):
        calls.append(kwargs)
        if kwargs:  # the restore's re-lock sees what a concurrent control committed meanwhile
            obj.status, obj.paused_by = HeartbeatStatus.TERMINATED.value, "principal-9"

    harness.session.refresh.side_effect = _newer_control_committed
    with pytest.raises(HTTPException) as exc:
        await harness.call("pause", state)
    assert exc.value.status_code == 503
    assert (state.status, state.paused_by) == (HeartbeatStatus.TERMINATED.value, "principal-9")
    assert harness.rows[-1].meta["failure"] == SUPERSEDED
    assert calls[-1] == {"with_for_update": True}  # the restore re-takes the row lock
    harness.session.rollback.assert_awaited_once()  # the lock is released without writing


@pytest.mark.asyncio
async def test_a_missing_outcome_row_is_logged_with_a_findable_marker(harness, monkeypatch, caplog):
    async def _only_the_attempt(event):
        harness.rows.append(event)
        return event.outcome == "attempted"

    monkeypatch.setattr(outcome, "record_committed", _only_the_attempt)
    await harness.call("pause", _state("pause"))
    (line,) = [r.getMessage() for r in caplog.records if OUTCOME_MISSING_MARKER in r.getMessage()]
    attempt = harness.rows[0]
    assert f"attempt_id={attempt.id}" in line and "agent=a1" in line and "control=agent.pause" in line


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_the_state_row_is_locked_before_the_audit_row(harness, route):
    await harness.call(route, _state(route))
    harness.get_state.assert_awaited_once_with(harness.session, "a1", for_update=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["pause", "terminate"])
async def test_a_second_request_for_the_same_transition_audits_nothing(harness, route):
    state = _state(route)
    await harness.call(route, state)  # the first request commits the transition and releases the lock
    harness.rows.clear()
    again = await harness.call(route, state)  # the second reads the committed state under the lock
    assert again is state
    assert harness.rows == []


@pytest.mark.asyncio
async def test_for_update_takes_the_row_lock():
    captured = []

    async def _execute(stmt):
        captured.append(str(stmt.compile(dialect=postgresql.dialect())))
        return MagicMock(scalar_one_or_none=lambda: object())

    session = SimpleNamespace(execute=_execute)
    await _get_or_create_state(session, "a1", for_update=True)
    await _get_or_create_state(session, "a1")
    assert "FOR UPDATE" in captured[0]
    assert "FOR UPDATE" not in captured[1]
