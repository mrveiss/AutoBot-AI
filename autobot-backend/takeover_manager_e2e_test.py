#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Session takeover: workflow automation, manual intervention and terminal messaging.

#14979: this file used to be a hand-run driver. ``SessionTakeoverTestSuite``
defined ``__init__``, so pytest refused the class outright and all ten
``test_*`` methods were dead text -- the file was named ``*_test.py``, sat in a
collected tree and imported cleanly, so every signal a reader had said the
tests ran.

Nothing here needs a running service. The suite drives
``WorkflowAutomationManager`` in-process, talks to ``TerminalWebSocket``
through an ``AsyncMock`` socket and persists workflow state to an in-process
``fakeredis`` (see ``setup_method``), so it is an ordinary unit suite that was
merely uncollectable. Three things had to change beyond the class shape:

* The ``try: ... except ImportError: COMPONENTS_AVAILABLE = False`` wrapper is
  gone. Every method opened with ``if not COMPONENTS_AVAILABLE: return``, so a
  broken import turned the whole suite into ten silent passes. The imports are
  now plain: an import failure is a collection error with a traceback.
* ``test_chat_integration`` called the real ``Orchestrator``, whose planner is
  a live dependency, and then asserted only ``if workflow_id:`` -- so a planner
  returning ``None`` for every request passed. The orchestrator is now an
  ``AsyncMock`` and the assertions are unconditional.
* ``test_command_risk_assessment`` asserted a Python re-implementation of the
  frontend's ``assessCommandRisk``, defined inside the test body. A test that
  asserts its own copy of the logic cannot fail on a product change. It now
  asserts ``SecureCommandExecutor.assess_command_risk`` -- the classifier that
  actually gates terminal execution.
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis as fakeredis_async

from api.terminal_handlers import TerminalWebSocket
from api.workflow_automation import (
    AutomationMode,
    WorkflowAutomationManager,
    WorkflowControlRequest,
    WorkflowStep,
)
from secure_command_executor import CommandRisk, SecureCommandExecutor


