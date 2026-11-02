# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run a shell command with a deadline, an output cap and a working directory (#19807).

The child leads its own process group, so a timeout or a cancelled caller kills
the shell and everything it started, not just the shell.
"""

from __future__ import annotations

import asyncio
import os
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


async def _drain(stream: asyncio.StreamReader, limit: int) -> tuple[bytes, bool]:
    """Read *stream* to EOF, keeping at most *limit* bytes; True when bytes were dropped."""
    kept: list[bytes] = []
    size = 0
    dropped = False
    while chunk := await stream.read(_READ_CHUNK):
        take = chunk[: max(limit - size, 0)]
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
    """Run *command* in a shell in *cwd*, killing its process group after *timeout_s*."""
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=child_env(cwd),
        start_new_session=True,
    )
    try:
        (out, out_cut), (err, err_cut), _ = await asyncio.wait_for(
            asyncio.gather(
                _drain(process.stdout, max_output_bytes),
                _drain(process.stderr, max_output_bytes),
                process.wait(),
            ),
            timeout=timeout_s,
        )
        return BoundedResult(out, err, process.returncode, False, out_cut or err_cut)
    except asyncio.TimeoutError:
        return BoundedResult(b"", b"", None, True, False)
    finally:
        await _reap(process)
