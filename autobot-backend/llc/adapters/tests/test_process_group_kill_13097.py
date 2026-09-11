# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cancel/timeout must kill an LLC agent's whole process tree, not one PID (GH#13097).

None of the LLC CLI adapters used to spawn their child in its own process group,
so ``terminate_pid`` signalling a single PID left every descendant -- Bash-tool
children, MCP servers, npx/node chains -- orphaned. These tests use real
processes (POSIX process groups have no useful mock) to prove the grandchild
dies with the group, that the pre-fix single-PID kill does not, and that the
own-process-group guard never signals this test runner's group.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import os
import pathlib
import signal
import time
from unittest.mock import patch

import psutil
import pytest

from autobot_shared.eventually import eventually
from llc.adapters.subprocess_support import spawn_detached, terminate_pid

_ADAPTERS_DIR = pathlib.Path(__file__).resolve().parent.parent
_TEST_LOG_NAME = "ProcessGroupKillTest"

_requires_posix = pytest.mark.skipif(os.name != "posix", reason="killpg/getpgid process-group signalling is POSIX-only")


def _create_time(pid: int) -> float:
    """The real psutil create_time for a just-spawned *pid* (PR#16284 review)."""
    return psutil.Process(pid).create_time()


def _pid_alive(pid: int) -> bool:
    """True if *pid* can still be signalled (existence check, no delivery)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _reap(proc: asyncio.subprocess.Process) -> None:
    """Make sure *proc* is dead and reaped, whatever the test did to it."""
    with contextlib.suppress(ProcessLookupError):
        os.kill(proc.pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        await proc.wait()


async def _spawn_parent_with_grandchild() -> tuple[asyncio.subprocess.Process, int]:
    """A session-leader parent that forks a long-lived grandchild.

    Mirrors what the LLC adapters now do via ``spawn_detached``: the parent
    leads its own process group, and the grandchild it forks stands in for a
    Bash-tool child or an MCP server the CLI spawns -- the thing a single-PID
    kill orphans.
    """
    proc = await spawn_detached(
        "sh",
        "-c",
        "sleep 300 & echo $!; wait",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    line = await proc.stdout.readline()
    return proc, int(line.decode().strip())


@_requires_posix
@pytest.mark.asyncio
class TestGrandchildSurvival:
    """AC: grandchild killed by terminate_pid; contrast: a single-PID kill leaves it."""

    async def test_terminate_pid_kills_the_grandchild(self) -> None:
        proc, grandchild_pid = await _spawn_parent_with_grandchild()
        try:
            assert _pid_alive(grandchild_pid)
            create_time = _create_time(proc.pid)
            await terminate_pid(proc.pid, grace_seconds=2, log_name=_TEST_LOG_NAME, expected_create_time=create_time)
            await eventually(lambda: not _pid_alive(grandchild_pid))
        finally:
            await _reap(proc)
            with contextlib.suppress(ProcessLookupError):
                os.kill(grandchild_pid, signal.SIGKILL)

    async def test_old_single_pid_kill_leaves_grandchild_orphaned(self) -> None:
        """Contrast: the pre-GH#13097 behaviour -- proves this test can fail."""
        proc, grandchild_pid = await _spawn_parent_with_grandchild()
        try:
            assert _pid_alive(grandchild_pid)
            os.kill(proc.pid, signal.SIGTERM)  # single PID only, no group
            await eventually(lambda: not _pid_alive(proc.pid))
            assert _pid_alive(grandchild_pid), "single-PID kill must leave the grandchild running"
        finally:
            await _reap(proc)
            with contextlib.suppress(ProcessLookupError):
                os.kill(grandchild_pid, signal.SIGKILL)


