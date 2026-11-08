# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Steps 6-7 of the Company OS workflow (#19253): the dispatch gate.

Each gate check names a CONTROL: another agent with work and a clean record, which must be
dispatched at least twice in the interval. Only then is the subject's silence the claim. Setup is
asserted for real, and the gate itself (#19240) is asserted, so a dispatch beside the control is a failure.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from autobot_shared.logging_manager import get_logger
from llc.scheduler.dispatch_gate import BUDGET_EXHAUSTED
from tests.company_os_e2e._helpers import (
    CONTROL_TASKS,
    agent_is_active,
    make_ready_task,
    make_ready_tasks,
    observe_silence,
    quiesce,
    set_paused_directly,
)
from tests.company_os_e2e._scenario import WAKE_WINDOW_SECONDS, step, wait_for

pytestmark = pytest.mark.e2e
logger = get_logger(__name__)

# A local model has no price and needs no catalogue (a clean install has none, so a hosted model's
# cost event is refused as unpriced); its tokens still count against a TOKEN budget.
MODEL = "llama3"
HEADROOM_TOKENS = 1000


def _remaining(api, agent_id: str) -> int:
    return int(Decimal(api.call("GET", f"/budget/{agent_id}")["remaining"]))


def _exhaust(api, agent_id: str) -> None:
    """Spend the token budget to exactly its limit, then prove one more event is refused.

    The limit is set relative to what is ALREADY spent (a run that took the key spends tokens of its
    own), and the spend is exactly the remainder: the event that crosses the limit is refused with
    402 and rolled back, so the stored row never reads over-limit; it reads exhausted at remaining 0.
    """
    spent = int(api.call("GET", f"/budget/{agent_id}")["tokens_spent"])
    api.call(
        "PATCH", f"/budget/{agent_id}/limit", json={"budget_mode": "tokens", "token_limit": spent + HEADROOM_TOKENS}
    )
    for _ in range(3):
        left = _remaining(api, agent_id)
        if left <= 0:
            break
        event = {"tokens_in": left, "tokens_out": 0, "model": MODEL}
        api.call("POST", f"/budget/{agent_id}/ingest", json=event)
    assert (
        _remaining(api, agent_id) <= 0
    ), f"budget row does not read exhausted: {api.call('GET', f'/budget/{agent_id}')}"
    over = api.refuse("POST", f"/budget/{agent_id}/ingest", json={"tokens_in": 1, "tokens_out": 0, "model": MODEL})
    assert over.status_code == 402, f"a further event on an exhausted budget answered {over.status_code}"


def test_step_6_exhausted_budget_is_not_dispatched(scenario):  # noqa: ANN001
    scenario.require(2, 4)
    a, b = scenario.agent("a"), scenario.agent("b")
    with step(6):
        # quiesce() is a point-in-time check: it returns the moment no run is in flight, and a heartbeat or
        # assignment wake can start the next run right after, which then spends tokens between _exhaust's
        # read and its ingest (#21166, #20830). Pausing makes the agent ineligible for dispatch FIRST, so
        # waiting for the run table to settle stays true while the limit is set and exhausted.
        direct = _pause(scenario, a["agent_id"])
        try:
            quiesce(scenario, a["agent_id"])  # no new run can start; wait out the one already running
            scenario.ids["t_budget"] = datetime.now(timezone.utc).isoformat()
            _exhaust(scenario.api, a["agent_id"])  # precondition: asserted, not xfailed
        except BaseException:
            _resume_logging_failure(scenario, a["agent_id"], direct)  # the original error is the one reported
            raise
        _resume(scenario, a["agent_id"], direct)  # eligible again: only the exhausted budget may now stop it
        # Silence only means "the budget stopped it" if nothing else can: read the agent back as active.
        active = wait_for(lambda: agent_is_active(scenario, a["agent_id"]), WAKE_WINDOW_SECONDS)
        assert active, f"agent is not eligible after the resume, so its silence would not be the budget's: {a}"

        def arrange() -> None:
            make_ready_task(scenario, "Exhausted agent's next task", a["node_id"])
            make_ready_tasks(scenario, "Control agent's task (budget)", b["node_id"], CONTROL_TASKS)

        control, subject = observe_silence(scenario, b["agent_id"], a["agent_id"], arrange)
        assert not subject, f"the exhausted agent was dispatched {subject} time(s) beside the control's {control}"
        # Positive signal: the scheduler's only record of a budget refusal is this log line (heartbeat_scheduler.py
        # "Heartbeat skipped for agent %s: %s" with dispatch_gate.BUDGET_EXHAUSTED); no run or activity row is written.
        refused = wait_for(
            lambda: scenario.server_log_has(f"Heartbeat skipped for agent {a['agent_id']}: {BUDGET_EXHAUSTED}"),
            WAKE_WINDOW_SECONDS,
        )
        assert refused, f"the scheduler never recorded a budget refusal for agent {a['agent_id']}"
        scenario.done.add(6)


def test_step_7_pause_and_resume_through_the_api(scenario):  # noqa: ANN001
    scenario.require(2)
    api, agent = scenario.api, scenario.agent("b")["agent_id"]
    with step(7):
        paused = api.call("POST", api.company(f"/controls/agents/{agent}/pause"), json={"reason": "e2e"})
        assert paused["status"] == "paused", paused
        resumed = api.call("POST", api.company(f"/controls/agents/{agent}/resume"))
        assert resumed["status"] != "paused", resumed
        scenario.done.add(7)


def _pause(scenario, agent: str) -> bool:  # noqa: ANN001
    """Pause through the route; if the route is broken (step 7 records that), pause directly. True if direct."""
    api = scenario.api
    resp = api.refuse("POST", api.company(f"/controls/agents/{agent}/pause"), json={"reason": "e2e"})
    if resp.status_code == 200:
        return False
    assert resp.status_code == 500, f"pause answered {resp.status_code} {resp.text[:200]}"
    set_paused_directly(scenario, agent, True)
    return True


def _resume(scenario, agent: str, direct: bool) -> None:  # noqa: ANN001
    if direct:
        set_paused_directly(scenario, agent, False)
    else:
        scenario.api.call("POST", scenario.api.company(f"/controls/agents/{agent}/resume"))


def _resume_logging_failure(scenario, agent: str, direct: bool) -> None:  # noqa: ANN001
    """Resume on the error path: a failure here is logged, never allowed to replace the error being handled."""
    try:
        _resume(scenario, agent, direct)
    except Exception:
        logger.exception("Could not resume agent %s after a failed step 6", agent)


def test_step_7b_paused_agent_is_not_dispatched_until_resumed(scenario):  # noqa: ANN001
    scenario.require(2, 4)
    ceo, b = scenario.agent("ceo"), scenario.agent("b")
    with step("7b"):
        quiesce(scenario, b["agent_id"])
        direct = _pause(scenario, b["agent_id"])

        def arrange() -> None:
            make_ready_tasks(scenario, "Control agent's task (pause)", ceo["node_id"], CONTROL_TASKS)
            make_ready_task(scenario, "Paused agent's task", b["node_id"])

        control, subject = observe_silence(scenario, ceo["agent_id"], b["agent_id"], arrange)
        assert not subject, f"the paused agent was dispatched {subject} time(s) beside the control's {control}"
        _resume(scenario, b["agent_id"], direct)
        before = len(scenario.stub_invocations(b["agent_id"]))
        woke = wait_for(lambda: len(scenario.stub_invocations(b["agent_id"])) > before, WAKE_WINDOW_SECONDS)
        assert woke, "the resumed agent was not dispatched again"
