# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent-facing tool must not flatten every failure into four words (#15110).

``TerminalTool.execute_command`` closed with one ``except Exception`` around
session recovery, the service call **and** the formatting after it. "No terminal
session could be created", "the command failed" and "the formatter raised" all
reached the model as ``{"status": "error", "error": "Command execution failed"}``
-- the third instance of the shape #15073 removed from the service, one layer
further out, and the one that mattered most because its audience is a model
that will act on the answer.

It also relabelled the ``TypeError`` the service now *deliberately* re-raises,
so a signature mismatch reached the model as a failed command instead of
reaching CI and the error tracker.

What is asserted here is the **distinction**. A fix that reported every outcome
as some error would satisfy "an error is returned" and leave the model exactly
as unable to tell the cases apart, so every test below pins which outcome
happened, and one compares all three head to head.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.agent_terminal.errors import (
    EXECUTION_FAILED_CODE,
    POST_EXECUTION_FAILED_CODE,
    POST_EXECUTION_FAILED_STATUS,
    SESSION_SETUP_FAILED_CODE,
)
from tools.terminal_tool import TerminalTool

pytestmark = pytest.mark.asyncio

#: The defect the service re-raises rather than swallowing: a keyword the callee
#: does not accept. A programming error, not a verdict on the command.
SIGNATURE_MISMATCH = TypeError("log_command() got an unexpected keyword argument 'role'")

SUCCESSFUL_RUN = {
    "status": "success",
    "stdout": "hello from the pty\n",
    "stderr": "",
    "return_code": 0,
}

POST_EXECUTION_RESULT = {
    **SUCCESSFUL_RUN,
    "status": POST_EXECUTION_FAILED_STATUS,
    "command_status": "success",
    "post_execution_error": "TypeError: add_message() got an unexpected keyword argument 'role'",
}


def _tool(*, service_result=None, service_error: BaseException | None = None) -> TerminalTool:
    """A tool whose session recovery succeeds and whose service is a double."""
    tool = TerminalTool.__new__(TerminalTool)
    tool.active_sessions = {}
    tool.agent_terminal_service = AsyncMock()
    if service_error is not None:
        tool.agent_terminal_service.execute_command = AsyncMock(side_effect=service_error)
    else:
        tool.agent_terminal_service.execute_command = AsyncMock(return_value=dict(service_result or SUCCESSFUL_RUN))
    tool._ensure_active_session = AsyncMock(return_value="term-15110")
    return tool


async def _execute(tool: TerminalTool):
    return await tool.execute_command(conversation_id="conv-15110", command="echo hello")


# --- the acceptance criteria ------------------------------------------------


async def test_a_type_error_below_the_tool_is_not_returned_as_a_failed_command():
    """AC1. The service re-raises this on purpose; relabelling it hid it from CI."""
    tool = _tool(service_error=SIGNATURE_MISMATCH)

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        await _execute(tool)


async def test_an_attribute_error_below_the_tool_also_travels_on():
    """The other half of the pair the service re-raises."""
    tool = _tool(service_error=AttributeError("'NoneType' object has no attribute 'log_command'"))

    with pytest.raises(AttributeError):
        await _execute(tool)


async def test_a_session_setup_failure_is_not_a_command_failure():
    """AC2, first half: nowhere to run the command is not the command failing."""
    tool = _tool()
    tool._ensure_active_session = AsyncMock(side_effect=OSError("pty spawn failed"))

    response = await _execute(tool)

    assert response["error_code"] == SESSION_SETUP_FAILED_CODE
    assert "No terminal session could be established" in response["error"]
    assert "pty spawn failed" in response["error"]


async def test_a_command_failure_is_reported_as_an_execution_failure():
    """AC2, second half. Without it the fix could relabel everything alike."""
    tool = _tool(service_error=RuntimeError("the executor gave up"))

    response = await _execute(tool)

    assert response["error_code"] == EXECUTION_FAILED_CODE


async def test_the_three_failure_modes_are_told_apart_by_the_caller():
    """Head to head. "All three produce an error" is the vacuous version of this."""
    no_session = _tool()
    no_session._ensure_active_session = AsyncMock(side_effect=OSError("pty spawn failed"))
    failed_command = _tool(service_error=RuntimeError("the executor gave up"))
    ran_then_broke = _tool(service_result=POST_EXECUTION_RESULT)

    responses = [await _execute(no_session), await _execute(failed_command), await _execute(ran_then_broke)]
    codes = [r["error_code"] for r in responses]

    assert len(set(codes)) == 3, f"the three outcomes are not distinguishable: {codes}"
    # And only the one whose command actually ran can show what it printed.
    assert not responses[0].get("stdout")
    assert not responses[1].get("stdout")
    assert responses[2]["stdout"] == SUCCESSFUL_RUN["stdout"]


async def test_completed_with_errors_keeps_the_output_and_names_the_failure():
    """AC3. This status had no branch and fell through to "success"."""
    response = await _execute(_tool(service_result=POST_EXECUTION_RESULT))

    assert response["status"] == POST_EXECUTION_FAILED_STATUS
    assert response["error_code"] == POST_EXECUTION_FAILED_CODE
    assert response["stdout"] == SUCCESSFUL_RUN["stdout"]
    assert response["return_code"] == 0
    assert response["command_status"] == "success"
    assert "add_message()" in response["post_execution_error"]
    assert "Command execution failed" not in str(response)


async def test_a_formatter_defect_is_post_execution_not_a_failed_command():
    """The third stage the old catch-all covered, and the subtlest.

    The command ran and its output exists; a defect in the formatting after it
    must not discard that output or claim the command failed.
    """
    tool = _tool()
    tool._format_execution_result = lambda *a, **k: (_ for _ in ()).throw(SIGNATURE_MISMATCH)

    response = await _execute(tool)

    assert response["status"] == POST_EXECUTION_FAILED_STATUS
    assert response["error_code"] == POST_EXECUTION_FAILED_CODE
    assert response["stdout"] == SUCCESSFUL_RUN["stdout"]
    assert "Command execution failed" not in str(response)


# --- the paths that must be unchanged ---------------------------------------


async def test_a_clean_run_is_still_reported_as_success():
    """Baseline: without it the tests above cannot show the fix changed anything."""
    response = await _execute(_tool())

    assert response["status"] == "success"
    assert response["stdout"] == SUCCESSFUL_RUN["stdout"]
    assert "error_code" not in response


async def test_a_missing_service_is_still_reported_before_anything_runs():
    tool = TerminalTool.__new__(TerminalTool)
    tool.active_sessions = {}
    tool.agent_terminal_service = None

    response = await _execute(tool)

    assert response["status"] == "error"
    assert "not available" in response["error"]


async def test_the_error_codes_are_three_distinct_wire_values():
    """Non-vacuity for the head-to-head test: three names, three values."""
    codes = {SESSION_SETUP_FAILED_CODE, EXECUTION_FAILED_CODE, POST_EXECUTION_FAILED_CODE}

    assert len(codes) == 3, f"the outcome vocabulary collapsed: {codes}"
