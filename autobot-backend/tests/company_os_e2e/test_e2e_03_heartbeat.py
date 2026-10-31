# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Step 5 of the Company OS workflow (#19253): a scheduled heartbeat run picks the task up.

Nothing here calls the scheduler. The agents were hired heartbeat-enabled, so the server's own
scheduler wakes the assignee on its cron; the stubbed model call is the only fake in the path.
"""

import pytest

from tests.company_os_e2e._scenario import WAKE_WINDOW_SECONDS, step, wait_for

pytestmark = pytest.mark.e2e


def test_step_5_heartbeat_run_is_dispatched_for_the_assignee(scenario):  # noqa: ANN001
    scenario.require(2, 4)
    agent = scenario.agents["a"]["agent_id"]
    with step(5):
        woke = wait_for(lambda: scenario.stub_invocations(agent), WAKE_WINDOW_SECONDS)
        assert woke, f"agent was not dispatched within {WAKE_WINDOW_SECONDS:.0f}s of being assigned a ready task"
        runs = wait_for(lambda: [r for r in scenario.runs(agent) if r["status"] == "completed"], 60)
        assert runs, f"no completed run recorded for the agent: {scenario.runs(agent)}"
        scenario.done.add(5)


def test_step_5b_dispatched_run_takes_the_task(scenario):  # noqa: ANN001
    scenario.require(5)
    agent = scenario.agents["a"]["agent_id"]
    with step("5b"):
        call = scenario.stub_invocations(agent)[0]
        assert call["has_key"], f"the run was dispatched without a run-scoped API key; stub saw {call}"
        assert call.get("error") is None, f"the woken agent's own API calls failed: {call.get('error')}"
        assert call["work_item"] == scenario.ids["task"], f"agent checked out {call['work_item']!r}"
