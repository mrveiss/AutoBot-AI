# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run a command with a deadline, an optional output cap and its process group killed on expiry (#19807, #20740).

The child leads its own process group, so a timeout or a cancelled caller kills
the shell and everything it started, not just the shell.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
from dataclasses import dataclass

_READ_CHUNK = 65536
#: The only variables a child inherits from the backend; everything else (keys, DSNs, tokens) is withheld.
CHILD_ENV_PASSTHROUGH: tuple[str, ...] = ("PATH", "LANG", "LC_ALL", "TZ")


def child_env(cwd: str) -> dict[str, str]:
    """A minimal explicit environment for a child: the passthrough names, and HOME set to *cwd*."""
    env = {name: os.environ[name] for name in CHILD_ENV_PASSTHROUGH if name in os.environ}
    env["HOME"] = cwd
    return env


@dataclass(frozen=True)
class BoundedResult:
    """What a bounded run produced; streams are raw bytes, capped per stream."""

    stdout: bytes
    stderr: bytes
    return_code: int | None
    timed_out: bool
    truncated: bool


async def _drain(stream: asyncio.StreamReader, limit: int | None) -> tuple[bytes, bool]:
    """Read *stream* to EOF, keeping at most *limit* bytes (all when None); True when bytes were dropped."""
    kept: list[bytes] = []
    size = 0
    dropped = False
    while chunk := await stream.read(_READ_CHUNK):
        take = chunk if limit is None else chunk[: max(limit - size, 0)]
        kept.append(take)
        size += len(take)
        dropped = dropped or len(take) < len(chunk)
    return b"".join(kept), dropped


async def _reap(process: asyncio.subprocess.Process) -> None:
    """Kill the child's process group if it is still running, then collect it."""
    try:
        os.killpg(process.pid, signal.SIGKILL)  # always: a backgrounded process outlives its shell
    except ProcessLookupError:
        pass  # the whole group already exited
    await process.wait()


async def run_bounded(command: str, *, cwd: str, timeout_s: float, max_output_bytes: int) -> BoundedResult:
    """Run *command* in *cwd* with no shell, killing its process group after *timeout_s*.

    The words come from ``shlex.split`` and the first one is what runs, so ``;``, ``$()``
    and quotes in an argument are plain text, never interpreted. A command that does not
    parse raises ``ValueError``.
    """
    process = await asyncio.create_subprocess_exec(
        *shlex.split(command),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=child_env(cwd),
        start_new_session=True,
    )
    return await _wait_bounded(process, timeout_s, max_output_bytes, kill_group_on_exit=True)


async def run_shell_bounded(command: str, *, timeout_s: float, max_output_bytes: int | None = None) -> BoundedResult:
    """Run *command* through the shell with the caller's environment, killing its process group after *timeout_s*.

    The attended path (#20740): shell semantics and environment are unchanged, but no
    command outlives its deadline. Same wait and drain as :func:`run_bounded`; the process
    group is killed on timeout or cancellation only, so a job the command deliberately put
    in the background (``nohup svc &``) still outlives a shell that finished in time.
    """
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    return await _wait_bounded(process, timeout_s, max_output_bytes, kill_group_on_exit=False)


async def _wait_bounded(
    process: asyncio.subprocess.Process, timeout_s: float, max_output_bytes: int | None, *, kill_group_on_exit: bool
) -> BoundedResult:
    """Collect *process* within *timeout_s*; on expiry or cancellation its whole process group is killed.

    *kill_group_on_exit* also kills the group after a normal exit: right for an unattended step,
    whose leftovers nobody watches; wrong for an attended shell, whose background jobs are intended.
    """
    finished = False
    try:
        (out, out_cut), (err, err_cut), _ = await asyncio.wait_for(
            asyncio.gather(
                _drain(process.stdout, max_output_bytes),
                _drain(process.stderr, max_output_bytes),
                process.wait(),
            ),
            timeout=timeout_s,
        )
        finished = True
        return BoundedResult(out, err, process.returncode, False, out_cut or err_cut)
    except asyncio.TimeoutError:
        return BoundedResult(b"", b"", None, True, False)
    finally:
        if kill_group_on_exit or not finished:  # timed out, or cancelled by the caller
            await _reap(process)
