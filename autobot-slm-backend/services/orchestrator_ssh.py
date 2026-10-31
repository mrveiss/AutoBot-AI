# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSH plumbing for `services/service_orchestrator.py` (#18186).

Extracted from `ServiceOrchestrator` rather than added to it: that module sits at the line count
the Python file-size ratchet grandfathered it at, and moving `_systemctl_action`'s `sudo -n
systemctl` onto the one SSH restart executor (`services/service_restart.py`) needed room. Both the
generic `_execute_ssh` and the systemctl path report through `report_ssh`, so the two keep one
(success, output) contract.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Tuple

from services.service_restart import run_systemctl_over_ssh, systemctl_remote_command
from services.ssh_utils import ssh_destination

logger = logging.getLogger(__name__)

_SSH_TIMEOUT_S = 30.0


def ssh_base_cmd(ssh_user: str, ssh_key, host: str) -> list:
    """The ssh argv up to the host, without the remote command."""
    return [
        "/usr/bin/ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "BatchMode=yes",
        "-i",
        str(ssh_key),
        "--",
        ssh_destination(ssh_user, host),
    ]


async def spawn_ssh(ssh_cmd: list) -> tuple:
    """Run *ssh_cmd*; returns (returncode, stdout, stderr)."""
    process = await asyncio.create_subprocess_exec(
        *ssh_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=_SSH_TIMEOUT_S)
    return process.returncode, stdout, stderr


async def systemctl_sudo_call(ssh_base: list, action: str, service: str) -> tuple:
    """`sudo -n systemctl <action> <service>` through the one executor; (returncode, stdout, stderr)."""
    done = await run_systemctl_over_ssh(
        ssh_base, action, [service], use_noninteractive_sudo=True, timeout=_SSH_TIMEOUT_S
    )
    return done.returncode, done.stdout, done.stderr


def systemctl_user_cmd(action: str, service: str) -> str:
    """`systemctl --user <action> -- <service>` from the one builder; ValueError on a hostile value (#18359)."""
    return systemctl_remote_command(action, [service], user_scope=True)


async def report_ssh(call) -> Tuple[bool, str]:
    """Await *call* (an ssh run) as (success, output)."""
    try:
        returncode, stdout, stderr = await call
        if returncode == 0:
            output = stdout.decode("utf-8", errors="replace")
            return True, output or "Command completed successfully"
        error = stderr.decode("utf-8", errors="replace")
        return False, f"Command failed: {error[:500]}"
    except asyncio.TimeoutError:
        return False, "SSH command timed out"
    except Exception as e:
        logger.exception("SSH command error: %s", e)
        return False, "SSH command error"
