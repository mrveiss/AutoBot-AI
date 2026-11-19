# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A repeated pause keeps the first pause (#21056).

The fake session applies the UPDATEs ``ControlsService`` issues to one in-memory agent row, so
the sequence operator pause -> system pause -> resume is observable end to end.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from llc.exceptions import AdapterAuthFailed, SubscriptionQuotaExhausted
from llc.models import ActivityEventType
from llc.scheduler.auth_failure import pause_after_auth_failure
from llc.scheduler.heartbeat_scheduler import LLCHeartbeatScheduler
from llc.services.controls_service import AgentNotPausableError, ControlsService
from testkit.fake_async_session import FakeAsyncSession, FakeResult

_CS = "llc.services.controls_service"
_HBS = "llc.scheduler.heartbeat_scheduler"


class _AgentSession(FakeAsyncSession):
    """Answers the agent row SELECT and applies the pause/resume UPDATEs to it.

    The pause UPDATE is conditional (``status NOT IN (:paused, :terminated)``) and returns the row's
    previous status through ``RETURNING``, as Postgres does; no row matches -> ``fetchone()`` is None.
    """

    def __init__(self, status="available"):
        super().__init__()
        self.agent = {"status": status, "pre_pause_status": None, "pause_reason": None}
        self.updates = []
        self.selects = 0

    async def execute(self, statement, params=None, **kw):
        await super().execute(statement, params)
        sql = str(statement)
        if sql.startswith("SELECT status, pre_pause_status, pause_reason"):
            self.selects += 1
            a = self.agent
            row = None if a["status"] is None else (a["status"], a["pre_pause_status"], a["pause_reason"])
            return SimpleNamespace(fetchone=lambda: row)
        if sql.startswith("UPDATE agent_org_nodes"):
            self.updates.append(params)
            return SimpleNamespace(fetchone=lambda: self._apply(sql, params))
        return FakeResult([])

    def _apply(self, sql, p):
        if "pause_reason = :reason" not in sql:
            self.agent.update(status=p["status"], pause_reason=None, pre_pause_status=None)
            return None
        assert "pre_pause_status = status" in sql, "the previous status must come from the row, not a prior read"
        assert "status NOT IN (:paused, :terminated)" in sql, "the pause must be conditional in the statement"
        if self.agent["status"] in (None, p["paused"], p["terminated"]):
            return None
        before = self.agent["status"]
        self.agent.update(status=p["paused"], pause_reason=p["reason"], pre_pause_status=before)
        return (before,)


def _log():
    log = AsyncMock()
    log.record = AsyncMock()
    return log


@pytest.fixture
def redis():
    client = AsyncMock()
    with patch(f"{_CS}.get_async_redis_client", AsyncMock(return_value=client)):
        yield client


async def _operator_pause(session, log):
    svc = ControlsService(activity_log=log)
    await svc.pause_agent(session, "co", "ag", "user-1", reason="operator hold")
    return svc


async def test_second_pause_keeps_first_reason_and_pre_pause_status(redis):
    session, log = _AgentSession("available"), _log()
    svc = await _operator_pause(session, log)
    assert session.agent["status"] == "paused"

    result = await svc.pause_agent(session, "co", "ag", None, reason="quota", actor_type="system")

    assert session.agent["status"] == "paused"
    assert session.agent["pause_reason"] == "operator hold"
    assert session.agent["pre_pause_status"] == "available"
    assert result["already_paused"] is True and result["pause_reason"] == "operator hold"
    assert redis.set.await_count == 2, "the Redis flag is still (re)set"


async def test_repeat_is_logged_as_a_noop(redis):
    session, log = _AgentSession("available"), _log()
    svc = await _operator_pause(session, log)

    await svc.pause_agent(session, "co", "ag", None, reason="quota", actor_type="system")

    assert log.record.await_count == 2
    kw = log.record.await_args.kwargs
    paused = {"status": "paused", "pause_reason": "operator hold"}
    assert kw["event_type"] == ActivityEventType.CONTROL_AGENT_PAUSE_REPEATED
    assert log.record.await_args_list[0].kwargs["event_type"] == ActivityEventType.CONTROL_AGENT_PAUSED
    assert kw["before"] == paused and kw["after"] == paused
    assert kw["actor_type"] == "system"
    assert kw["metadata"] == {
        "repeated_pause": "noop",
        "requested_reason": "quota",
        "requested_actor_type": "system",
    }


async def _resume_status(session, svc):
    return (await svc.resume_agent(session, "co", "ag", "user-1"))["status"]


