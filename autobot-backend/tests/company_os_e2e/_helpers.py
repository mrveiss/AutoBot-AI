# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Small building blocks the scenario files share (#19253)."""

from __future__ import annotations

import time
from typing import Callable

from tests.company_os_e2e._scenario import WAKE_WINDOW_SECONDS, Scenario, wait_for

# Longer than the scheduler's poll interval, so a wake that was going to happen in the same
# cron minute as the control's has happened before the absence of the subject's is read.
GRACE_SECONDS = 15.0


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


def observe_wake(scn: Scenario, control: str, subject: str, arrange: Callable[[], None]) -> tuple[int, int]:
    """Run ``arrange`` (which gives both agents work), then watch one wake window.

    Returns (control, subject) new dispatches. Counts are taken BEFORE ``arrange`` so a wake that
    work assignment triggers at once is counted, not missed. The control is an agent that has work
    and is allowed to run: seeing it dispatched is what makes the subject's silence mean
    something, since "not dispatched" is also what a scheduler that is not running looks like.
    """
    before_c, before_s = len(scn.stub_invocations(control)), len(scn.stub_invocations(subject))
    arrange()
    woke = wait_for(lambda: len(scn.stub_invocations(control)) > before_c, WAKE_WINDOW_SECONDS)
    time.sleep(GRACE_SECONDS)
    new_c = len(scn.stub_invocations(control)) - before_c
    new_s = len(scn.stub_invocations(subject)) - before_s
    assert woke, "the control agent was never dispatched, so no conclusion about the subject can be drawn"
    return new_c, new_s
