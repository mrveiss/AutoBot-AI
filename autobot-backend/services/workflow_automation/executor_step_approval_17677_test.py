# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A step the executor parks for approval is released by the control route (#17677).

The approval card in the Workflow Builder answers through ``POST /control_workflow``;
until now nothing ran that answer against the executor (``workflow_ownership_17014_test``
stands the manager in). These tests use the real manager, controller and executor, and
stub only the edges: the messenger (what would go to the browser) and the command runner
(``_execute_command`` is a simulation today). A step waits until it is approved or
skipped; there is no step timeout (owner decision, #17677).
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from auth_middleware import get_current_user

from . import executor as executor_module
from . import routes
from .manager import WorkflowAutomationManager
from .models import ActiveWorkflow, AutomationMode, WorkflowStep, WorkflowStepStatus

BOUND_SECONDS = 20
ALICE = {"username": "alice", "user_id": "u-alice", "role": "user"}


class _FakeMessenger:
    """Records what would reach the browser; sends nothing."""

    terminal_sessions: dict = {}

    def __init__(self):
        self.sent = []

    async def send_message(self, session_id, message):
        self.sent.append((session_id, message))
        return True


class _Harness:
    def __init__(self, manager, messenger, ran, workflow):
        self.manager = manager
        self.messenger = messenger
        self.ran = ran
        self.workflow = workflow

    def park_current_step(self):
        asyncio.run(
            asyncio.wait_for(
                self.manager.executor.process_next_step(self.workflow, self.manager.active_workflows),
                BOUND_SECONDS,
            )
        )

    def control(self, client, action, step_id):
        body = {"workflow_id": self.workflow.workflow_id, "action": action, "step_id": step_id}
        return client.post("/control_workflow", json=body)

    @property
    def statuses(self):
        return [s.status for s in self.workflow.steps]


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(executor_module, "TimingConstants", SimpleNamespace(SERVICE_STARTUP_DELAY=0, STANDARD_DELAY=0))
    manager = WorkflowAutomationManager()
    messenger = _FakeMessenger()
    manager.messenger = manager.executor.messenger = manager.controller.messenger = messenger
    manager.executor.step_evaluator.judges_enabled = False

    ran: list[str] = []

    async def _stub_command(workflow, command, value_redactor):
        ran.append(command)
        return {"command": command, "exit_code": 0, "stdout": "ok", "stderr": "", "execution_time": 0.0}

    monkeypatch.setattr(manager.executor, "_execute_command", _stub_command)

    workflow = ActiveWorkflow(
        workflow_id="wf-1",
        name="n",
        description="d",
        session_id="s-1",
        steps=[
            WorkflowStep(step_id="s1", command="systemctl restart nginx", description="Restart nginx"),
            WorkflowStep(step_id="s2", command="echo second", description="Second"),
        ],
        automation_mode=AutomationMode.SEMI_AUTOMATIC,
        owner_id="u-alice",
    )
    manager.active_workflows[workflow.workflow_id] = workflow
    monkeypatch.setattr(routes, "get_workflow_manager", lambda: manager)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: ALICE
    client = TestClient(app, raise_server_exceptions=False)
    return _Harness(manager, messenger, ran, workflow), client


def test_step_parks_waiting_sends_the_event_and_does_not_run(harness):
    h, _ = harness
    h.park_current_step()
    assert h.statuses[0] == WorkflowStepStatus.WAITING_APPROVAL
    sent = [m for _, m in h.messenger.sent if m["type"] == "step_confirmation_required"]
    assert [(m["workflow_id"], m["step_id"]) for m in sent] == [("wf-1", "s1")]
    assert h.ran == []


def test_approve_step_through_the_control_route_runs_it_and_parks_the_next(harness):
    h, client = harness
    h.park_current_step()
    response = h.control(client, "approve_step", "s1")
    assert response.status_code == 200 and response.json()["success"] is True
    assert h.ran == ["systemctl restart nginx"]
    assert h.statuses == [WorkflowStepStatus.COMPLETED, WorkflowStepStatus.WAITING_APPROVAL]
    assert h.workflow.steps[0].execution_result["stdout"] == "ok"


def test_skip_step_through_the_control_route_skips_without_running(harness):
    h, client = harness
    h.park_current_step()
    response = h.control(client, "skip_step", "s1")
    assert response.status_code == 200 and response.json()["success"] is True
    assert h.ran == []
    assert h.statuses == [WorkflowStepStatus.SKIPPED, WorkflowStepStatus.WAITING_APPROVAL]


def test_second_approve_while_executing_does_not_run_the_step_again(harness):
    """A repeated approve of a step that is no longer parked is refused with 409 and runs nothing."""
    h, client = harness
    h.park_current_step()
    h.workflow.steps[0].status = WorkflowStepStatus.EXECUTING  # the first approve is mid-run
    response = h.control(client, "approve_step", "s1")
    assert response.status_code == 409
    assert h.ran == []
    assert h.statuses[0] == WorkflowStepStatus.EXECUTING


@pytest.mark.parametrize("action", ["approve_step", "skip_step"])
def test_decision_for_a_step_still_executing_is_refused_and_changes_nothing(harness, action):
    """#20918: approve and skip both need the step parked in WAITING_APPROVAL, not just named."""
    h, client = harness
    h.park_current_step()
    h.workflow.steps[0].status = WorkflowStepStatus.EXECUTING
    response = h.control(client, action, "s1")
    assert response.status_code == 409
    assert h.ran == []
    assert h.statuses == [WorkflowStepStatus.EXECUTING, WorkflowStepStatus.PENDING]
    assert h.workflow.current_step_index == 0


@pytest.mark.parametrize("action", ["approve_step", "skip_step"])
def test_decision_for_the_wrong_step_is_refused_and_changes_nothing(harness, action):
    """#20918: a step id that is not the waiting step is a 409, never `success: true`."""
    h, client = harness
    h.park_current_step()
    response = h.control(client, action, "s2")
    assert response.status_code == 409
    assert h.ran == []
    assert h.statuses == [WorkflowStepStatus.WAITING_APPROVAL, WorkflowStepStatus.PENDING]
    assert h.workflow.current_step_index == 0


@pytest.mark.parametrize("action", ["approve_step", "skip_step"])
def test_decision_for_an_unknown_step_is_refused(harness, action):
    h, client = harness
    h.park_current_step()
    assert h.control(client, action, "nope").status_code == 409
    assert h.ran == []
    assert h.statuses[0] == WorkflowStepStatus.WAITING_APPROVAL


@pytest.mark.parametrize("action", ["approve_step", "skip_step"])
def test_refused_wrong_step_decision_is_not_counted_as_approved_or_skipped(harness, action):
    """#20918: the approval metric moves only for a decision the executor accepted."""
    h, client = harness
    recorded = []
    h.manager.controller.prometheus_metrics = SimpleNamespace(
        record_workflow_approval=lambda **kw: recorded.append(kw["decision"])
    )
    h.park_current_step()
    assert h.control(client, action, "s2").status_code == 409
    assert recorded == []
    assert h.control(client, action, "s1").status_code == 200
    assert recorded == [{"approve_step": "approved", "skip_step": "skipped"}[action]]
