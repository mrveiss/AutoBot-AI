# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Step 5 of the Company OS workflow (#19253): a scheduled heartbeat run picks the task up.

Nothing here calls the scheduler. The agents were hired heartbeat-enabled, so the server wakes the
assignee itself: at once on the assignment event, then on its cron. The stubbed model call is the
only fake in the path.
"""

import pytest

from tests.company_os_e2e._scenario import WAKE_WINDOW_SECONDS, step, wait_for

pytestmark = pytest.mark.e2e


def test_step_5_heartbeat_run_is_dispatched_for_the_assignee(scenario):  # noqa: ANN001
    scenario.require(2, 4)
    agent = scenario.agent("a")["agent_id"]
    with step(5):
        woke = wait_for(lambda: scenario.stub_invocations(agent), WAKE_WINDOW_SECONDS)
        assert woke, f"agent was not dispatched within {WAKE_WINDOW_SECONDS:.0f}s of being assigned a ready task"
        runs = wait_for(lambda: [r for r in scenario.runs(agent) if r["status"] == "completed"], 60)
        assert runs, f"no completed run recorded for the agent: {scenario.runs(agent)}"
        scenario.done.add(5)


def test_step_5b_dispatched_run_takes_the_task(scenario):  # noqa: ANN001
    scenario.require(5)
    agent = scenario.agent("a")["agent_id"]
    task = scenario.ids["task"]
    with step("5b"):
        # Every run of the agent so far had a run-scoped key and its own API calls worked.
        calls = scenario.stub_invocations(agent)
        keyless = [c for c in calls if not c["has_key"]]
        assert not keyless, f"{len(keyless)} run(s) were dispatched without a run-scoped API key: {keyless[0]}"
        failed = [c for c in calls if c.get("error")]
        assert not failed, f"a woken agent's own API calls failed: {failed[0]['error']}"
        # One of them, now or within a wake window, takes THE task: an earlier wake may have found it
        # still in backlog.
        took = wait_for(
            lambda: [c for c in scenario.stub_invocations(agent) if c["work_item"] == task], WAKE_WINDOW_SECONDS
        )
        assert took, f"no run of the agent took the task {task}; runs: {scenario.stub_invocations(agent)}"
