# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Automation Manager Module

Main coordinator for workflow automation using composition.
"""

import logging
import uuid
from typing import Dict, List, Optional

from backend.type_defs.common import Metadata
from src.enhanced_orchestrator import EnhancedOrchestrator
from src.orchestrator import Orchestrator

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

logger = logging.getLogger(__name__)


class WorkflowAutomationManager:
    """Manages automated workflow execution with user intervention points"""

    def __init__(self):
        """Initialize manager with workflow state and specialized components."""
        # Core state
        self.active_workflows: Dict[str, ActiveWorkflow] = {}

        # Composition: delegate to specialized components
        self.messenger = WorkflowMessenger()
        self.executor = WorkflowExecutor(self.messenger)
        self.controller = WorkflowController(self.messenger, self.executor)
        self.template_manager = WorkflowTemplateManager()

        # Orchestrators for chat request processing
        self.orchestrator = Orchestrator()
        self.enhanced_orchestrator = EnhancedOrchestrator()

    @property
    def terminal_sessions(self) -> Dict:
        """Expose terminal sessions from messenger for WebSocket management"""
        return self.messenger.terminal_sessions

    async def create_workflow_from_chat_request(
        self, user_request: str, session_id: str
    ) -> Optional[str]:
        """Create automated workflow from natural language chat request"""
        try:
            # Use orchestrator to analyze request and create workflow steps
            complexity = self.orchestrator.classify_request_complexity(user_request)
            base_steps = self.orchestrator.plan_workflow_steps(user_request, complexity)

            # Convert orchestrator steps to workflow steps
            workflow_steps = []
            for i, step in enumerate(base_steps):
                workflow_step = WorkflowStep(
                    step_id=f"step_{i+1}",
                    command=self._extract_command_from_step(step),
                    description=step.action,
                    explanation=f"This step is part of: {user_request}",
                    requires_confirmation=step.user_approval_required,
                    dependencies=[
                        f"step_{j+1}"
                        for j in range(i)
                        if base_steps[j].id in (step.dependencies or [])
                    ],
                )
                workflow_steps.append(workflow_step)

            # Create workflow
            if workflow_steps:
                workflow_id = await self.create_automated_workflow(
                    name=f"Chat Request: {user_request[:50]}...",
                    description=user_request,
                    steps=workflow_steps,
                    session_id=session_id,
                )
                return workflow_id

            return None

        except Exception as e:
            logger.error("Failed to create workflow from chat request: %s", e)
            return None

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
    ) -> str:
        """Create new automated workflow"""
        workflow_id = str(uuid.uuid4())

        workflow = ActiveWorkflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            session_id=session_id,
            steps=steps,
            automation_mode=automation_mode,
        )

        self.active_workflows[workflow_id] = workflow

        logger.info("Created automated workflow %s: %s", workflow_id, name)
        return workflow_id

    async def start_workflow_execution(self, workflow_id: str) -> bool:
        """Start executing automated workflow"""
        if workflow_id not in self.active_workflows:
            logger.error("Workflow %s not found", workflow_id)
            return False

        workflow = self.active_workflows[workflow_id]
        return await self.executor.start_execution(workflow, self.active_workflows)

    async def handle_workflow_control(
        self, control_request: WorkflowControlRequest
    ) -> bool:
        """Handle workflow control actions from user"""
        return await self.controller.handle_control(
            control_request, self.active_workflows
        )

    def get_workflow_status(self, workflow_id: str) -> Optional[Metadata]:
        """Get current workflow status (Issue #372 - uses model method)."""
        if workflow_id not in self.active_workflows:
            return None

        workflow = self.active_workflows[workflow_id]
        return workflow.to_status_dict()

    def get_template_workflow(
        self, template_name: str, session_id: str
    ) -> List[WorkflowStep]:
        """Get workflow steps from a template"""
        return self.template_manager.get_template(template_name, session_id)

    def list_templates(self) -> List[str]:
        """List available workflow templates"""
        return self.template_manager.list_templates()

    # =========================================================================
    # Issue #390: Plan Approval System Methods
    # =========================================================================

    async def present_plan_for_approval(
        self,
        workflow_id: str,
        approval_mode: PlanApprovalMode = PlanApprovalMode.FULL_PLAN_APPROVAL,
        timeout_seconds: int = 300,
    ) -> Optional[PlanApprovalRequest]:
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
        return await self.executor.present_plan_for_approval(
            workflow, approval_mode, timeout_seconds
        )

    async def wait_for_plan_approval(
        self,
        workflow_id: str,
        timeout_seconds: int = 300,
    ) -> Optional[PlanApprovalRequest]:
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
            return await self.executor.wait_for_plan_approval(
                workflow_id, timeout_seconds
            )
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
        return self.executor.handle_plan_approval_response(
            workflow_id, approved, modifications, reason
        )

    def get_pending_approval(self, workflow_id: str) -> Optional[PlanApprovalRequest]:
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
