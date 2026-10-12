# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSH plumbing for `services/backup.py` (#18186).

Extracted from `BackupService` rather than added to it: that module sits at the line count the
Python file-size ratchet grandfathered it at, and moving the restore's `systemctl stop|start` onto
the one SSH restart executor (`services/service_restart.py`) needed room. `BackupService` keeps
`_build_ssh_command` and `_run_command` as thin delegates so every caller and test patch point
is unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Tuple

from services.role_units import REDIS_UNIT
from services.service_restart import run_systemctl_over_ssh

logger = logging.getLogger(__name__)

_REDIS_UNIT_TIMEOUT_S = 30  # seconds; the value `_run_command(..., timeout=30)` used for stop/start


def ssh_base_command(host: str, user: str, port: int) -> list:
    """The ssh argv up to the host, without the remote command."""
    return [
        "/usr/bin/ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "BatchMode=yes",
        "-p",
        str(port),
        f"{user}@{host}",
    ]


async def _reported(call) -> Tuple[bool, str]:
    """Await *call* (an ssh run giving (returncode, stdout bytes)) as (success, output)."""
    try:
        returncode, stdout = await call
        return returncode == 0, stdout.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        return False, "Command timed out"
    except Exception as e:
        logger.error("SSH command execution error: %s", e)
        return False, "Command execution failed"


async def _spawn(cmd: list, timeout: int, stdin: bytes | None) -> Tuple[int | None, bytes]:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(process.communicate(input=stdin), timeout=timeout)
    return process.returncode, stdout


async def run_command(cmd: list, timeout: int = 60, stdin: bytes | None = None) -> Tuple[bool, str]:
    """Run a command and return (success, output); *stdin* is written to its standard input."""
    return await _reported(_spawn(cmd, timeout, stdin))


async def systemctl_redis(ssh_base_cmd: list, action: str) -> Tuple[bool, str]:
    """`sudo systemctl <action>` of the Redis unit, reported like `run_command` (no `-n`, 30 s)."""
    return await _reported(_redis_unit_call(ssh_base_cmd, action))


async def _redis_unit_call(ssh_base_cmd: list, action: str) -> Tuple[int | None, bytes]:
    done = await run_systemctl_over_ssh(
        ssh_base_cmd,
        action,
        [REDIS_UNIT],
        use_noninteractive_sudo=False,
        timeout=_REDIS_UNIT_TIMEOUT_S,
        merge_stderr=True,
    )
    return done.returncode, done.stdout