@_requires_posix
@pytest.mark.asyncio
class TestTerminatePidRealProcesses:
    """terminate_pid's contract against real processes: already-dead, grace, own-group guard."""

    async def test_already_dead_pid_returns_true(self) -> None:
        proc = await asyncio.create_subprocess_exec("true", start_new_session=True)
        create_time = _create_time(proc.pid)
        await proc.wait()
        result = await terminate_pid(
            proc.pid, grace_seconds=1, log_name=_TEST_LOG_NAME, expected_create_time=create_time
        )
        assert result is True

    async def test_sigterm_then_sigkill_after_grace(self) -> None:
        """A process that traps SIGTERM is still gone after the grace period (SIGKILL).

        The child must echo readiness *after* installing the trap, and the test
        must read that line before signalling: without this sync, SIGTERM can race
        shell startup and arrive before ``trap ''`` runs, so it hits the default
        (terminate) disposition and the process dies on SIGTERM instead of
        surviving to SIGKILL -- flaky about half the time when reproduced locally.
        """
        proc = await spawn_detached(
            "sh",
            "-c",
            "trap '' TERM; echo ready; sleep 300",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await proc.stdout.readline()  # trap is installed by the time this returns
            assert _pid_alive(proc.pid)
            create_time = _create_time(proc.pid)
            start = time.monotonic()
            result = await terminate_pid(
                proc.pid, grace_seconds=1, log_name=_TEST_LOG_NAME, expected_create_time=create_time
            )
            elapsed = time.monotonic() - start
            assert result is False
            assert elapsed >= 1.0, "SIGKILL must not fire before the grace period elapses"
            await eventually(lambda: not _pid_alive(proc.pid))
        finally:
            await _reap(proc)

    async def test_own_process_group_guard_falls_back(self) -> None:
        """A child sharing our pgid (spawned without start_new_session) is never killpg'd."""
        proc = await asyncio.create_subprocess_exec(
            "sleep", "300", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        try:
            assert os.getpgid(proc.pid) == os.getpgid(0), "precondition: child shares our process group"
            create_time = _create_time(proc.pid)
            with patch("os.killpg", side_effect=AssertionError("must never killpg our own group")):
                result = await terminate_pid(
                    proc.pid, grace_seconds=1, log_name=_TEST_LOG_NAME, expected_create_time=create_time
                )
            assert result is False
            await eventually(lambda: not _pid_alive(proc.pid))
        finally:
            await _reap(proc)


_PSUTIL_PROCESS = "llc.adapters.subprocess_support.psutil.Process"


@_requires_posix
@pytest.mark.asyncio
class TestPidReuseSafety:
    """PR#16284 review: never signal a process the run no longer owns.

    A real spawn + record + exit, then a mocked psutil reporting the SAME
    pid alive under a DIFFERENT identity — exactly what a PID the OS handed
    to an unrelated process looks like from terminate_pid's side.
    """

    async def test_reused_pid_with_different_identity_is_never_signalled(self) -> None:
        proc = await spawn_detached("true", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        create_time = _create_time(proc.pid)
        await proc.wait()  # the pid is free now -- something else could hold it next

        with (
            patch(_PSUTIL_PROCESS) as mock_cls,
            patch("os.kill") as mock_kill,
            patch("os.killpg") as mock_killpg,
        ):
            mock_cls.return_value.create_time.return_value = create_time + 1.0  # a DIFFERENT process
            result = await terminate_pid(
                proc.pid, grace_seconds=1, log_name=_TEST_LOG_NAME, expected_create_time=create_time
            )

        assert result is True
        mock_kill.assert_not_called()
        mock_killpg.assert_not_called()


# ---------------------------------------------------------------------------
# Structural: every direct spawn call under llc/adapters/ opts into a new
# session, or goes through subprocess_support.spawn_detached. AST-based so a
# multi-line call is still read (grep would miss the flag on its own line).
# ---------------------------------------------------------------------------

_SPAWN_FUNCS = frozenset({"create_subprocess_exec", "create_subprocess_shell"})


def _spawn_call_nodes(path: pathlib.Path) -> list[ast.Call]:
    """Every create_subprocess_exec/_shell Call node in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (getattr(node.func, "attr", None) or getattr(node.func, "id", None)) in _SPAWN_FUNCS
    ]


def _has_start_new_session(call: ast.Call) -> bool:
    return any(
        kw.arg == "start_new_session" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in call.keywords
    )


class TestSpawnSitesCreateNewSession:
    """GH#13097: no adapter spawn site may silently skip its own process group."""

    def test_every_call_site_sets_start_new_session(self) -> None:
        violations: dict[str, list[int]] = {}
        for path in sorted(_ADAPTERS_DIR.glob("*.py")):
            bad = [c.lineno for c in _spawn_call_nodes(path) if not _has_start_new_session(c)]
            if bad:
                violations[path.name] = bad
        assert not violations, (
            f"create_subprocess_exec/_shell call(s) without start_new_session=True: {violations}. "
            "Route through subprocess_support.spawn_detached, or pass the flag directly."
        )

    def test_scan_is_not_vacuous(self) -> None:
        """Sanity: the walk actually reaches spawn_detached's own call (#16009-style discipline)."""
        found = {p.name: len(_spawn_call_nodes(p)) for p in _ADAPTERS_DIR.glob("*.py")}
        assert (
            found.get("subprocess_support.py") == 1
        ), f"expected exactly one direct create_subprocess_exec call (inside spawn_detached), found: {found}"
