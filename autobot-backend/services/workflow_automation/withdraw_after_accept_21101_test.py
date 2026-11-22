# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A pending step approval is withdrawn only after its decision is accepted (#21101).

Reuses the harness of the step approval gate test (#20917): real manager, controller and executor,
with a gate that records what is withdrawn.
"""

import asyncio

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from auth_middleware import get_current_user

from . import routes
from .models import WorkflowStepStatus
from .step_approval_gate_20917_test import ALICE, _make, _Recorder


@pytest.fixture
def parked(monkeypatch):
    harness = _make(monkeypatch, ALICE["user_id"])
    harness.recorder = _Recorder()
    harness.manager.executor.step_approvals = harness.recorder
    harness.park()
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: ALICE
    harness.client = TestClient(app, raise_server_exceptions=False)
    return harness


def _post(harness, action, step_id="s1"):
    body = {"workflow_id": "wf-1", "action": action, "step_id": step_id}
    return harness.client.post("/control_workflow", json=body)


@pytest.mark.parametrize("action", ["approve_step", "skip_step"])
def test_a_decision_for_the_wrong_step_is_refused_and_leaves_the_approval_pending(parked, action):
    assert _post(parked, action, step_id="s2").status_code == 409
    assert parked.recorder.withdrawn == []
    assert parked.statuses[0] == WorkflowStepStatus.WAITING_APPROVAL


@pytest.mark.parametrize("action", ["approve_step", "skip_step"])
def test_a_decision_for_an_unknown_step_is_refused_and_leaves_the_approval_pending(parked, action):
    assert _post(parked, action, step_id="nope").status_code == 409
    assert parked.recorder.withdrawn == []


@pytest.mark.parametrize("action", ["approve_step", "skip_step"])
def test_a_decision_for_a_step_not_awaiting_is_refused_and_leaves_the_approval_pending(parked, action):
    parked.workflow.steps[0].status = WorkflowStepStatus.EXECUTING
    assert _post(parked, action).status_code == 409
    assert parked.recorder.withdrawn == []


@pytest.mark.parametrize("action", ["approve_step", "skip_step"])
def test_an_accepted_decision_withdraws_the_approval_once(parked, action):
    assert _post(parked, action).json()["success"] is True
    assert parked.recorder.withdrawn == [("wf-1", "s1")]


@pytest.mark.parametrize("action", ["approve_step", "skip_step"])
def test_a_second_decision_on_the_same_step_is_refused_and_withdraws_once(parked, action):
    assert _post(parked, action).status_code == 200
    assert _post(parked, action).status_code == 409
    assert parked.recorder.withdrawn == [("wf-1", "s1")]


@pytest.mark.parametrize("handler,name", [("_approve_step", "approve_and_execute_step"), ("_skip_step", "skip_step")])
def test_a_failure_after_acceptance_still_withdraws_the_approval(parked, handler, name):
    async def _boom(workflow, step_id, _workflows):
        workflow.steps[0].status = WorkflowStepStatus.SKIPPED  # the decision was accepted before the failure
        raise RuntimeError("apply failed")

    setattr(parked.manager.executor, name, _boom)
    controller = parked.manager.controller
    with pytest.raises(RuntimeError):
        asyncio.run(getattr(controller, handler)(parked.workflow, "s1", parked.manager.active_workflows))
    assert parked.recorder.withdrawn == [("wf-1", "s1")]


@pytest.mark.parametrize("handler,name", [("_approve_step", "approve_and_execute_step"), ("_skip_step", "skip_step")])
def test_a_failure_before_acceptance_keeps_the_approval_pending(parked, handler, name):
    async def _boom(*_args):
        raise RuntimeError("apply failed")

    setattr(parked.manager.executor, name, _boom)
    controller = parked.manager.controller
    with pytest.raises(RuntimeError):
        asyncio.run(getattr(controller, handler)(parked.workflow, "s1", parked.manager.active_workflows))
    assert parked.recorder.withdrawn == []


class _Metrics:
    def __init__(self):
        self.decisions = []

    def record_workflow_approval(self, workflow_type, decision):
        self.decisions.append(decision)


@pytest.mark.parametrize("handler", ["_approve_step", "_skip_step"])
def test_concurrent_decisions_on_one_step_accept_one_and_refuse_one(parked, handler):
    controller = parked.manager.controller
    controller.prometheus_metrics = _Metrics()
    decide = getattr(controller, handler)

    async def _race():
        args = (parked.workflow, "s1", parked.manager.active_workflows)
        return await asyncio.gather(decide(*args), decide(*args), return_exceptions=True)

    results = asyncio.run(_race())
    assert sorted(type(r).__name__ for r in results) == ["StepNotAwaitingApproval", "bool"]
    assert parked.recorder.withdrawn == [("wf-1", "s1")]
    assert controller.prometheus_metrics.decisions == [{"_approve_step": "approved", "_skip_step": "skipped"}[handler]]


def _failing_withdraw(parked):
    async def _withdraw(*_args):
        raise OSError("withdraw failed")

    parked.recorder.withdraw = _withdraw


def test_a_failing_withdraw_does_not_replace_the_apply_failure_and_still_records_the_metric(parked):
    async def _boom(workflow, _step_id, _workflows):
        workflow.steps[0].status = WorkflowStepStatus.SKIPPED
        raise RuntimeError("apply failed")

    parked.manager.executor.skip_step = _boom
    controller = parked.manager.controller
    controller.prometheus_metrics = _Metrics()
    _failing_withdraw(parked)
    with pytest.raises(RuntimeError, match="apply failed"):
        asyncio.run(controller._skip_step(parked.workflow, "s1", parked.manager.active_workflows))
    assert controller.prometheus_metrics.decisions == ["skipped"]


def test_a_failing_withdraw_after_a_successful_apply_surfaces_and_still_records_the_metric(parked):
    controller = parked.manager.controller
    controller.prometheus_metrics = _Metrics()
    _failing_withdraw(parked)
    with pytest.raises(OSError, match="withdraw failed"):
        asyncio.run(controller._skip_step(parked.workflow, "s1", parked.manager.active_workflows))
    assert controller.prometheus_metrics.decisions == ["skipped"]
