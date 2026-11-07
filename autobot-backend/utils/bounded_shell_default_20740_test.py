# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No command outlives its deadline, on any branch of the command path (#20740, #20741).

These run real processes. A mocked runner cannot show that a child process is gone.
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest

from security_layer import SecurityLayer
from utils import command_utils
from utils.agent_command_helpers import run_agent_command
from utils.command_utils import execute_shell_command


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _pid_from(path) -> int:
    for _ in range(50):
        if path.exists() and path.read_text().strip():
            return int(path.read_text().strip())
        time.sleep(0.05)
    raise AssertionError("the child never wrote its pid")


@pytest.mark.asyncio
async def test_a_command_with_no_policy_is_killed_at_the_default_deadline(tmp_path):
    pid_file = tmp_path / "pid"
    with patch.object(command_utils, "DEFAULT_SHELL_TIMEOUT_S", 1):
        result = await execute_shell_command(f"sh -c 'echo $$ > {pid_file}; sleep 60'")
    assert result["return_code"] == 124 and result["status"] == "error"
    assert result["stderr"] == "Command timed out after 1s and was killed"
    assert not _alive(_pid_from(pid_file)), "the child outlived the deadline, not only the shell"


@pytest.mark.asyncio
async def test_the_attended_path_keeps_shell_semantics_and_environment(monkeypatch):
    monkeypatch.setenv("AUTOBOT_20740_PROBE", "kept")
    result = await execute_shell_command("echo a | tr a b; echo $AUTOBOT_20740_PROBE")
    assert result["status"] == "success"
    assert result["stdout"].splitlines() == ["b", "kept"]


@pytest.mark.asyncio
async def test_command_security_off_has_the_same_deadline():
    """Same operation, same behaviour: turning command security off must not remove the limit."""
    with patch.object(command_utils, "DEFAULT_SHELL_TIMEOUT_S", 1):
        result = await SecurityLayer._execute_basic_command(MagicMock(), "sleep 60")
    assert result["return_code"] == 124
    assert result["security"] == {"enabled": False}


@pytest.mark.asyncio
async def test_run_agent_command_actually_runs_argv():
    """#20741: every call used to raise TypeError, so network discovery ran nothing."""
    assert await run_agent_command(["echo", "x"]) == {"status": "success", "output": "x"}


@pytest.mark.asyncio
async def test_run_agent_command_reports_its_own_timeout():
    result = await run_agent_command(["sleep", "30"], timeout=1)
    assert result == {"status": "error", "message": "Command timed out after 1 seconds"}


@pytest.mark.asyncio
async def test_run_agent_command_never_passes_argv_to_a_shell():
    result = await run_agent_command(["echo", "a; echo injected"])
    assert result == {"status": "success", "output": "a; echo injected"}


@pytest.mark.asyncio
async def test_a_background_job_outlives_a_shell_that_finished_in_time(tmp_path):
    """Attended semantics: only a timeout kills the group, never a normal exit."""
    pid_file = tmp_path / "bg"
    result = await execute_shell_command(f"sleep 30 > /dev/null 2>&1 & echo $! > {pid_file}")
    assert result["status"] == "success" and result["timed_out"] is False
    pid = _pid_from(pid_file)
    try:
        assert _alive(pid), "a job deliberately backgrounded was killed when its shell returned"
    finally:
        os.kill(pid, 9)
