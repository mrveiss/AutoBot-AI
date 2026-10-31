# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Steps 8-9 of the Company OS workflow (#19253): a hire waits for approval; the audit log is complete."""

import pytest

from tests.company_os_e2e._scenario import step

pytestmark = pytest.mark.e2e

ACTOR_TYPES = {"user", "agent", "system"}
NEW_HIRE = {
    "agent_name": "Worker C",
    "org_role": "worker",
    "model": "claude-haiku-4-5-20251001",
    "adapter_type": "e2e_stub",
}

# (step, action the log must hold for it). Event names are the ActivityEventType values.
EXPECTED_ACTIONS = [
    (1, "company.created"),
    (2, "agent.hired"),
    (3, "work_item.created"),
    (4, "work_item.assigned"),
    (5, "heartbeat.started"),
    (5, "heartbeat.completed"),
    (7, "control.agent_paused"),
    (7, "control.agent_resumed"),
    (8, "approval.requested"),
    (8, "approval.approved"),
]


def _roster_names(api) -> list[str]:
    return [a["name"] for a in api.call("GET", f"/agents?company_id={api.company_id}")]


def test_step_8_approval_can_be_filed_and_decided(scenario):  # noqa: ANN001
    api = scenario.api
    scenario.require(2)
    with step(8):
        approval = api.call(
            "POST",
            "/approvals",
            json={
                "company_id": api.company_id,
                "type": "hire",
                "requested_by_agent_id": scenario.agents["ceo"]["node_id"],
                "payload": {"agent_name": NEW_HIRE["agent_name"]},
            },
        )
        assert approval["status"] == "pending", approval
        pending = api.call("GET", f"/approvals?company_id={api.company_id}&type=hire")
        assert approval["id"] in {p["id"] for p in pending}, "the filed approval is not in the pending list"
        decided = api.call("POST", f"/approvals/{approval['id']}/decide", json={"decision": "approved"})
        assert decided["status"] == "approved", decided
        scenario.ids["hire_approval"] = approval["id"]
        scenario.done.add(8)


@pytest.mark.xfail(
    reason="the hire route does not read require_approval_for_hires or an approval (#8214)", strict=False
)
def test_step_8_hire_happens_only_after_approval(scenario):  # noqa: ANN001
    api = scenario.api
    scenario.require(2)
    with step(8):
        api.call("PATCH", api.company(""), json={"require_approval_for_hires": True})
        # Never-approved hire: must be refused and must not appear on the roster.
        refused = api.refuse("POST", api.company("/agent-hires"), json=NEW_HIRE)
        assert refused.status_code in (403, 409, 422), f"unapproved hire answered {refused.status_code}"
        assert NEW_HIRE["agent_name"] not in _roster_names(api), "the unapproved hire is on the roster"
        scenario.require(8)
        hired = api.call(
            "POST", api.company("/agent-hires"), json={**NEW_HIRE, "approval_id": scenario.ids["hire_approval"]}
        )
        assert hired["agent_name"] == NEW_HIRE["agent_name"]
        assert NEW_HIRE["agent_name"] in _roster_names(api), "the approved hire is not on the roster"


@pytest.mark.xfail(reason="most services write no activity record (#20101; PR #20107)", strict=False)
def test_step_9_activity_log_holds_every_step(scenario):  # noqa: ANN001
    api = scenario.api
    scenario.require(1)
    with step(9):
        log = api.call("GET", api.company("/activity?page_size=200"))
        rows = log["items"]
        assert rows, "the activity log is empty"
        bad = [r["action"] for r in rows if r["actor_type"] not in ACTOR_TYPES]
        assert not bad, f"rows without a valid actor_type: {bad}"
        held = {r["action"] for r in rows}
        missing = [f"step {n}: {action}" for n, action in EXPECTED_ACTIONS if action not in held]
        assert not missing, f"activity log lacks {missing}; it holds {sorted(held)}"
