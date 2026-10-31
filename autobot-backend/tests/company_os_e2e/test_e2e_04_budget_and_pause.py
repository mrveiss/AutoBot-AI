# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Steps 6-7 of the Company OS workflow (#19253): the dispatch gate.

Each check names a CONTROL: another agent with work and a clean record, dispatched in the same
window. "Subject was not dispatched" only means something next to "control was".
"""

from decimal import Decimal

import pytest

from tests.company_os_e2e._helpers import make_ready_task, observe_wake
from tests.company_os_e2e._scenario import WAKE_WINDOW_SECONDS, step, wait_for

pytestmark = pytest.mark.e2e

# Open PRs that make the gate real; an XPASS here is the signal to remove the marker.
GATE_PR = "PR #19958 (dispatch gate: budget exhaustion, pause, terminate; issue #19240)"
# A local model has no price and needs no catalogue (a clean install has none, so a hosted model's
# cost event is refused as unpriced); its tokens still count against a TOKEN budget.
MODEL = "llama3"
TOKEN_LIMIT = 1000


def _exhaust(api, agent_id: str) -> None:
    """Spend the token budget to exactly its limit, then prove one more event is refused.

    Exactly the limit, not past it: the event that crosses the limit is refused with 402 and
    rolled back, so the stored row never reads over-limit. The row reads exhausted at remaining 0.
    """
    api.call("PATCH", f"/budget/{agent_id}/limit", json={"budget_mode": "tokens", "token_limit": TOKEN_LIMIT})
    half = TOKEN_LIMIT // 2
    api.call("POST", f"/budget/{agent_id}/ingest", json={"tokens_in": half, "tokens_out": half, "model": MODEL})
    row = api.call("GET", f"/budget/{agent_id}")
    assert Decimal(row["remaining"]) <= 0, f"budget row does not read exhausted: {row}"
    over = api.refuse("POST", f"/budget/{agent_id}/ingest", json={"tokens_in": 1, "tokens_out": 0, "model": MODEL})
    assert over.status_code == 402, f"a further event on an exhausted budget answered {over.status_code}"


@pytest.mark.xfail(reason=f"scheduled dispatch ignores budget exhaustion until {GATE_PR}", strict=False)
def test_step_6_exhausted_budget_is_not_dispatched(scenario):  # noqa: ANN001
    scenario.require(2, 4)
    a, b = scenario.agents["a"], scenario.agents["b"]
    with step(6):
        _exhaust(scenario.api, a["agent_id"])

        def arrange() -> None:
            make_ready_task(scenario, "Exhausted agent's next task", a["node_id"])
            make_ready_task(scenario, "Control agent's task (budget)", b["node_id"])

        control, subject = observe_wake(scenario, b["agent_id"], a["agent_id"], arrange)
        assert subject == 0, f"the agent with an exhausted budget was dispatched {subject} time(s); control {control}"
        scenario.done.add(6)


def test_step_7_pause_and_resume_through_the_api(scenario):  # noqa: ANN001
    scenario.require(2)
    api, agent = scenario.api, scenario.agents["b"]["agent_id"]
    with step(7):
        paused = api.call("POST", api.company(f"/controls/agents/{agent}/pause"), json={"reason": "e2e"})
        assert paused["status"] == "paused", paused
        resumed = api.call("POST", api.company(f"/controls/agents/{agent}/resume"))
        assert resumed["status"] != "paused", resumed
        scenario.done.add(7)


@pytest.mark.xfail(reason=f"scheduled dispatch ignores pause until {GATE_PR}", strict=False)
def test_step_7b_paused_agent_is_not_dispatched_until_resumed(scenario):  # noqa: ANN001
    scenario.require(2, 4, 7)
    ceo, b = scenario.agents["ceo"], scenario.agents["b"]
    api = scenario.api
    with step("7b"):
        api.call("POST", api.company(f"/controls/agents/{b['agent_id']}/pause"), json={"reason": "e2e"})

        def arrange() -> None:
            make_ready_task(scenario, "Control agent's task (pause)", ceo["node_id"])
            make_ready_task(scenario, "Paused agent's task", b["node_id"])

        control, subject = observe_wake(scenario, ceo["agent_id"], b["agent_id"], arrange)
        assert subject == 0, f"the paused agent was dispatched {subject} time(s); control {control}"
        api.call("POST", api.company(f"/controls/agents/{b['agent_id']}/resume"))
        before = len(scenario.stub_invocations(b["agent_id"]))
        woke = wait_for(lambda: len(scenario.stub_invocations(b["agent_id"])) > before, WAKE_WINDOW_SECONDS)
        assert woke, "the resumed agent was not dispatched again"
