# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A parked workflow step is filed in the approvals inbox and released by its decision (#20917).

The real manager, controller, executor and step gate run; only the edges are stood in for: the
messenger, the command runner, the database session and the approval service (which records what
would be written). The ownership query on the real service is in
``tests/migrations/test_workflow_step_approval_20917.py``.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from auth_middleware import get_current_user
from services import approval_execution
from testkit.fake_async_session import FakeAsyncSession, FakeResult

from . import executor as executor_module
from . import routes
from . import step_approval_gate as gate
from .manager import WorkflowAutomationManager
from .models import ActiveWorkflow, AutomationMode, WorkflowStep, WorkflowStepStatus

ALICE_ID = str(uuid.uuid4())
ALICE = {"username": "alice", "user_id": ALICE_ID, "role": "user"}


class _Messenger:
    terminal_sessions: dict = {}

    def __init__(self):
        self.sent = []

    async def send_message(self, session_id, message):
        self.sent.append(message)
        return True


class _Service:
    """Stands in for ApprovalGateService: records create_approval, can be told to fail."""

    created: list = []
    fail = False

    def __init__(self, _db):
        pass

    async def create_approval(self, **kwargs):
        if _Service.fail:
            raise RuntimeError("database is down")
        _Service.created.append(kwargs)


class _Recorder:
    """A step gate that records instead of filing."""

    def __init__(self):
        self.withdrawn = []

    async def file(self, workflow, step):
        pass

    async def withdraw(self, workflow_id, step_id=None):
        self.withdrawn.append((workflow_id, step_id))


class _Harness:
    def __init__(self, manager, messenger, ran, workflow):
        self.manager, self.messenger, self.ran, self.workflow = manager, messenger, ran, workflow

    def park(self):
        asyncio.run(
            asyncio.wait_for(self.manager.executor.process_next_step(self.workflow, self.manager.active_workflows), 20)
        )

    def decide(self, status, step_id="s1"):
        approval = SimpleNamespace(
            id=uuid.uuid4(), status=status, resume_ref=gate.resume_ref_for(self.workflow.workflow_id, step_id)
        )
        asyncio.run(asyncio.wait_for(gate.resume_workflow_step(approval, None), 20))

    @property
    def statuses(self):
        return [s.status for s in self.workflow.steps]


def _make(monkeypatch, owner_id):
    monkeypatch.setattr(executor_module, "TimingConstants", SimpleNamespace(SERVICE_STARTUP_DELAY=0, STANDARD_DELAY=0))

    @asynccontextmanager
    async def _session():
        yield FakeAsyncSession(default_result=FakeResult(["alice"]))

    monkeypatch.setattr(gate, "get_async_session_factory", lambda: lambda: _session())
    monkeypatch.setattr(gate, "ApprovalGateService", _Service)
    _Service.created, _Service.fail = [], False
    manager = WorkflowAutomationManager()
    messenger = _Messenger()
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
            WorkflowStep(
                step_id="s1", command="systemctl restart nginx", description="Restart nginx", risk_level="high"
            ),
            WorkflowStep(step_id="s2", command="echo second", description="Second"),
        ],
        automation_mode=AutomationMode.SEMI_AUTOMATIC,
        owner_id=owner_id,
    )
    manager.active_workflows[workflow.workflow_id] = workflow
    monkeypatch.setattr(routes, "get_workflow_manager", lambda: manager)
    return _Harness(manager, messenger, ran, workflow)


@pytest.fixture
def harness(monkeypatch):
    return _make(monkeypatch, ALICE_ID)


def test_parked_step_is_filed_once_for_the_owner_username(harness):
    harness.park()
    assert len(_Service.created) == 1
    filed = _Service.created[0]
    assert filed["source"] == "workflow_step" and filed["owner_user"] == "alice"
    assert filed["workflow_id"] == "wf-1" and filed["workflow_step"] == "s1"
    assert filed["resume_ref"] == "wf-1:s1" and filed["risk_tier"] == "high"
    assert filed["context"]["command"] == "systemctl restart nginx"
    assert "nginx" not in filed["title"]  # the title rides the global event, which every client receives


def test_step_with_no_owner_files_nothing_and_still_notifies_the_socket(monkeypatch):
    h = _make(monkeypatch, None)
    h.park()
    assert _Service.created == []
    assert [m["step_id"] for m in h.messenger.sent if m["type"] == "step_confirmation_required"] == ["s1"]


def test_a_failing_filer_never_stops_the_step_parking(harness):
    _Service.fail = True
    harness.park()
    assert harness.statuses[0] == WorkflowStepStatus.WAITING_APPROVAL


def test_approving_the_filed_approval_runs_the_step(harness):
    harness.park()
    harness.decide("approved")
    assert harness.ran == ["systemctl restart nginx"]
    assert harness.statuses == [WorkflowStepStatus.COMPLETED, WorkflowStepStatus.WAITING_APPROVAL]


def test_rejecting_the_filed_approval_skips_the_step_and_parks_the_next(harness):
    harness.park()
    harness.decide("rejected")
    assert harness.ran == []
    assert harness.statuses == [WorkflowStepStatus.SKIPPED, WorkflowStepStatus.WAITING_APPROVAL]


def test_a_decision_on_a_step_that_is_not_the_current_one_runs_nothing(harness):
    harness.park()
    harness.decide("approved", step_id="s2")
    assert harness.ran == []
    assert harness.statuses[0] == WorkflowStepStatus.WAITING_APPROVAL


def test_answering_on_the_control_route_withdraws_the_approval_and_a_late_decision_is_a_no_op(harness):
    recorder = _Recorder()
    harness.manager.executor.step_approvals = recorder
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: ALICE
    client = TestClient(app, raise_server_exceptions=False)
    harness.park()
    body = {"workflow_id": "wf-1", "action": "approve_step", "step_id": "s1"}
    assert client.post("/control_workflow", json=body).json()["success"] is True
    assert recorder.withdrawn == [("wf-1", "s1")]
    harness.decide("approved")  # the approval was decided after the route already ran the step
    assert harness.ran == ["systemctl restart nginx"]


def test_cancelling_withdraws_every_pending_step_approval(harness):
    recorder = _Recorder()
    harness.manager.executor.step_approvals = recorder
    harness.park()
    asyncio.run(harness.manager.executor.cancel_workflow(harness.workflow, harness.manager.active_workflows))
    assert recorder.withdrawn == [("wf-1", None)]


def test_importing_the_approvals_api_registers_the_workflow_step_resume():
    import api.approval_gates  # noqa: F401

    assert approval_execution.is_registered_resume_source("workflow_step")
    assert not approval_execution.is_registered_resume_source("no_such_source")  # control
