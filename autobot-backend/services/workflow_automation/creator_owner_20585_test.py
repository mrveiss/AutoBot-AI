# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every workflow creator records its verified caller, so a command step has someone to run as (#20585).

Each creator is driven with a stand-in manager that captures the ``owner_id`` it is
given. That recorded owner is then handed to ``run_command_step`` the way the
executor does: an administrator's step runs, any other role's is refused, and a
workflow recorded with no owner is refused as "no creator".
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks

from services.advanced_workflow.coordinator import WorkflowCoordinator
from services.advanced_workflow.models import SmartWorkflowStep
from services.workflow_serializer import SCHEMA_VERSION, WorkflowSerializer

from . import command_step
from .command_step import CommandStepFailed, run_command_step

_ADMIN = {"user_id": "admin-1", "role": "admin"}
_PLAIN = {"user_id": "user-1", "role": "user"}
_ROLES = {"admin-1": "admin", "user-1": "user"}


class _Manager:
    """Captures what a creator passes to the automation manager."""

    def __init__(self) -> None:
        self.created: list[dict] = []

    async def create_automated_workflow(self, **kwargs):
        self.created.append(kwargs)
        return "wf-1"

    async def create_workflow_from_chat_request(self, *args, **kwargs):
        self.created.append(kwargs)
        return "wf-1"

    async def start_workflow_execution(self, workflow_id):
        return True

    @property
    def owner(self):
        return self.created[-1].get("owner_id")


@pytest.fixture
def runner(monkeypatch):
    """``run_command_step`` with the account store and the security layer stood in for."""

    async def _role(owner_id):
        return _ROLES.get(owner_id)

    layer = MagicMock()
    layer.execute_command = AsyncMock(return_value={"return_code": 0, "stdout": "ok", "stderr": ""})
    monkeypatch.setattr(command_step, "current_role", _role)
    monkeypatch.setattr(command_step, "get_security_layer", lambda: layer)

    async def _run(owner):
        return await run_command_step("echo hi", user=owner, value_redactor=str)

    return _run


async def _chat_creator(monkeypatch, user) -> _Manager:
    from api import workflow as module
    from services.workflow_automation import routes

    manager = _Manager()
    monkeypatch.setattr(routes, "get_workflow_manager", lambda: manager)
    monkeypatch.setattr(module, "_validate_orchestrator", lambda request: None)
    monkeypatch.setattr(module, "_try_simple_response", lambda message: None)
    request = module.WorkflowExecutionRequest(user_message="list files")
    await module.execute_workflow(request, BackgroundTasks(), MagicMock(), admin_check=True, current_user=user)
    return manager


async def _template_creator(monkeypatch, user) -> _Manager:
    from api import templates as module
    from services.workflow_automation import routes

    manager = _Manager()
    step = {"step_id": "s1", "action": "echo hi", "description": "d", "agent_type": "a"}
    data = {"template_name": "t", "category": "c", "steps": [step]}
    monkeypatch.setattr(routes, "get_workflow_manager", lambda: manager)
    monkeypatch.setattr(
        module.workflow_template_manager,
        "create_workflow_from_template",
        lambda *a: data,
    )
    request = module.TemplateExecutionRequest(template_id="tpl", variables={})
    await module.execute_template_workflow("tpl", request, current_user=user)
    return manager


async def _coordinator_creator(owner_id) -> _Manager:
    manager = _Manager()
    coordinator = object.__new__(WorkflowCoordinator)
    coordinator.base_manager = manager
    coordinator.risk_analyzer = MagicMock()
    coordinator.risk_analyzer.assess_step_risk_level.return_value = "low"
    step = SmartWorkflowStep(step_id="s1", command="echo hi", description="d")
    await coordinator._create_workflow("wf-1", "do it", [step], "sess", MagicMock(), owner_id)
    return manager


async def _serializer_creator(owner_id) -> _Manager:
    manager = _Manager()
    step = {
        "step_id": "s1",
        "command": "echo hi",
        "description": "d",
        "risk_level": "low",
    }
    doc = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": "2026-01-01T00:00:00Z",
        "workflow_id": "wf-0",
        "name": "w",
        "description": "d",
        "automation_mode": "semi_automatic",
        "steps": [step],
        "metadata": {},
    }
    await WorkflowSerializer(manager).import_workflow(doc, owner_id=owner_id)
    return manager


@pytest.mark.asyncio
async def test_execute_workflow_runs_as_its_verified_caller(monkeypatch, runner):
    assert (await runner((await _chat_creator(monkeypatch, _ADMIN)).owner))["exit_code"] == 0
    with pytest.raises(CommandStepFailed, match="administrator"):
        await runner((await _chat_creator(monkeypatch, _PLAIN)).owner)


@pytest.mark.asyncio
async def test_template_execution_runs_as_its_verified_caller(monkeypatch, runner):
    assert (await runner((await _template_creator(monkeypatch, _ADMIN)).owner))["exit_code"] == 0
    with pytest.raises(CommandStepFailed, match="administrator"):
        await runner((await _template_creator(monkeypatch, _PLAIN)).owner)


@pytest.mark.asyncio
async def test_coordinator_workflow_runs_as_its_verified_caller(runner):
    assert (await runner((await _coordinator_creator("admin-1")).owner))["exit_code"] == 0
    with pytest.raises(CommandStepFailed, match="administrator"):
        await runner((await _coordinator_creator("user-1")).owner)


@pytest.mark.asyncio
async def test_imported_workflow_runs_as_its_verified_caller(runner):
    assert (await runner((await _serializer_creator("admin-1")).owner))["exit_code"] == 0
    with pytest.raises(CommandStepFailed, match="administrator"):
        await runner((await _serializer_creator("user-1")).owner)


@pytest.mark.asyncio
async def test_a_workflow_with_no_recorded_owner_is_still_refused(runner):
    with pytest.raises(CommandStepFailed, match="no creator"):
        await runner((await _serializer_creator(None)).owner)