async def test_quota_pause_during_operator_pause_resumes_to_original_status(redis):
    session, log = _AgentSession("available"), _log()
    svc = await _operator_pause(session, log)
    agent = {"agent_id": "ag", "company_id": "co"}
    exc = SubscriptionQuotaExhausted("ag", "quota gone")

    with (
        patch(f"{_HBS}.get_async_session_factory", return_value=lambda: session),
        patch(f"{_HBS}.ControlsService", return_value=svc),
    ):
        await LLCHeartbeatScheduler()._handle_quota_exhausted(agent, uuid.uuid4(), exc)

    assert session.agent["pause_reason"] == "operator hold"
    assert await _resume_status(session, svc) == "available"


async def test_auth_failure_pause_during_operator_pause_resumes_to_original_status(redis):
    session, log = _AgentSession("available"), _log()
    svc = await _operator_pause(session, log)
    failure = AdapterAuthFailed("claude_code", "ext-1", "failed", "auth")

    with (
        patch("llc.scheduler.auth_failure.get_async_session_factory", return_value=lambda: session),
        patch("llc.scheduler.auth_failure.ControlsService", return_value=svc),
    ):
        await pause_after_auth_failure(failure, {"agent_id": "ag", "company_id": "co"}, uuid.uuid4())

    assert session.agent["pause_reason"] == "operator hold"
    assert await _resume_status(session, svc) == "available"


async def test_pause_sprint_keeps_an_operator_pause(redis):
    """pause_sprint pauses through pause_agent, so the same guard covers it."""
    session, log = _AgentSession("available"), _log()
    svc = await _operator_pause(session, log)

    with (
        patch.object(svc, "_get_sprint", AsyncMock(return_value={"id": "sp"})),
        patch.object(svc, "_agents_in_sprint", AsyncMock(return_value=["ag"])),
    ):
        await svc.pause_sprint(session, "co", "sp", "user-2")

    assert session.agent["pause_reason"] == "operator hold"
    assert session.agent["pre_pause_status"] == "available"
    assert session.agent["status"] == "paused"


async def test_terminated_agent_is_refused_and_nothing_is_written(redis):
    session, log = _AgentSession("terminated"), _log()
    session.agent.update(pause_reason="fired for cause", pre_pause_status=None)
    svc = ControlsService(activity_log=log)

    with pytest.raises(AgentNotPausableError) as refused:
        await svc.pause_agent(session, "co", "ag", "user-1", reason="hold")

    assert refused.value.status == "terminated"
    assert session.agent == {"status": "terminated", "pre_pause_status": None, "pause_reason": "fired for cause"}
    log.record.assert_not_awaited()
    redis.set.assert_not_awaited()


async def test_missing_agent_is_not_found_and_sets_no_flag(redis):
    from llc.services.controls_service import AgentNotFoundError

    session = _AgentSession(None)

    log = _log()
    with pytest.raises(AgentNotFoundError):
        await ControlsService(activity_log=log).pause_agent(session, "co", "ag", "user-1")
    log.record.assert_not_awaited()
    redis.set.assert_not_awaited()


async def test_first_pause_is_one_conditional_update_with_no_prior_read(redis):
    session = _AgentSession("in_sprint")

    await ControlsService(activity_log=_log()).pause_agent(session, "co", "ag", "user-1", reason="hold")

    assert len(session.updates) == 1 and session.selects == 0
    assert session.agent["pre_pause_status"] == "in_sprint"


async def test_pause_sprint_skips_a_terminated_agent(redis):
    session = _AgentSession("terminated")
    svc = ControlsService(activity_log=_log())

    with (
        patch.object(svc, "_get_sprint", AsyncMock(return_value={"id": "sp"})),
        patch.object(svc, "_agents_in_sprint", AsyncMock(return_value=["ag"])),
    ):
        await svc.pause_sprint(session, "co", "sp", "user-2")

    assert session.agent["status"] == "terminated"
    redis.set.assert_not_awaited()


async def test_auto_pause_of_a_terminated_agent_returns_false_and_writes_nothing(redis):
    session, log = _AgentSession("terminated"), _log()
    svc = ControlsService(activity_log=log)

    assert await svc.auto_pause_agent(session, "co", "ag", "subscription quota exhausted") is False
    assert session.agent["status"] == "terminated"
    log.record.assert_not_awaited()
    redis.set.assert_not_awaited()
    assert await svc.auto_pause_agent(_AgentSession("available"), "co", "ag", "quota") is True
