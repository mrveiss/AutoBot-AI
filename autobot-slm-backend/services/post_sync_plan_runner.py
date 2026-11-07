# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Execute one node's ordered post-sync plan, recording every action (#17455).

The caller (api/node_post_sync.py) builds the plan -- every role's actions through
``ordered_post_sync_plan`` -- and this module only runs it, top to bottom, through
``post_sync_runner``. One implementation of "run post-sync work": the node route and
the role route both come here.

Failure semantics (the same as the per-role path before #17455, which returned on a
failed post-sync before restarting or marking the role synced):

* a failed install/schema/build/post-sync command ABORTS the plan: nothing after it
  runs, restarts included, and the caller marks no role on the node synced;
* a failed RESTART is recorded and logged but does NOT abort or fail the sync
  (owner decision 3: "records failures"); its row carries ``success=False``.

The self-killing unit (``defer_units``, passed in by the caller from ``_post_sync_plan``,
only on the node this SLM runs on) is NOT run by ``execute_plan``: its action is returned in
``PlanResult.deferred``. The caller records role versions, then ``record_issued`` commits an
*issued* row (``success=None``) per deferred restart, the response goes out, and only then
``issue_deferred`` sends the restart that may end this process. If that restart returns (the
process survived, e.g. ``sudo -n`` refused it), ``restart_units`` records the real outcome as
a follow-up row, so a failure is never left as "issued".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Iterable

from autobot_shared.ssot_config import config
from services.post_sync_recorder import ActionOutcome, RunContext, record_action_run
from services.post_sync_runner import (
    recorded_restart_command,
    restart_ssh_base,
    restart_units,
    run_post_sync_command,
    units_are_valid,
)
from services.post_sync_timeouts import POST_SYNC_TIMEOUT_S
from services.ssh_utils import build_ssh_base_cmd

logger = logging.getLogger(__name__)

_RESTART = "restart"


@dataclass(frozen=True)
class NodeConn:
    """How to reach one node over SSH."""

    node_id: str
    ip: str
    user: str
    port: int


@dataclass(frozen=True)
class DeferredRestart:
    """A self-killing restart held back until the response is out."""

    action: object
    conn: NodeConn
    rec: RunContext


@dataclass
class PlanResult:
    """Recorded rows in execution order; ``aborted`` when a non-restart action failed."""

    rows: list = field(default_factory=list)
    aborted: bool = False
    skipped: list = field(default_factory=list)  # labels of actions never run because of the abort
    deferred: list = field(default_factory=list)  # DeferredRestart, issued after the response


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _run_command(action, conn: NodeConn, rec: RunContext) -> ActionOutcome:
    ssh_base = build_ssh_base_cmd(conn.ip, conn.user, conn.port, config.path.ssh_key_path)
    return await run_post_sync_command(
        ssh_base, action.command, POST_SYNC_TIMEOUT_S, rec, action.label, action.category
    )


async def _run_action(action, conn: NodeConn, rec: RunContext) -> ActionOutcome:
    if action.category == _RESTART:
        ssh_base = restart_ssh_base(conn.ip, conn.user, conn.port)
        return await restart_units(ssh_base, action.systemd_service.split(), rec)
    return await _run_command(action, conn, rec)


def _is_deferred(action, defer_units: Iterable[str]) -> bool:
    units = (action.systemd_service or "").split() if action.category == _RESTART else []
    # an invalid unit is never issued: it runs now so restart_units records the refusal as a failure (#18359)
    return bool(units) and units_are_valid(units) and all(unit in defer_units for unit in units)


async def execute_plan(
    actions: Iterable, conn: NodeConn, rec: RunContext, defer_units: Iterable[str] = ()
) -> PlanResult:
    """Run *actions* in the order given; see the module docstring for failure semantics."""
    result = PlanResult()
    ran: set[tuple] = set()
    pending = list(actions)
    for index, action in enumerate(pending):
        action_rec = replace(rec, role_name=action.role_name)
        if _is_deferred(action, defer_units):
            result.deferred.append(DeferredRestart(action, conn, action_rec))
            continue
        key = (action.role_name, action.command)
        if action.category != _RESTART and key in ran:
            continue  # one role's command can classify as schema AND build; run it once
        ran.add(key)
        outcome = await _run_action(action, conn, action_rec)
        if outcome.row is not None:
            result.rows.append(outcome.row)
        if action.category != _RESTART and not outcome.success:
            result.aborted, result.deferred = True, []
            result.skipped = [a.label for a in pending[index + 1 :]]
            break
    return result


async def record_issued(result: PlanResult) -> None:
    """Commit an *issued* row (success unknown) per deferred restart, BEFORE any is sent."""
    msg = "issued; outcome unknown (this restart may end the SLM process before one exists)"
    for item in result.deferred:
        units = item.action.systemd_service.split()
        joined = " ".join(units)
        now = _now()
        command = recorded_restart_command(units)
        row = await record_action_run(
            item.rec, _RESTART, f"Restart {joined}", command, joined, ActionOutcome(None, None, "", msg, now, now)
        )
        if row is not None:
            result.rows.append(row)


async def issue_deferred(pending: Iterable[DeferredRestart]) -> None:
    """Send the held-back restarts. One that returns (the process survived) records its real
    outcome -- refused, timed out or done -- as a follow-up row."""
    for item in pending:
        base = restart_ssh_base(item.conn.ip, item.conn.user, item.conn.port)
        await restart_units(base, item.action.systemd_service.split(), item.rec)
