# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AgentTerminalSession.has_running_task() is a live signal, not a stub (#16947).

`running_command_task` was declared on the dataclass but never assigned
anywhere outside `models.py` -- `has_running_task()` (and so
`sync_session_presence`'s busy signal) was always False in production.
`_run_tracked` is the one place both `_execute_auto_approved_command` and
`_run_approved_command_body` reach the executor, so fixing it there covers
both the auto-approved and human-approved paths.
"""

import asyncio

import pytest

from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.service import AgentTerminalService
from services.command_approval_manager import AgentRole

pytestmark = pytest.mark.asyncio


def _session() -> AgentTerminalSession:
    return AgentTerminalSession(
        session_id="term-16947",
        agent_id="agent-16947",
        agent_role=AgentRole.CHAT_AGENT,
        conversation_id="conv-16947",
    )


def _service() -> AgentTerminalService:
    svc = AgentTerminalService.__new__(AgentTerminalService)
    return svc


async def test_has_running_task_is_true_only_for_the_commands_span():
    svc = _service()
    session = _session()
    assert session.has_running_task() is False

    release = asyncio.Event()
    seen_busy_mid_command = False

    async def _slow_execute_in_pty(_session, _command):
        nonlocal seen_busy_mid_command
        seen_busy_mid_command = session.has_running_task()
        await release.wait()
        return {"status": "success"}

    svc.command_executor = type("_Exec", (), {"execute_in_pty": staticmethod(_slow_execute_in_pty)})()

    run = asyncio.ensure_future(svc._run_tracked(session, "echo hi"))
    await asyncio.sleep(0)  # let _run_tracked start and reach execute_in_pty
    release.set()
    result = await run

    assert result == {"status": "success"}
    assert seen_busy_mid_command is True
    assert session.has_running_task() is False


async def test_has_running_task_clears_even_when_the_executor_raises():
    svc = _service()
    session = _session()

    async def _raising_execute_in_pty(_session, _command):
        raise RuntimeError("pty boom")

    svc.command_executor = type("_Exec", (), {"execute_in_pty": staticmethod(_raising_execute_in_pty)})()

    with pytest.raises(RuntimeError, match="pty boom"):
        await svc._run_tracked(session, "echo hi")

    assert session.has_running_task() is False
