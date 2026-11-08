# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Steps 1-2 of the Company OS workflow (#19253): a company, then a CEO and two agents."""

import pytest

from tests.company_os_e2e._scenario import step

pytestmark = pytest.mark.e2e

COMPANY_NAME = "AutoBot LLC"
STUB = "e2e_stub"
HEARTBEAT_CRON = "* * * * *"


def _hire(api, name: str, role: str) -> dict:
    hired = api.call(
        "POST",
        api.company("/agent-hires"),
        json={
            "agent_name": name,
            "org_role": role,
            "model": "claude-haiku-4-5-20251001",
            "adapter_type": STUB,
            "heartbeat_enabled": True,
            "heartbeat_cron": HEARTBEAT_CRON,
        },
    )
    roster = api.call("GET", f"/agents?company_id={api.company_id}")
    node = next(a for a in roster if a["agent_id"] == hired["agent_id"])
    return {"agent_id": hired["agent_id"], "node_id": node["org_node_id"]}


def test_step_1_create_company(scenario):  # noqa: ANN001
    api = scenario.api
    with step(1):
        company = api.call("POST", "/companies/", json={"name": COMPANY_NAME, "issue_prefix": "ABL"})
        api.select_company(company["id"])
        assert company["name"] == COMPANY_NAME
        mine = api.call("GET", "/companies/")
        assert any(c["id"] == company["id"] for c in mine), "the creator cannot see the company they created"
        scenario.done.add(1)


def test_step_2_hire_ceo_and_two_agents(scenario):  # noqa: ANN001
    api = scenario.api
    scenario.require(1)
    with step(2):
        for key, name, role in (("ceo", "CEO", "manager"), ("a", "Worker A", "worker"), ("b", "Worker B", "worker")):
            scenario.agents[key] = _hire(api, name, role)
        ceo = scenario.agents["ceo"]
        designated = api.call("PUT", api.company("/ceo"), json={"holder_type": "agent", "holder_id": ceo["node_id"]})
        assert designated["holder_exists"] is True
        roster = api.call("GET", f"/agents?company_id={api.company_id}")
        enabled = [a for a in roster if a["heartbeat_enabled"]]
        assert len(enabled) == 3, f"expected 3 heartbeat-enabled agents, roster shows {len(enabled)}"
        scenario.done.add(2)
