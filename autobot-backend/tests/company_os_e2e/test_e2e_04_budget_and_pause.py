# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Steps 6-7 of the Company OS workflow (#19253): the dispatch gate.

Each gate check names a CONTROL: another agent with work and a clean record, which must be
dispatched at least twice in the interval. Only then is the subject's silence the claim. Setup is
asserted for real; the open bug is recorded with pytest.xfail at the one assertion that encodes it.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.company_os_e2e._helpers import (
    CONTROL_TASKS,
    make_ready_task,
    make_ready_tasks,
    observe_silence,
    set_paused_directly,
)
from tests.company_os_e2e._scenario import WAKE_WINDOW_SECONDS, step, wait_for

pytestmark = pytest.mark.e2e

GATE = "PR #19958 (dispatch gate: budget exhaustion, pause, terminate; issue #19240)"
# A local model has no price and needs no catalogue (a clean install has none, so a hosted model's
# cost event is refused as unpriced); its tokens still count against a TOKEN budget.
MODEL = "llama3"
HEADROOM_TOKENS = 1000
PAUSE_BUG_LOG = ("NoReferencedTableError", "llc_activity_log")


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
    a, b = scenario.agents["a"], scenario.agents["b"]
    with step(6):
        scenario.ids["t_budget"] = datetime.now(timezone.utc).isoformat()
        _exhaust(scenario.api, a["agent_id"])  # precondition: asserted, not xfailed

        def arrange() -> None:
            make_ready_task(scenario, "Exhausted agent's next task", a["node_id"])
            make_ready_tasks(scenario, "Control agent's task (budget)", b["node_id"], CONTROL_TASKS)

        control, subject = observe_silence(scenario, b["agent_id"], a["agent_id"], arrange)
        if subject:
            pytest.xfail(
                f"the exhausted agent was dispatched {subject} time(s) beside the control's {control}: "
                f"no dispatch gate until {GATE}; remove this xfail when it lands"
            )
        scenario.done.add(6)


def test_step_7_pause_and_resume_through_the_api(scenario):  # noqa: ANN001
    scenario.require(2)
    api, agent = scenario.api, scenario.agents["b"]["agent_id"]
    with step(7):
        pause = api.refuse("POST", api.company(f"/controls/agents/{agent}/pause"), json={"reason": "e2e"})
        if pause.status_code == 500:
            assert scenario.server_log_has(
                *PAUSE_BUG_LOG
            ), f"pause answered 500 and the server log does not show the known cause: {pause.text[:200]}"
            pytest.xfail(
                "pause returns 500: the activity-log write cannot resolve its organizations foreign key "
                "(#20150); remove this xfail when #20150 is fixed"
            )
        assert pause.status_code == 200 and pause.json()["status"] == "paused", (pause.status_code, pause.text[:200])
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


def test_step_7b_paused_agent_is_not_dispatched_until_resumed(scenario):  # noqa: ANN001
    scenario.require(2, 4)
    ceo, b = scenario.agents["ceo"], scenario.agents["b"]
    with step("7b"):
        direct = _pause(scenario, b["agent_id"])

        def arrange() -> None:
            make_ready_tasks(scenario, "Control agent's task (pause)", ceo["node_id"], CONTROL_TASKS)
            make_ready_task(scenario, "Paused agent's task", b["node_id"])

        control, subject = observe_silence(scenario, ceo["agent_id"], b["agent_id"], arrange)
        if subject:
            pytest.xfail(
                f"the paused agent was dispatched {subject} time(s) beside the control's {control}: "
                f"no dispatch gate until {GATE}; remove this xfail when it lands"
            )
        _resume(scenario, b["agent_id"], direct)
        before = len(scenario.stub_invocations(b["agent_id"]))
        woke = wait_for(lambda: len(scenario.stub_invocations(b["agent_id"])) > before, WAKE_WINDOW_SECONDS)
        assert woke, "the resumed agent was not dispatched again"