class TestSessionTakeover:
    """Session takeover and workflow automation behaviour, driven in-process."""

    def setup_method(self) -> None:
        self.test_session_id = f"test_session_{int(time.time())}"
        self.workflow_manager = WorkflowAutomationManager()
        # Starting a workflow drives the state machine, which persists every
        # phase to Redis through `AsyncRedisClientMixin._get_redis`. The backend
        # conftest replaces `autobot_shared.redis_client` with a socket-free
        # stand-in returning None (#14932), so the three tests that start a
        # workflow would die on `NoneType.set` before reaching an assertion.
        # Seeding the mixin's cached client with the in-process fake -- as
        # `services/temporal_invalidation_test.py` and
        # `llm_shared/tests/test_provider_degradation.py` do -- runs the real
        # persistence path instead of skipping it.
        self.workflow_manager.executor.state_machine._redis = fakeredis_async.FakeRedis(
            server=fakeredis_async.FakeServer(), decode_responses=True
        )

    async def test_workflow_creation(self):
        """A created workflow is registered active with its steps and mode intact."""
        steps = [
            WorkflowStep(
                step_id="step_1",
                command="echo 'Starting system update'",
                description="Initialize system update",
                explanation="This command starts the system update process",
                requires_confirmation=True,
            ),
            WorkflowStep(
                step_id="step_2",
                command="sudo apt update",
                description="Update package repositories",
                explanation="Updates the list of available packages",
                requires_confirmation=True,
            ),
            WorkflowStep(
                step_id="step_3",
                command="apt list --upgradable",
                description="Check upgradable packages",
                explanation="Shows which packages can be upgraded",
                requires_confirmation=False,
            ),
        ]

        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Test System Update Workflow",
            description="Complete system update with user confirmation",
            steps=steps,
            session_id=self.test_session_id,
            automation_mode=AutomationMode.SEMI_AUTOMATIC,
        )

        assert workflow_id is not None, "Workflow creation failed"
        assert workflow_id in self.workflow_manager.active_workflows, "Workflow not found in active list"

        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert workflow.name == "Test System Update Workflow", "Workflow name mismatch"
        assert len(workflow.steps) == 3, "Incorrect number of steps"
        assert workflow.automation_mode == AutomationMode.SEMI_AUTOMATIC, "Automation mode mismatch"

    async def test_step_confirmation_flow(self):
        """Execution halts on the first step that requires confirmation."""
        steps = [
            WorkflowStep(
                "confirm_1",
                "echo 'Step 1 executed'",
                "Execute step 1",
                requires_confirmation=True,
            ),
            WorkflowStep(
                "confirm_2",
                "echo 'Step 2 executed'",
                "Execute step 2",
                requires_confirmation=True,
            ),
        ]

        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Confirmation Test Workflow",
            description="Test step-by-step confirmation",
            steps=steps,
            session_id=self.test_session_id,
        )

        await self.workflow_manager.start_workflow_execution(workflow_id)

        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert workflow.current_step_index == 0, "Workflow should be waiting at first step"
        assert workflow.steps[0].status.value == "waiting_approval", "First step should be waiting for approval"

        approved = await self.workflow_manager.handle_workflow_control(
            WorkflowControlRequest(workflow_id=workflow_id, action="approve_step", step_id="confirm_1")
        )
        assert approved is True, "Approving the waiting step should be accepted"

    async def test_manual_takeover(self):
        """Pausing mid-workflow records an intervention, and resuming clears it."""
        steps = [
            WorkflowStep("takeover_1", "echo 'Before takeover'", "Pre-takeover step"),
            WorkflowStep("takeover_2", "echo 'After takeover'", "Post-takeover step"),
            WorkflowStep("takeover_3", "echo 'Final step'", "Final step"),
        ]

        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Manual Takeover Test",
            description="Test manual intervention",
            steps=steps,
            session_id=self.test_session_id,
        )
        await self.workflow_manager.start_workflow_execution(workflow_id)

        await self.workflow_manager.handle_workflow_control(
            WorkflowControlRequest(workflow_id=workflow_id, action="pause")
        )

        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert workflow.is_paused is True, "Workflow should be paused"
        assert len(workflow.user_interventions) > 0, "User intervention should be recorded"
        assert workflow.user_interventions[-1]["action"] == "pause", "Pause action should be recorded"

        await self.workflow_manager.handle_workflow_control(
            WorkflowControlRequest(workflow_id=workflow_id, action="resume")
        )

        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert workflow.is_paused is False, "Workflow should be resumed"

    async def test_emergency_kill(self):
        """An emergency-kill control message is answered on the terminal socket."""
        mock_websocket = AsyncMock()
        terminal_session = TerminalWebSocket(
            websocket=mock_websocket,
            session_id=self.test_session_id,
        )
        terminal_session.active = True

        await terminal_session.handle_message(
            {
                "type": "workflow_control",
                "action": "emergency_kill",
                "session_id": self.test_session_id,
            }
        )

        terminal_session.websocket.send_text.assert_called()

    async def test_pause_resume_workflow(self):
        """Both control actions succeed and both are recorded as interventions."""
        steps = [
            WorkflowStep("pause_1", "echo 'Before pause'", "Pre-pause step"),
            WorkflowStep("pause_2", "echo 'Pausable step'", "Pausable step"),
            WorkflowStep("pause_3", "echo 'After pause'", "Post-pause step"),
        ]

        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Pause/Resume Test",
            description="Test pause and resume functionality",
            steps=steps,
            session_id=self.test_session_id,
        )
        await self.workflow_manager.start_workflow_execution(workflow_id)

        paused = await self.workflow_manager.handle_workflow_control(
            WorkflowControlRequest(workflow_id=workflow_id, action="pause")
        )
        assert paused is True, "Pause should succeed"

        resumed = await self.workflow_manager.handle_workflow_control(
            WorkflowControlRequest(workflow_id=workflow_id, action="resume")
        )
        assert resumed is True, "Resume should succeed"

        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert len(workflow.user_interventions) == 2, "Should have 2 interventions (pause + resume)"

    async def test_chat_integration(self):
        """A planned request becomes a workflow: commands and dependencies mapped.

        The orchestrator is mocked. Calling the real one makes this test depend
        on a live planner, and its manager-side handler turns any planner error
        into ``return None`` -- which is why the original version, asserting
        only ``if workflow_id:``, passed whether or not planning worked at all.
        """
        planned = [
            SimpleNamespace(
                task_id="plan_a",
                action="Update package repositories",
                requires_approval=True,
                dependencies=[],
            ),
            SimpleNamespace(
                task_id="plan_b",
                action="Run the verification probe",
                requires_approval=False,
                dependencies=["plan_a"],
                inputs={"command": "systemctl status autobot"},
            ),
        ]
        self.workflow_manager.orchestrator = AsyncMock()
        self.workflow_manager.orchestrator.classify_request_complexity_verdict.return_value = SimpleNamespace(
            complexity="COMPLEX",
            classified=True,
            state=SimpleNamespace(value="classified"),
        )
        self.workflow_manager.orchestrator.plan_workflow_steps.return_value = planned

        workflow_id = await self.workflow_manager.create_workflow_from_chat_request(
            "Update my system and install security patches", self.test_session_id
        )

        assert workflow_id is not None, "A planned request must produce a workflow"
        workflow = self.workflow_manager.active_workflows[workflow_id]
        assert len(workflow.steps) == 2, "Every planned task must become a step"

        first, second = workflow.steps
        # No `inputs` on the first task, so the manager derives the command from
        # the action text; the second carries an explicit command and keeps it.
        assert first.command == "sudo apt update", "Package-update action should map to the update command"
        assert second.command == "systemctl status autobot", "An explicit planned command must survive"
        assert first.requires_confirmation is True, "Approval requirement must carry across"
        assert second.requires_confirmation is False, "Approval requirement must carry across"
        assert first.dependencies == [], "The first step depends on nothing"
        assert second.dependencies == ["step_1"], "Planner task ids must be remapped to step ids"

    async def test_command_risk_assessment(self):
        """The executor's classifier gates the commands a takeover step may run."""
        executor = SecureCommandExecutor()
        expected = {
            "ls -la": CommandRisk.SAFE,
            "echo 'safe command'": CommandRisk.SAFE,
            "chmod 777 /": CommandRisk.MODERATE,
            "sudo apt update": CommandRisk.HIGH,
            "apt list --upgradable": CommandRisk.HIGH,
            "rm -rf /tmp/test": CommandRisk.FORBIDDEN,
            "sudo rm -rf /": CommandRisk.FORBIDDEN,
            "dd if=/dev/zero of=/dev/sda": CommandRisk.FORBIDDEN,
            "mkfs.ext4 /dev/sdb1": CommandRisk.FORBIDDEN,
            "killall -9 python": CommandRisk.FORBIDDEN,
        }

        for command, expected_risk in expected.items():
            risk, reasons = executor.assess_command_risk(command)
            assert risk == expected_risk, f"{command!r}: expected {expected_risk}, got {risk}"
            assert reasons, f"{command!r}: a classification must say why"

    async def test_websocket_communication(self):
        """Every workflow-control and ping message gets a reply on the socket."""
        mock_websocket = AsyncMock()
        terminal_session = TerminalWebSocket(
            websocket=mock_websocket,
            session_id=self.test_session_id,
        )
        terminal_session.active = True

        messages = [
            {
                "type": "workflow_control",
                "action": "pause",
                "session_id": self.test_session_id,
            },
            {
                "type": "workflow_control",
                "action": "resume",
                "session_id": self.test_session_id,
            },
            {"type": "ping"},
        ]

        for message in messages:
            await terminal_session.handle_message(message)

        assert terminal_session.websocket.send_text.call_count >= len(messages), "WebSocket messages should be sent"

    async def test_workflow_dependencies(self):
        """Declared step dependencies survive workflow creation unchanged."""
        steps = [
            WorkflowStep("dep_1", "echo 'Base step'", "Base step", dependencies=[]),
            WorkflowStep("dep_2", "echo 'Depends on 1'", "Dependent step", dependencies=["dep_1"]),
            WorkflowStep("dep_3", "echo 'Depends on 2'", "Final step", dependencies=["dep_2"]),
        ]

        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Dependency Test",
            description="Test step dependencies",
            steps=steps,
            session_id=self.test_session_id,
        )

        step1, step2, step3 = self.workflow_manager.active_workflows[workflow_id].steps
        assert len(step1.dependencies or []) == 0, "Step 1 should have no dependencies"
        assert "dep_1" in (step2.dependencies or []), "Step 2 should depend on step 1"
        assert "dep_2" in (step3.dependencies or []), "Step 3 should depend on step 2"

    async def test_error_handling(self):
        """Controlling an unknown workflow is refused, and a junk message is survived.

        The original wrapped both halves in ``try/except Exception`` and logged
        the exception as a success, so the method could not fail. Both calls are
        now made directly: an exception from either is a real failure.
        """
        refused = await self.workflow_manager.handle_workflow_control(
            WorkflowControlRequest(workflow_id="non_existent_workflow", action="pause")
        )
        assert refused is False, "Invalid workflow control should return False"

        mock_websocket = AsyncMock()
        terminal_session = TerminalWebSocket(
            websocket=mock_websocket,
            session_id=self.test_session_id,
        )

        await terminal_session.handle_message({"type": "invalid_type", "data": "malformed"})

        assert (
            self.workflow_manager.get_workflow_status("non_existent_workflow") is None
        ), "An unknown workflow has no status"

    async def test_status_reports_every_step_of_a_multi_step_workflow(self):
        """The status dict a client renders lists each step with its own id.

        Replaces the ``run_demo_workflow()`` driver this file used to carry,
        which built the same five-step workflow and asserted nothing about it.
        """
        demo_steps = [
            WorkflowStep(
                step_id=f"demo_{index}",
                command=command,
                description=description,
                requires_confirmation=confirm,
            )
            for index, (command, description, confirm) in enumerate(
                [
                    ("echo 'Starting development environment setup'", "Initialize setup process", False),
                    ("sudo apt update", "Update package repositories", True),
                    ("sudo apt install -y git curl wget", "Install essential development tools", True),
                    ("git --version", "Verify tool installations", False),
                    ("echo 'Development environment setup complete'", "Complete setup process", False),
                ],
                start=1,
            )
        ]

        workflow_id = await self.workflow_manager.create_automated_workflow(
            name="Development Environment Setup Demo",
            description="Complete development environment setup with user confirmation points",
            steps=demo_steps,
            session_id=self.test_session_id,
            automation_mode=AutomationMode.SEMI_AUTOMATIC,
        )

        status = self.workflow_manager.get_workflow_status(workflow_id)
        assert status is not None, "A created workflow must report a status"
        assert [step["step_id"] for step in status["steps"]] == [
            f"demo_{index}" for index in range(1, 6)
        ], "Status must list every step, in order"
        assert [step["requires_confirmation"] for step in status["steps"]] == [
            False,
            True,
            True,
            False,
            False,
        ], "Status must carry each step's confirmation requirement"
