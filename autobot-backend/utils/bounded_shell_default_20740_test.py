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

#: The deadline each timeout test hands the runner; the same bound limits how long a killed process may take to vanish.
_DEADLINE_S = 1
#: Fields after the closing parenthesis of a stat line: state is first, start time is the 20th.
_STAT_STATE, _STAT_START = 0, 19
#: A shell snippet that records its own stat line (pid and start time) with builtins only.
_RECORD_STAT = 'read -r stat < /proc/$$/stat; echo "$stat"'


def _stat_fields(stat_line: str) -> list[str]:
    """The stat fields that follow the command name, which may itself contain spaces."""
    return stat_line.rpartition(")")[2].split()


def _is_gone(pid: int, start: str) -> bool:
    """True once *pid* is not a running process: absent, a zombie, or reused by a newer process.

    A killed child that nobody has reaped yet is a zombie: dead, but ``os.kill(pid, 0)`` still succeeds.
    """
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            fields = _stat_fields(handle.read())
    except (FileNotFoundError, ProcessLookupError):
        return True
    return fields[_STAT_STATE] == "Z" or fields[_STAT_START] != start


async def _gone_within_deadline(pid: int, start: str) -> bool:
    """Poll until *pid* is gone or the deadline's worth of time has passed; SIGKILL delivery is asynchronous."""
    loop = asyncio.get_running_loop()
    give_up = loop.time() + _DEADLINE_S
    while not await asyncio.to_thread(_is_gone, pid, start):
        if loop.time() >= give_up:
            return False
        await asyncio.sleep(0.02)
    return True


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _read_stripped(path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


async def _stat_from(path) -> str:
    for _ in range(50):
        text = await asyncio.to_thread(_read_stripped, path)
        if text:
            return text
        await asyncio.sleep(0.05)
    raise AssertionError("the child never wrote its pid")


async def _pid_from(path) -> int:
    return int((await _stat_from(path)).split()[0])


async def _identity_from(path) -> tuple[int, str]:
    """The child's pid and its start time, so a pid reused later is not mistaken for the child."""
    text = await _stat_from(path)
    return int(text.split()[0]), _stat_fields(text)[_STAT_START]


@pytest.mark.asyncio
async def test_a_command_with_no_policy_is_killed_at_the_default_deadline(tmp_path):
    pid_file = tmp_path / "pid"
    with patch.object(command_utils, "DEFAULT_SHELL_TIMEOUT_S", _DEADLINE_S):
        result = await execute_shell_command(f"sh -c '{_RECORD_STAT} > {pid_file}; sleep 60'")
    assert result["return_code"] == 124 and result["status"] == "error"
    assert result["stderr"] == f"Command timed out after {_DEADLINE_S}s and was killed"
    pid, start = await _identity_from(pid_file)
    assert await _gone_within_deadline(pid, start), "the child outlived the deadline, not only the shell"


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

    with patch.object(command_utils, "DEFAULT_SHELL_TIMEOUT_S", _DEADLINE_S), patch("os.killpg", recording_killpg):
        result = await execute_shell_command(f"sh -c '{_RECORD_STAT} > {pid_file}; sleep 60'")
    child, start = await _identity_from(pid_file)
    assert result["timed_out"] is True
    assert signalled and own_group not in signalled and 0 not in signalled
    assert child != own_group and await _gone_within_deadline(child, start)
    assert os.getpgid(0) == own_group  # and we are still here


@pytest.mark.asyncio
async def test_a_grandchild_the_shell_waits_on_dies_with_the_group(tmp_path):
    """Killing only the shell would orphan this sleep for its full minute; the group kill ends it within the deadline."""
    pid_file = tmp_path / "grandchild"
    script = f'sleep 60 & read -r stat < /proc/$!/stat; echo "$stat" > {pid_file}; wait'
    with patch.object(command_utils, "DEFAULT_SHELL_TIMEOUT_S", _DEADLINE_S):
        result = await execute_shell_command(f"sh -c '{script}'")
    pid, start = await _identity_from(pid_file)
    assert result["timed_out"] is True
    assert await _gone_within_deadline(pid, start), "a process the shell started survived the group kill"


@pytest.mark.asyncio
async def test_an_eof_terminated_fake_process_completes_without_a_group_kill():
    """A patched spawn must hand back streams that reach EOF; a bare AsyncMock streams forever (CI OOM)."""
    with patch("asyncio.create_subprocess_shell", return_value=finished_process(b"out\n")):
        result = await asyncio.wait_for(execute_shell_command("echo out"), timeout=5)
    assert result["stdout"] == "out" and result["status"] == "success"
