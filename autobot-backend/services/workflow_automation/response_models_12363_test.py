# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Each typed workflow-automation route returns a body its response model accepts (#12363).

The models in ``response_models.py`` must describe what the handlers return today. These tests
drive every route through FastAPI (so ``response_model`` validates the real payload) with a real
``ActiveWorkflow`` supplying the status shape, and check the error bodies match the error model.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from services.workflow_automation import routes
from services.workflow_automation.models import ActiveWorkflow, WorkflowStep
from services.workflow_automation.response_models import (
    AutomationWorkflowListResponse,
    AutomationWorkflowStatusResponse,
    WorkflowErrorResponse,
)

_USER = {"user_id": "u-1", "role": "admin"}


class _Manager:
    def __init__(self, workflow: ActiveWorkflow | None):
        self.active_workflows = {workflow.workflow_id: workflow} if workflow else {}
        self.completed_workflows = {}
        self.accept = True

    async def create_automated_workflow(self, **_kwargs):
        return "wf-1"

    async def start_workflow_execution(self, _workflow_id):
        return self.accept

    async def handle_workflow_control(self, _request):
        return self.accept

    def get_workflow_status(self, workflow_id):
        workflow = self.active_workflows.get(workflow_id)
        return workflow.to_status_dict() if workflow else None

    def get_completed_workflows(self):
        return [w.to_status_dict() for w in self.completed_workflows.values()]


def _workflow() -> ActiveWorkflow:
    step = WorkflowStep(step_id="step_1", command="echo hi", description="say hi", risk_level="low")
    return ActiveWorkflow(workflow_id="wf-1", name="n", description="d", session_id="s", steps=[step], owner_id="u-1")


@pytest.fixture
def manager(monkeypatch):
    manager = _Manager(_workflow())
    monkeypatch.setattr(routes, "get_workflow_manager", lambda: manager)
    monkeypatch.setattr(routes, "require_command_permission", lambda _user: None)
    return manager


@pytest.fixture
def client(manager):
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_current_user] = lambda: dict(_USER)
    return TestClient(app, raise_server_exceptions=False)


def test_create_workflow_returns_the_created_shape(client):
    body = {"name": "w", "description": "", "steps": [], "session_id": "s"}
    response = client.post("/create_workflow", json=body)
    assert response.status_code == 200
    assert set(response.json()) == {"success", "workflow_id", "message"}


def test_start_and_control_return_the_action_shape(client):
    start = client.post("/start_workflow/wf-1")
    control = client.post("/control_workflow", json={"workflow_id": "wf-1", "action": "pause"})
    assert start.status_code == control.status_code == 200
    assert set(start.json()) == set(control.json()) == {"success", "message"}


def test_status_body_validates_against_the_model_without_losing_a_field(client, manager):
    response = client.get("/workflow_status/wf-1")
    assert response.status_code == 200
    assert response.json()["workflow"] == manager.get_workflow_status("wf-1")
    AutomationWorkflowStatusResponse.model_validate(response.json())


@pytest.mark.parametrize("path", ["/active_workflows", "/completed_workflows"])
def test_list_routes_return_every_status_field(client, manager, path):
    if path == "/completed_workflows":
        manager.completed_workflows, manager.active_workflows = manager.active_workflows, {}
    response = client.get(path)
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["workflows"] == [
        w.to_status_dict() for w in (manager.active_workflows or manager.completed_workflows).values()
    ]
    AutomationWorkflowListResponse.model_validate(payload)


@pytest.mark.parametrize(
    "method,path,payload,code",
    [
        ("get", "/workflow_status/missing", None, 404),
        ("post", "/start_workflow/missing", None, 404),
        ("post", "/control_workflow", {"workflow_id": "missing", "action": "pause"}, 404),
    ],
)
def test_error_bodies_match_the_error_model(client, method, path, payload, code):
    response = getattr(client, method)(path, **({"json": payload} if payload else {}))
    assert response.status_code == code
    WorkflowErrorResponse.model_validate(response.json())


def test_a_refused_start_is_a_404_error_body(client, manager):
    manager.accept = False
    response = client.post("/start_workflow/wf-1")
    assert response.status_code == 404
    WorkflowErrorResponse.model_validate(response.json())


def test_the_openapi_contract_documents_the_models(client):
    paths = client.app.openapi()["paths"]
    ok = paths["/workflow_status/{workflow_id}"]["get"]["responses"]
    assert ok["200"]["content"]["application/json"]["schema"]["$ref"].endswith("AutomationWorkflowStatusResponse")
    assert "404" in ok and "500" in ok
