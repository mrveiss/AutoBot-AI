# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A command that ran must never be reported as one that failed to run (#15073).

One `except Exception` wrapped the executor call *and* the four post-processing
awaits after it. A `TypeError` in a logging helper — exactly the class of defect
#13281 stopped swallowing one layer down — came back as
``{"status": "error", "error": "Command execution failed"}``: the wrong
diagnosis (the operator is sent to the PTY and the shell, where nothing is
broken) and, worse, the command's real stdout/stderr/return_code discarded.

What is asserted here is the *distinction*, not the mere presence of an error.
A fix that reported both outcomes as some error would satisfy "an error is
returned" and still leave the user unable to tell "your command failed" from
"your command worked, our bookkeeping did not". So every test below pins which
of the two happened, and one compares the two responses head to head.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.status_enums import CommandRisk
from services.agent_terminal.errors import (
    EXECUTION_FAILED_CODE,
    POST_EXECUTION_FAILED_CODE,
    POST_EXECUTION_FAILED_STATUS,
)
from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.service import AgentTerminalService
from services.command_approval_manager import AgentRole

pytestmark = pytest.mark.asyncio

# The defect #13281 surfaced and this layer relabelled: a keyword the callee
# does not accept. It is a programming error, not a failed command.
SIGNATURE_MISMATCH = TypeError("add_message() got an unexpected keyword argument 'role'")

SUCCESSFUL_RUN = {
    "status": "success",
    "stdout": "hello from the pty\n",
    "stderr": "",
    "return_code": 0,
}


def _session() -> AgentTerminalSession:
    return AgentTerminalSession(
        session_id="term-15073",
        agent_id="agent-15073",
        agent_role=AgentRole.CHAT_AGENT,
        conversation_id="conv-15073",
    )


def _service(*, executor_result=None, executor_error: BaseException | None = None) -> AgentTerminalService:
    """A service whose collaborators are all doubles except the code under test."""
    svc = AgentTerminalService.__new__(AgentTerminalService)
    svc.command_executor = AsyncMock()
    if executor_error is not None:
        svc.command_executor.execute_in_pty = AsyncMock(side_effect=executor_error)
    else:
        svc.command_executor.execute_in_pty = AsyncMock(return_value=dict(executor_result or SUCCESSFUL_RUN))
    svc.approval_handler = AsyncMock()
    svc.terminal_logger = AsyncMock()
    svc.prometheus_metrics = MagicMock()  # record_task_execution is sync
    svc.chat_workflow_manager = None
    svc.session_manager = AsyncMock()
    svc.redis_client = None
    return svc


async def _approve(svc: AgentTerminalService):
    return await svc._execute_approved_command(
        session=_session(),
        command="echo hello",
        command_id="cmd-1",
        risk_level="LOW",
        user_id="user-1",
        comment=None,
        auto_approve_future=False,
    )


async def _auto_execute(svc: AgentTerminalService, *, post_execution_error: BaseException | None = None):
    """Drive the real ``execute_command`` boundary, stubbing only the gates before it.

    ``post_execution_error`` is raised from the chat-history write, one of the
    steps that runs after the command has already produced its output.
    """
    svc.get_session = AsyncMock(return_value=_session())
    svc._assess_command = lambda command: (None, CommandRisk.SAFE, [], False, [])
    svc._check_agent_permission = lambda *_a, **_k: None
    svc._check_auto_approval_or_queue = AsyncMock(return_value=(True, None))
    svc._save_command_to_chat = AsyncMock(side_effect=post_execution_error)
    return await svc.execute_command(session_id="term-15073", command="echo hello")


# --------------------------------------------------------------------------
# Approved path (service.py::_execute_approved_command)
# --------------------------------------------------------------------------


async def test_post_processing_failure_keeps_the_output_the_command_produced():
    """The exact bug: the command ran, so its result must survive the failure."""
    svc = _service()
    svc._post_execution_updates = AsyncMock(side_effect=SIGNATURE_MISMATCH)

    response = await _approve(svc)

    assert response["status"] == POST_EXECUTION_FAILED_STATUS
    assert response["error_code"] == POST_EXECUTION_FAILED_CODE
    assert response["stdout"] == SUCCESSFUL_RUN["stdout"]
    assert response["return_code"] == 0
    assert response["command_status"] == "success"
    assert "add_message()" in response["post_execution_error"]
    assert "Command execution failed" not in str(response)


async def test_a_command_that_never_ran_is_reported_as_an_execution_failure():
    """The other outcome, so the fix cannot pass by relabelling everything."""
    svc = _service(executor_error=OSError("pty spawn failed"))

    response = await _approve(svc)

    assert response["status"] == "error"
    assert response["error_code"] == EXECUTION_FAILED_CODE
    assert "stdout" not in response


async def test_the_two_failures_are_told_apart_by_the_caller():
    """Head to head: same call, two outcomes, nothing a caller could confuse."""
    ran = _service()
    ran._post_execution_updates = AsyncMock(side_effect=SIGNATURE_MISMATCH)
    never_ran = _service(executor_error=OSError("pty spawn failed"))

    ran_response = await _approve(ran)
    never_ran_response = await _approve(never_ran)

    assert ran_response["status"] != never_ran_response["status"]
    assert ran_response["error_code"] != never_ran_response["error_code"]
    # Only one of the two can show the user what the command printed.
    assert ran_response.get("stdout") and not never_ran_response.get("stdout")


async def test_a_programming_error_in_execution_itself_reaches_the_caller():
    """#13281's split, held one layer up: a signature mismatch is not a verdict."""
    svc = _service(executor_error=SIGNATURE_MISMATCH)

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        await _approve(svc)


async def test_the_post_processing_failure_is_logged_with_its_traceback(caplog):
    """`logger.error("...: %s", e)` loses the only line that names the real defect."""
    svc = _service()
    svc._post_execution_updates = AsyncMock(side_effect=SIGNATURE_MISMATCH)

    with caplog.at_level(logging.ERROR):
        await _approve(svc)

    failures = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert failures, "the post-execution failure was not logged at all"
    assert any(r.exc_info for r in failures), "logged without exc_info: no traceback to follow"


# --------------------------------------------------------------------------
# Auto-approved path (service.py::execute_command)
# --------------------------------------------------------------------------


async def test_auto_approved_run_reports_success_when_nothing_after_it_breaks():
    """Baseline: the intact path is untouched, so the next test measures the fix."""
    response = await _auto_execute(_service())

    assert response["status"] == "success"
    assert response["stdout"] == SUCCESSFUL_RUN["stdout"]


async def test_auto_approved_post_processing_failure_keeps_the_output():
    """The second site: fixing only one leaves the other free to misreport."""
    response = await _auto_execute(_service(), post_execution_error=SIGNATURE_MISMATCH)

    assert response["status"] == POST_EXECUTION_FAILED_STATUS
    assert response["error_code"] == POST_EXECUTION_FAILED_CODE
    assert response["stdout"] == SUCCESSFUL_RUN["stdout"]
    assert response["command_status"] == "success"
    assert "Command execution failed" not in str(response)


async def test_auto_approved_execution_failure_stays_an_execution_failure():
    svc = _service(executor_error=OSError("pty spawn failed"))

    response = await _auto_execute(svc)

    assert response["status"] == "error"
    assert response["error_code"] == EXECUTION_FAILED_CODE
    assert "stdout" not in response


async def test_auto_approved_programming_error_in_execution_reaches_the_caller():
    svc = _service(executor_error=SIGNATURE_MISMATCH)

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        await _auto_execute(svc)
