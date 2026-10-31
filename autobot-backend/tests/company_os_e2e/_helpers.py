# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Small building blocks the scenario files share (#19253)."""

from __future__ import annotations

import asyncio
from typing import Callable

import asyncpg
import redis

from tests.company_os_e2e._scenario import WAKE_WINDOW_SECONDS, Scenario, wait_for

# Each dispatch of an agent takes (checks out) one task once the run key works, so an agent that
# must be dispatched repeatedly needs several ready tasks, not one.
CONTROL_TASKS = 3
CONTROL_DISPATCHES = 2
# The control's second dispatch is a full cron cycle after its first; allow for both.
SILENCE_WINDOW_SECONDS = WAKE_WINDOW_SECONDS * 2

# Mirrors ControlsService (llc/services/controls_service.py): the row's status and the Redis flag.
AGENT_PAUSED_KEY = "llc:agent:{agent_id}:paused"


def make_ready_task(scn: Scenario, title: str, assignee_node_id: str) -> str:
    """A task in the scenario's project, assigned to an agent and ready to be picked up."""
    api = scn.api
    item = api.call(
        "POST",
        "/work-items",
        json={
            "company_id": api.company_id,
            "type": "task",
            "title": title,
            "project_id": scn.ids["project"],
            "parent_id": scn.ids["epic"],
            "goal_id": scn.ids["goal"],
        },
    )
    api.call("PATCH", f"/work-items/{item['id']}", json={"assignee_agent_id": assignee_node_id})
    api.call("POST", f"/work-items/{item['id']}/transition", json={"status": "ready"})
    return item["id"]


def make_ready_tasks(scn: Scenario, title: str, assignee_node_id: str, count: int) -> None:
    for n in range(count):
        make_ready_task(scn, f"{title} {n + 1}", assignee_node_id)


def observe_silence(scn: Scenario, control: str, subject: str, arrange: Callable[[], None]) -> tuple[int, int]:
    """Baseline, ``arrange`` (which gives both agents work), then watch until the control has run twice.

    Returns (control, subject) new dispatches. The baselines are taken BEFORE ``arrange`` so a wake
    that assigning work triggers at once is counted, not missed. The control is an agent with work
    and a clean record; its second dispatch is one full cron cycle after its first, so the subject's
    silence across that interval is the claim. If the control does not reach two dispatches the
    scheduler is not working and nothing can be concluded: that raises, it is not a defect of the
    subject.
    """
    before_c, before_s = len(scn.stub_invocations(control)), len(scn.stub_invocations(subject))
    arrange()
    reached = wait_for(
        lambda: len(scn.stub_invocations(control)) - before_c >= CONTROL_DISPATCHES, SILENCE_WINDOW_SECONDS
    )
    new_c = len(scn.stub_invocations(control)) - before_c
    new_s = len(scn.stub_invocations(subject)) - before_s
    assert reached, (
        f"the control agent was dispatched {new_c} time(s) in {SILENCE_WINDOW_SECONDS:.0f}s, "
        f"fewer than {CONTROL_DISPATCHES}: the scheduler is not dispatching, so nothing can be said of the subject"
    )
    return new_c, new_s


async def _set_status(scn: Scenario, agent_id: str, paused: bool) -> None:
    run, db = scn.stack.run, scn.stack.database
    sql = (
        "UPDATE agent_org_nodes SET status = 'paused', pre_pause_status = 'available', paused_at = now() "
        "WHERE agent_id = $1"
        if paused
        else "UPDATE agent_org_nodes SET status = 'available', pre_pause_status = NULL, paused_at = NULL "
        "WHERE agent_id = $1"
    )
    conn = await asyncpg.connect(**run.pg_connect_args(db))
    try:
        await conn.execute(sql, agent_id)
    finally:
        await conn.close()


def set_paused_directly(scn: Scenario, agent_id: str, paused: bool) -> None:
    """Pause or resume an agent the way ControlsService does (row status plus Redis flag), bypassing the route.

    Used by the dispatch-gate check only when the pause ROUTE is itself broken (step 7 records that
    separately), so the gate can still be observed.
    """
    asyncio.run(_set_status(scn, agent_id, paused))
    admin = scn.stack.admin
    client = redis.Redis(host=admin.redis_host, port=admin.redis_port)
    try:
        key = AGENT_PAUSED_KEY.format(agent_id=agent_id)
        client.set(key, "1") if paused else client.delete(key)
    finally:
        client.close()
