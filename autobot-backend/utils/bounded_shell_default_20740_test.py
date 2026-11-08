# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No command outlives its deadline, on any branch of the command path (#20740, #20741).

These run real processes. A mocked runner cannot show that a child process is gone.
"""

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest

from security_layer import SecurityLayer
from tests.fixtures.fake_process import finished_process
from utils import command_utils
from utils.agent_command_helpers import run_agent_command
from utils.command_utils import execute_shell_command


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _read_stripped(path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


async def _pid_from(path) -> int:
    for _ in range(50):
        text = await asyncio.to_thread(_read_stripped, path)
        if text:
            return int(text)
        await asyncio.sleep(0.05)
    raise AssertionError("the child never wrote its pid")


@pytest.mark.asyncio
async def test_a_command_with_no_policy_is_killed_at_the_default_deadline(tmp_path):
    pid_file = tmp_path / "pid"
    with patch.object(command_utils, "DEFAULT_SHELL_TIMEOUT_S", 1):
        result = await execute_shell_command(f"sh -c 'echo $$ > {pid_file}; sleep 60'")
    assert result["return_code"] == 124 and result["status"] == "error"
    assert result["stderr"] == "Command timed out after 1s and was killed"
    assert not _alive(await _pid_from(pid_file)), "the child outlived the deadline, not only the shell"


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
    pid = await _pid_from(pid_file)
    try:
        assert _alive(pid), "a job deliberately backgrounded was killed when its shell returned"
    finally:
        os.kill(pid, 9)


@pytest.mark.asyncio
async def test_a_timed_out_command_kills_only_its_own_process_group(tmp_path):
    """The child leads a group of its own, so the group kill never reaches the test process's group."""
    pid_file = tmp_path / "pid"
    own_group = os.getpgid(0)
    signalled: list[int] = []
    real_killpg = os.killpg

    def recording_killpg(pgid, sig):
        signalled.append(pgid)
        real_killpg(pgid, sig)

    with patch.object(command_utils, "DEFAULT_SHELL_TIMEOUT_S", 1), patch("os.killpg", recording_killpg):
        result = await execute_shell_command(f"sh -c 'echo $$ > {pid_file}; sleep 60'")
    child = await _pid_from(pid_file)
    assert result["timed_out"] is True
    assert signalled and own_group not in signalled and 0 not in signalled
    assert child != own_group and not _alive(child)  # the shell was its group's leader: pid == pgid
    assert os.getpgid(0) == own_group  # and we are still here


@pytest.mark.asyncio
async def test_an_eof_terminated_fake_process_completes_without_a_group_kill():
    """A patched spawn must hand back streams that reach EOF; a bare AsyncMock streams forever (CI OOM)."""
    with patch("asyncio.create_subprocess_shell", return_value=finished_process(b"out\n")):
        result = await asyncio.wait_for(execute_shell_command("echo out"), timeout=5)
    assert result["stdout"] == "out" and result["status"] == "success"
