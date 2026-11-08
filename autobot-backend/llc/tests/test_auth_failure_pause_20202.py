# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A claude_code authentication failure keeps its reason on the run and pauses the agent (#20202).

The run goes through the ordinary FAILED path first; the pause is a separate best-effort step, so a
pause that cannot happen never costs the FAILED row.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from llc.adapters.base import AdapterRunStatus
from llc.adapters.claude_code_adapter import AUTH_FAILED_REASON
from llc.exceptions import AdapterAuthFailed, AdapterRunFailed
from llc.models.enums import LLCRunStatus
from llc.scheduler.heartbeat_scheduler import LLCHeartbeatScheduler, _dispatch_registry_adapter
from llc.services.controls_service import AgentNotFoundError
from testkit.fake_async_session import FakeAsyncSession

_RUN_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
_COMPANY = str(uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"))
_SCHED = "llc.scheduler.heartbeat_scheduler"
_PAUSE = "llc.scheduler.auth_failure.ControlsService.pause_agent"


def _agent(**kwargs):
    base = {"agent_id": "agent-auth", "company_id": _COMPANY, "adapter_type": "claude_code", "org_role": "worker"}
    return {**base, **kwargs}


def _adapter(error: str):
    adapter = AsyncMock()
    adapter.invoke = AsyncMock(return_value="ext-run")
    adapter.status = AsyncMock(return_value=AdapterRunStatus(status=LLCRunStatus.FAILED, error=error))
    return adapter


async def _dispatch(error: str):
    with (
        patch(f"{_SCHED}._issue_run_key", AsyncMock(return_value=(None, None))),
        patch(f"{_SCHED}._revoke_run_key", AsyncMock()),
    ):
        await _dispatch_registry_adapter(_adapter(error), _agent(), {})


async def _run(dispatch_error: Exception, agent=None, sessions=None):
    """Drive ``_run_adapter`` to a dispatch error; returns the sessions it opened, in order."""
    sessions = [] if sessions is None else sessions

    def factory():
        sessions.append(FakeAsyncSession())
        return sessions[-1]

    with (
        patch(f"{_SCHED}.get_async_session_factory", return_value=factory),
        patch("llc.scheduler.auth_failure.get_async_session_factory", return_value=factory),
        patch(f"{_SCHED}.mark_running", AsyncMock(return_value=0)),
        patch(f"{_SCHED}._dispatch_adapter", AsyncMock(side_effect=dispatch_error)),
        patch(f"{_SCHED}.release_run_workspace", AsyncMock()),
        patch(f"{_SCHED}._record_run_for_replay", AsyncMock()),
    ):
        scheduler = LLCHeartbeatScheduler()
        await scheduler._run_adapter(agent or _agent(), _RUN_ID, {})
        for task in list(scheduler._tasks):
            await task
    return sessions


def _row_values(session) -> dict:
    return session.statements[0].compile().params


@pytest.mark.asyncio
async def test_an_auth_failed_run_raises_the_subclass_carrying_its_reason():
    with pytest.raises(AdapterAuthFailed) as caught:
        await _dispatch(AUTH_FAILED_REASON)
    assert caught.value.reason == AUTH_FAILED_REASON
    assert AUTH_FAILED_REASON in str(caught.value)


@pytest.mark.asyncio
async def test_a_generic_failed_run_stays_plain_and_still_carries_its_reason():
    with pytest.raises(AdapterRunFailed) as caught:
        await _dispatch("turn limit")
    assert type(caught.value) is AdapterRunFailed
    assert caught.value.reason == "turn limit" and "turn limit" in str(caught.value)


def test_a_run_failure_without_a_reason_keeps_its_old_message():
    assert str(AdapterRunFailed("claude_code", "r1", LLCRunStatus.FAILED)).endswith("'failed'")


@pytest.mark.asyncio
async def test_the_run_row_is_failed_with_the_reason_and_the_agent_is_paused_once_after_it():
    failure = AdapterAuthFailed("claude_code", "ext-run", LLCRunStatus.FAILED, AUTH_FAILED_REASON)
    sessions: list = []
    seen: dict = {}

    async def pause(self, session, company_id, agent_id, **kw):
        seen["row_commits_before_pause"] = sessions[0].commits
        seen["args"] = (company_id, agent_id, kw)

    with patch(_PAUSE, new=pause):
        await _run(failure, sessions=sessions)
    values = _row_values(sessions[0])
    assert values["status"] == LLCRunStatus.FAILED.value and AUTH_FAILED_REASON in values["error"]
    assert seen["row_commits_before_pause"] == 1, "the FAILED row is committed before the pause is attempted"
    company_id, agent_id, kw = seen["args"]
    assert (company_id, agent_id) == (_COMPANY, "agent-auth")
    assert kw["actor_type"] == "system" and kw["actor_user_id"] is None
    assert "re-authentication" in kw["reason"] and "manually" in kw["reason"]
    assert len(sessions) == 2 and sessions[1].commits == 1


@pytest.mark.asyncio
async def test_a_plain_failure_does_not_pause_the_agent():
    with patch(_PAUSE, new=AsyncMock()) as pause:
        sessions = await _run(AdapterRunFailed("claude_code", "ext-run", LLCRunStatus.FAILED, "turn limit"))
    pause.assert_not_awaited()
    assert len(sessions) == 1 and "turn limit" in _row_values(sessions[0])["error"]


@pytest.mark.asyncio
async def test_a_pause_that_fails_still_leaves_the_row_failed_with_its_reason():
    failure = AdapterAuthFailed("claude_code", "ext-run", LLCRunStatus.FAILED, AUTH_FAILED_REASON)
    with (
        patch(_PAUSE, new=AsyncMock(side_effect=AgentNotFoundError("agent-auth"))),
        patch("llc.scheduler.auth_failure.logger") as log,
    ):
        sessions = await _run(failure)
    values = _row_values(sessions[0])
    assert values["status"] == LLCRunStatus.FAILED.value and AUTH_FAILED_REASON in values["error"]
    assert sessions[0].commits == 1 and sessions[1].commits == 0
    log.warning.assert_called_once()


@pytest.mark.asyncio
async def test_an_agent_without_a_company_is_not_paused_and_the_row_is_still_failed():
    failure = AdapterAuthFailed("claude_code", "ext-run", LLCRunStatus.FAILED, AUTH_FAILED_REASON)
    with patch(_PAUSE, new=AsyncMock()) as pause, patch("llc.scheduler.auth_failure.logger") as log:
        sessions = await _run(failure, _agent(company_id=None))
    pause.assert_not_awaited()
    assert AUTH_FAILED_REASON in _row_values(sessions[0])["error"]
    log.warning.assert_called_once()
