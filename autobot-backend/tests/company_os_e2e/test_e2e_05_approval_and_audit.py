# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Steps 8-9 of the Company OS workflow (#19253): a hire waits for approval; the audit log is complete."""

from datetime import datetime

import pytest

from tests.company_os_e2e._expected_activity import EXPECTED, Expected
from tests.company_os_e2e._scenario import Scenario, step

pytestmark = pytest.mark.e2e

ACTOR_TYPES = {"user", "agent", "system"}
PAGE_SIZE = 200
NEW_HIRE = {
    "agent_name": "Worker C",
    "org_role": "worker",
    "model": "claude-haiku-4-5-20251001",
    "adapter_type": "e2e_stub",
}


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
                "requested_by_agent_id": scenario.agent("ceo")["node_id"],
                "payload": {"agent_name": NEW_HIRE["agent_name"]},
            },
        )
        assert approval["status"] == "pending", approval
        pending = api.call("GET", f"/approvals?company_id={api.company_id}&type=hire")
        assert approval["id"] in {p["id"] for p in pending}, "the filed approval is not in the pending list"
        decided = api.call("POST", f"/approvals/{approval['id']}/decide", json={"decision": "approved"})
        assert decided["status"] == "approved", decided
        scenario.ids["approval"] = approval["id"]
        scenario.done.add(8)


def test_step_8_hire_happens_only_after_approval(scenario):  # noqa: ANN001
    api = scenario.api
    scenario.require(2, 8)
    with step("8b"):
        api.call("PATCH", api.company(""), json={"require_approval_for_hires": True})  # precondition
        pending = api.refuse("POST", api.company("/agent-hires"), json=NEW_HIRE)
        assert pending.status_code == 202, f"a hire needing approval answered {pending.status_code}"
        assert NEW_HIRE["agent_name"] not in _roster_names(api), "the hire is on the roster before approval"
        approval_id = pending.json()["approval_id"]
        decided = api.call("POST", f"/approvals/{approval_id}/decide", json={"decision": "approved"})
        assert decided["status"] == "approved", decided
        assert NEW_HIRE["agent_name"] in _roster_names(api), "the approved hire is not on the roster"


def _all_rows(api) -> list[dict]:
    """Every activity row of the company, across all pages."""
    rows, page = [], 1
    while True:
        body = api.call("GET", api.company(f"/activity?page={page}&page_size={PAGE_SIZE}"))
        rows += body["items"]
        if not body["has_next"]:
            return rows
        page += 1


ENTITY_STEP = {"company": 1, "goal": 3, "project": 3, "epic": 3, "task": 3, "approval": 8}


def _entity_ids(scn: Scenario, key: str) -> set[str]:
    if key == "company":
        return {scn.api.company_id}
    if key.startswith("agent:"):
        agent = scn.agent(key.split(":", 1)[1])
        return {agent["agent_id"], agent["node_id"]}
    return {scn.need(key, ENTITY_STEP[key])}


def _candidates(scn: Scenario, rows: list[dict], want: Expected) -> list[dict]:
    ids = _entity_ids(scn, want.entity)
    since = datetime.fromisoformat(scn.need(want.after, 6)) if want.after else None
    return [
        r
        for r in rows
        if r["entity_id"] in ids
        and want.action in (None, r["action"])
        and (since is None or datetime.fromisoformat(r["occurred_at"]) >= since)
    ]


def _actor_ok(scn: Scenario, row: dict, want: Expected) -> bool:
    if row["actor_type"] != want.actor_type:
        return False
    if want.actor_type == "user":
        return row["actor_user_id"] == scn.stack.user_id
    return row["actor_user_id"] is None


def test_step_9_activity_log_holds_every_step(scenario):  # noqa: ANN001
    scenario.require(1)
    with step(9):
        rows = _all_rows(scenario.api)
        foreign = [r["id"] for r in rows if r["company_id"] != scenario.api.company_id]
        assert not foreign, f"rows of another company in this company's log: {foreign}"
        bad = [r["action"] for r in rows if r["actor_type"] not in ACTOR_TYPES]
        assert not bad, f"rows without a valid actor_type: {bad}"
        missing, wrong = [], []
        for want in EXPECTED:
            found = _candidates(scenario, rows, want)
            if not found:
                missing.append(want)
            elif not any(_actor_ok(scenario, r, want) for r in found):
                wrong.append(f"step {want.step} {want.action}: actors {sorted({r['actor_type'] for r in found})}")
        assert not wrong, f"records with the wrong actor (expected {[w for w in wrong]}): see rows"
        unowned = [f"step {w.step} {w.action}" for w in missing if not w.owner]
        assert not unowned, f"records missing with no open issue to explain them: {unowned}"
        if missing:
            listed = "; ".join(
                f"step {w.step} {w.action or 'any record'} ({w.owner}, writer: {w.writer})" for w in missing
            )
            pytest.xfail(
                f"{len(missing)} of {len(EXPECTED)} expected records absent: {listed}. Remove when #20101 lands"
            )
