# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Steps 3-4 of the Company OS workflow (#19253): a goal, a project, work items, an assignment."""

import pytest

from tests.company_os_e2e._scenario import step, wait_for

pytestmark = pytest.mark.e2e


def _project(api, goal_id: str) -> str:
    body = {"company_id": api.company_id}
    portfolio = api.call("POST", api.company("/portfolios"), json={**body, "name": "Launch"})
    program = api.call("POST", f"/portfolios/{portfolio['id']}/programs", json={**body, "name": "Launch program"})
    project = api.call(
        "POST", f"/programs/{program['id']}/projects", json={**body, "name": "First release", "goal_id": goal_id}
    )
    return project["id"]


def _item(api, scn, item_type: str, title: str, parent_id: str | None = None) -> str:
    body = {
        "company_id": api.company_id,
        "type": item_type,
        "title": title,
        "project_id": scn.ids["project"],
        "goal_id": scn.ids["goal"],
    }
    if parent_id:
        body["parent_id"] = parent_id
    return api.call("POST", "/work-items", json=body)["id"]


def _titles_in_project(api, project_id: str) -> set[str]:
    listed = api.call("GET", f"/work-items?company_id={api.company_id}&project_id={project_id}")
    return {i["title"] for i in (listed if isinstance(listed, list) else listed.get("items", []))}


def test_step_3_goal_project_and_work_items(scenario):  # noqa: ANN001
    api = scenario.api
    scenario.require(1)
    with step(3):
        body = {"company_id": api.company_id, "title": "Ship the first release", "level": "objective"}
        scenario.ids["goal"] = api.call("POST", "/goals", json=body)["id"]
        scenario.ids["project"] = _project(api, scenario.ids["goal"])
        scenario.ids["epic"] = _item(api, scenario, "epic", "Release readiness")
        # A task sits under a PBI, a PBI under an epic (work_item_hierarchy.ALLOWED_PARENT_TYPES, #18978).
        scenario.ids["pbi"] = _item(api, scenario, "pbi", "Release notes", scenario.ids["epic"])
        scenario.ids["task"] = _item(api, scenario, "task", "Write the release notes", scenario.ids["pbi"])
        titles = _titles_in_project(api, scenario.ids["project"])
        assert {
            "Release readiness",
            "Release notes",
            "Write the release notes",
        } <= titles, f"project items: {sorted(titles)}"
        scenario.done.add(3)


def test_step_4_assign_a_task(scenario):  # noqa: ANN001
    api = scenario.api
    scenario.require(2, 3)
    with step(4):
        node = scenario.agent("a")["node_id"]
        agent_id = scenario.agent("a")["agent_id"]
        item_id = scenario.ids["task"]
        api.call("PATCH", f"/work-items/{item_id}", json={"assignee_agent_id": node})
        api.call("POST", f"/work-items/{item_id}/transition", json={"status": "ready"})
        item = api.call("GET", f"/work-items/{item_id}")
        assert item["assignee_agent_id"] == node, f"assignee is {item['assignee_agent_id']!r}, expected {node!r}"
        # Assigning wakes the assignee at once, so by the time of this read its run may already hold the
        # task. That is ready or in_progress under the assignee; anything else, or in_progress with no
        # run of the assignee that took it, is something else moving the task.
        assert item["status"] in ("ready", "in_progress"), f"status is {item['status']!r}"
        if item["status"] == "in_progress":
            took = wait_for(lambda: [c for c in scenario.stub_invocations(agent_id) if c["work_item"] == item_id], 60)
            assert took, "the task is in_progress under its assignee but no run of the assignee took it"
        scenario.done.add(4)
