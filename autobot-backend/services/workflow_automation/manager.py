# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Automation Manager Module

Main coordinator for workflow automation using composition.
"""

import uuid
from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from orchestration.success_criteria import SuccessCriteriaEvaluator
from orchestrator import Orchestrator
from orchestrator import get_orchestrator_sync as get_orchestrator
from services.notification_service import NotificationService
from services.workflow_versioning import WorkflowVersionStore
from type_defs.common import Metadata

from .controller import WorkflowController
from .executor import WorkflowExecutor
from .messaging import WorkflowMessenger
from .models import (
    ActiveWorkflow,
    AutomationMode,
    PlanApprovalMode,
    PlanApprovalRequest,
    WorkflowControlRequest,
    WorkflowStep,
)
from .templates import WorkflowTemplateManager

logger = get_logger(__name__)


def _planned_command(task: object) -> str | None:
    """The task's command when it is one that can actually be run, else None.

    #13809 review: `inputs.get("command")` was filtered on truthiness alone, so
    a list or a dict passed and `WorkflowStep.command` -- declared `str` and not
    validated at runtime -- could carry a non-string into workflow status and
    snapshots. A non-dict `inputs` raised `AttributeError` into the broad
    handler above and became a plain `return None`, which is the #13730 shape
    of an error disappearing. Both are rejected here instead.
    """
    inputs = getattr(task, "inputs", None)
    if not isinstance(inputs, dict):
        return None
    command = inputs.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    return command


class WorkflowAutomationManager:
    """Manages automated workflow execution with user intervention points"""

    def __init__(self) -> None:
        """Initialize manager with workflow state and specialized components."""
        # Core state
        self.active_workflows: Dict[str, ActiveWorkflow] = {}
        # Issue #1367: Completed workflow history (persists until restart)
        self.completed_workflows: Dict[str, ActiveWorkflow] = {}

        # Composition: delegate to specialized components
        self.messenger = WorkflowMessenger()
        # Issue #3101: Wire notification service into executor.
        self._notification_service = NotificationService()
        self.executor = WorkflowExecutor(
            self.messenger,
            notification_service=self._notification_service,
            criteria_evaluator=SuccessCriteriaEvaluator(),
        )
        # Issue #1367: Archive finished workflows to completed history
        self.executor.on_workflow_finished = self.archive_completed_workflow
        self.controller = WorkflowController(self.messenger, self.executor)
        self.template_manager = WorkflowTemplateManager()

        # Orchestrators for chat request processing
        self.orchestrator = Orchestrator()
        self.enhanced_orchestrator = get_orchestrator()

    @property
    def terminal_sessions(self) -> Dict:
        """Expose terminal sessions from messenger for WebSocket management"""
        return self.messenger.terminal_sessions

    async def create_workflow_from_chat_request(
        self, user_request: str, session_id: str, owner_id: str | None = None
    ) -> str | None:
        """Create automated workflow from natural language chat request.

        #17014: ``owner_id`` is the authenticated caller, so the workflow records who
        created it and the control routes can scope to them. Callers with no user
        context leave it None, which makes the workflow admin-only rather than open.

        #13809: planned by ``create_workflow_plan``, the canonical LLM planner, with
        the shell-command contract on. ``plan_workflow_steps`` returned the same
        fixed skeleton for every request, so every chat workflow echoed its own step
        names and did nothing. Owner ruling 2026-10-03, recorded on #13809.
        """
        try:
            context = {"shell_commands": True, "user_id": owner_id or ""}
            plan = await self.orchestrator.create_workflow_plan(user_request, context)
            workflow_steps = self._steps_from_plan(plan.tasks, user_request)
            if not workflow_steps:
                # #13809: a plan with no command to run is the hollow workflow this
                # issue was about; refusing it keeps the failure visible.
                logger.warning("Chat plan for session %s carried no executable command", session_id)
                return None
            return await self.create_automated_workflow(
                name=f"Chat Request: {user_request[:50]}...",
                description=user_request,
                steps=workflow_steps,
                session_id=session_id,
                owner_id=owner_id,
            )
        except Exception as e:
            # #13730: this handler is what made the un-awaited planning calls
            # invisible — a TypeError became a plain `return None`, so both HTTP
            # routes reported "no workflow" instead of an error. Contract keeps
            # returning None, but the cause is now in the log.
            logger.error("Failed to create workflow from chat request: %s", e, exc_info=True)
            return None

    def _steps_from_plan(self, tasks, user_request: str) -> List[WorkflowStep]:
        """Turn planned tasks that carry a command into confirmation-gated steps.

        #13809: the command is LLM-authored from the user's text, so every step
        requires confirmation — a property of the step that executes, which holds
        whatever the route's start/approval defaults are. A task without a command
        is an agent action this terminal executor cannot run; it is named in the
        log and dropped rather than replaced by a placeholder echo.
        """
        runnable = [t for t in tasks if _planned_command(t) is not None]
        step_ids = {task.task_id: f"step_{i + 1}" for i, task in enumerate(runnable)}
        dropped = [t.action for t in tasks if t.task_id not in step_ids]
        if dropped:
            logger.warning("Chat plan tasks without a usable command were dropped: %s", dropped)

        # #13809 review: the planner copies the model's `dependencies` through
        # unchanged, and the model has no task id to reference -- the schema
        # asks for `["task_ids"]` but gives it no id field to assign, so the
        # ids it invents can never match the server-generated ones. Every such
        # reference was filtered out silently, leaving steps that look
        # independent. The filter stays (an unresolvable id cannot be ordered
        # against) but it no longer happens quietly. Root cause is in the
        # shared planning prompt, which other callers use: #17979.
        unresolved = sorted({d for task in runnable for d in (task.dependencies or []) if d not in step_ids})
        if unresolved:
            logger.warning(
                "Chat plan dependencies did not resolve to a step and were dropped: %s. "
                "The steps below are ordered as listed, not as the planner intended (#17979).",
                unresolved,
            )
        return [
            WorkflowStep(
                step_id=step_ids[task.task_id],
                command=self._extract_command_from_step(task),
                description=task.action,
                explanation=f"This step is part of: {user_request}",
                requires_confirmation=True,
                dependencies=[step_ids[d] for d in (task.dependencies or []) if d in step_ids],
            )
            for task in runnable
        ]

    def _extract_command_from_step(self, step) -> str:
        """Extract executable command from workflow step"""
        if hasattr(step, "inputs") and step.inputs:
            command = step.inputs.get("command", "")
            if command:
                return command

        # Fallback: create command from action description
        action = step.action.lower()
        if "update" in action and "package" in action:
            return "sudo apt update"
        elif "install" in action:
            return "sudo apt install -y git curl wget"
        elif "search" in action:
            return "find . -name '*' -type "
        else:
            return f"echo 'Executing: {step.action}'"

    async def create_automated_workflow(
        self,
        name: str,
        description: str,
        steps: List[WorkflowStep],
        session_id: str,
        automation_mode: AutomationMode = AutomationMode.SEMI_AUTOMATIC,
        owner_id: str | None = None,
    ) -> str:
        """Create new automated workflow.

        Issue #2304: owner_id should be passed by callers that have authenticated
        user context (e.g. API endpoints using Depends(get_current_user)).
        Internal callers without user context leave owner_id=None.
        """
        workflow_id = str(uuid.uuid4())

        workflow = ActiveWorkflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            session_id=session_id,
            steps=steps,
            automation_mode=automation_mode,
            owner_id=owner_id,
        )

        if not owner_id:
            # #17014: no owner means no user's secrets resolve for this workflow and only
            # an admin may steer it. Both are deliberate and both are invisible at the
            # point they bite, so they are stated here, once, where the choice is made.
            logger.warning("Workflow %s created with no owner: admin-only, no user secrets", workflow_id)

        self.active_workflows[workflow_id] = workflow

        # Snapshot initial state for rollback/audit (#2145)
        try:
            version_store = WorkflowVersionStore()
            await version_store.save_version(
                workflow_id,
                workflow.to_status_dict() if hasattr(workflow, "to_status_dict") else {"name": name},
                notes="initial version",
            )
        except Exception:
            logger.warning("workflow_versioning: could not snapshot workflow %s", workflow_id)

        logger.info("Created automated workflow %s: %s", workflow_id, name)
        return workflow_id

    async def start_workflow_execution(self, workflow_id: str, trigger_payload: dict | None = None) -> bool:
        """Start executing automated workflow.

        Args:
            workflow_id: ID of the workflow to execute.
            trigger_payload: Optional event data from the trigger that
                fired this workflow (#3138). Injected into the workflow's
                execution context as ``trigger_payload``.
        """
        if workflow_id not in self.active_workflows:
            logger.error("Workflow %s not found", workflow_id)
            return False

        workflow = self.active_workflows[workflow_id]
        if trigger_payload is not None:
            workflow.trigger_payload = trigger_payload
        return await self.executor.start_execution(workflow, self.active_workflows)

    async def handle_workflow_control(self, control_request: WorkflowControlRequest) -> bool:
        """Handle workflow control actions from user"""
        return await self.controller.handle_control(control_request, self.active_workflows)

    def get_workflow_status(self, workflow_id: str) -> Metadata | None:
        """Get workflow status from active or completed (#372, #1367)."""
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            workflow = self.completed_workflows.get(workflow_id)
        if not workflow:
            return None
        return workflow.to_status_dict()

    def get_template_workflow(self, template_name: str, session_id: str) -> List[WorkflowStep]:
        """Get workflow steps from a template"""
        return self.template_manager.get_template(template_name, session_id)

    def list_templates(self) -> List[str]:
        """List available workflow templates"""
        return self.template_manager.list_templates()

    # =========================================================================
    # Issue #1367: Completed Workflow History
    # =========================================================================

    MAX_COMPLETED_HISTORY = 100

    def archive_completed_workflow(self, workflow_id: str) -> None:
        """Move finished workflow from active to completed (#1367)."""
        workflow = self.active_workflows.pop(workflow_id, None)
        if not workflow:
            return
        self.completed_workflows[workflow_id] = workflow
        while len(self.completed_workflows) > self.MAX_COMPLETED_HISTORY:
            oldest_key = next(iter(self.completed_workflows))
            del self.completed_workflows[oldest_key]
        logger.info("Archived workflow %s to completed history", workflow_id)

    def get_completed_workflows(self) -> List[Metadata]:
        """Return all completed workflow statuses (#1367)."""
        return [wf.to_status_dict() for wf in self.completed_workflows.values()]

    # =========================================================================
    # Issue #390: Plan Approval System Methods
    # =========================================================================

    async def present_plan_for_approval(
        self,
        workflow_id: str,
        approval_mode: PlanApprovalMode = PlanApprovalMode.FULL_PLAN_APPROVAL,
        timeout_seconds: int = 300,
    ) -> PlanApprovalRequest | None:
        """
        Present workflow plan to user for approval before execution.

        Issue #390: Multi-step tasks should present plan before execution.

        Args:
            workflow_id: ID of the workflow to present
            approval_mode: How approval should be requested
            timeout_seconds: How long to wait for approval

        Returns:
            PlanApprovalRequest with presentation data, or None if workflow not found
        """
        if workflow_id not in self.active_workflows:
            logger.error("Workflow %s not found for plan presentation", workflow_id)
            return None

        workflow = self.active_workflows[workflow_id]
        return await self.executor.present_plan_for_approval(workflow, approval_mode, timeout_seconds)

    async def wait_for_plan_approval(
        self,
        workflow_id: str,
        timeout_seconds: int = 300,
    ) -> PlanApprovalRequest | None:
        """
        Wait for user to approve or reject the presented plan.

        Issue #390: Block execution until user approves plan.

        Args:
            workflow_id: ID of the workflow awaiting approval
            timeout_seconds: Maximum time to wait

        Returns:
            PlanApprovalRequest with final status, or None on error
        """
        try:
            return await self.executor.wait_for_plan_approval(workflow_id, timeout_seconds)
        except ValueError as e:
            logger.error("Error waiting for plan approval: %s", e)
            return None

    def handle_plan_approval_response(
        self,
        workflow_id: str,
        approved: bool,
        modifications: list[str] | None = None,
        reason: str | None = None,
    ) -> bool:
        """
        Handle user's response to plan approval request.

        Issue #390: Process user's decision on presented plan.

        Args:
            workflow_id: ID of the workflow
            approved: Whether user approved the plan
            modifications: List of step IDs to modify/skip
            reason: User's reason for rejection/modification

        Returns:
            True if response was processed successfully
        """
        return self.executor.handle_plan_approval_response(workflow_id, approved, modifications, reason)

    def get_pending_approval(self, workflow_id: str) -> PlanApprovalRequest | None:
        """
        Get pending plan approval request for a workflow.

        Issue #390: Check pending approval status.
        """
        return self.executor.get_pending_approval(workflow_id)

    async def cancel_workflow(self, workflow_id: str) -> bool:
        """
        Cancel a workflow (e.g., after plan rejection).

        Issue #390: Allow cancellation after plan rejection.
        """
        if workflow_id not in self.active_workflows:
            logger.error("Workflow %s not found for cancellation", workflow_id)
            return False

        workflow = self.active_workflows[workflow_id]
        await self.executor.cancel_workflow(workflow, self.active_workflows)
        return True
