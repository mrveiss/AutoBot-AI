# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run a role's post-sync command and restart over SSH, recording each (#17455).

Extracted from `services/sync_orchestrator.py` (pinned at its file-size ceiling).
Each function returns a structured `ActionOutcome` -- exit code, output tail,
start/finish -- instead of logging and discarding it, and writes one
`post_sync_action_runs` row when given a `RunContext`.

The restart uses `sudo -n` and `BatchMode=yes` (#17455, owner decision
2026-10-10): without NOPASSWD sudo it fails at once instead of waiting out the
timeout on a password prompt nobody can answer, and the failure is recorded.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Sequence

from services.post_sync_recorder import OUTPUT_TAIL_MAX, ActionOutcome, RunContext, record_action_run
from services.post_sync_timeouts import RESTART_TIMEOUT_S
from services.service_restart import build_service_ssh_base_cmd, run_systemctl_over_ssh, systemctl_remote_command
from services.unit_names import validate_unit_name

logger = logging.getLogger(__name__)


def restart_ssh_base(node_ip: str, node_user: str, node_port: int) -> list:
    """The canonical restart ssh argv (carries `BatchMode=yes`), built by the one existing builder."""
    node = SimpleNamespace(ip_address=node_ip, ssh_user=node_user, ssh_port=node_port)
    return build_service_ssh_base_cmd(node)  # builder reads only these three attributes


def _tail(raw: bytes | None) -> str:
    return (raw or b"").decode("utf-8", errors="replace").strip()[-OUTPUT_TAIL_MAX:]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _failed(started: datetime, error: str, *, exit_code: int | None = None, tail: str = "") -> ActionOutcome:
    return ActionOutcome(False, exit_code, tail, error, started, _now())


async def _spawn_and_wait(ssh_cmd: list, timeout: float) -> tuple[int | None, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *ssh_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, stdout


async def _post_sync_outcome(ssh_base: list, command: str, timeout: float) -> ActionOutcome:
    started = _now()
    try:
        code, stdout = await _spawn_and_wait([*ssh_base, command], timeout)
    except asyncio.TimeoutError:
        return _failed(started, f"timed out after {timeout}s")
    except Exception as e:
        return _failed(started, str(e) or type(e).__name__)
    tail = _tail(stdout)
    if code != 0:
        return _failed(started, f"exit {code}", exit_code=code, tail=tail)
    return ActionOutcome(True, code, tail, None, started, _now())


async def run_post_sync_command(
    ssh_base: list,
    command: str,
    timeout: float,
    rec: RunContext | None = None,
    label: str = "Post-sync command",
    category: str = "post_sync",
) -> ActionOutcome:
    """Run *command* on the node; a non-zero exit, timeout or spawn error is a failed outcome."""
    outcome = await _post_sync_outcome(ssh_base, command, timeout)
    if not outcome.success:
        logger.error("Post-sync command failed (%s): %s", outcome.error, outcome.output_tail)
    if rec is None:
        return outcome
    return replace(outcome, row=await record_action_run(rec, category, label, command, None, outcome))


async def _restart_outcome(ssh_base: list, units: Sequence[str]) -> ActionOutcome:
    started = _now()
    try:
        res = await run_systemctl_over_ssh(
            ssh_base,
            "restart",
            units,  # #16025: >1 unit, one call
            use_noninteractive_sudo=True,
            timeout=RESTART_TIMEOUT_S,
            merge_stderr=True,
        )
    except asyncio.TimeoutError:
        return _failed(started, f"timed out after {RESTART_TIMEOUT_S}s")
    except Exception as e:
        return _failed(started, str(e) or type(e).__name__)
    tail = _tail(res.stdout)
    if res.returncode != 0:
        return _failed(started, f"exit {res.returncode}", exit_code=res.returncode, tail=tail)
    return ActionOutcome(True, res.returncode, tail, None, started, _now())


def units_are_valid(units: Sequence[str]) -> bool:
    """True when every unit passes `validate_unit_name`; an invalid one is recorded as a failure, never run (#18359)."""
    try:
        for unit in units:
            validate_unit_name(unit)
    except ValueError:
        return False
    return True


def recorded_restart_command(units: Sequence[str]) -> str:
    """The exact remote line (validated, quoted) for the audit row; a rejected unit is named as such (#18359)."""
    if not units_are_valid(units):
        return "systemctl restart (rejected: invalid unit name)"
    return systemctl_remote_command("restart", units, use_noninteractive_sudo=True)


async def restart_units(ssh_base: list, units: Sequence[str], rec: RunContext | None = None) -> ActionOutcome:
    """`sudo -n systemctl restart <units>` in one call; every failure mode is a failed outcome.

    A failed restart is recorded and logged as a warning; it is the caller's choice whether it
    fails the sync (#17455 decision 3: it does not).
    """
    outcome = await _restart_outcome(ssh_base, units)
    joined = " ".join(units)
    if outcome.success:
        logger.info("Restarted %s", joined)
    else:
        logger.warning("Service restart failed: %s", outcome.error)
    if rec is None:
        return outcome
    command = recorded_restart_command(units)
    return replace(outcome, row=await record_action_run(rec, "restart", f"Restart {joined}", command, joined, outcome))
