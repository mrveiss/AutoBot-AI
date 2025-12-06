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
    WorkflowControlRequest,
    WorkflowStep,
)
from .templates import WorkflowTemplateManager

logger = logging.getLogger(__name__)


class WorkflowAutomationManager:
    """Manages automated workflow execution with user intervention points"""

    def __init__(self):
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
            logger.error(f"Failed to create workflow from chat request: {e}")
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

        logger.info(f"Created automated workflow {workflow_id}: {name}")
        return workflow_id

    async def start_workflow_execution(self, workflow_id: str) -> bool:
        """Start executing automated workflow"""
        if workflow_id not in self.active_workflows:
            logger.error(f"Workflow {workflow_id} not found")
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
        """Get current workflow status"""
        if workflow_id not in self.active_workflows:
            return None

        workflow = self.active_workflows[workflow_id]

        return {
            "workflow_id": workflow_id,
            "name": workflow.name,
            "description": workflow.description,
            "session_id": workflow.session_id,
            "current_step": workflow.current_step_index + 1,
            "total_steps": len(workflow.steps),
            "is_paused": workflow.is_paused,
            "is_cancelled": workflow.is_cancelled,
            "automation_mode": workflow.automation_mode.value,
            "created_at": workflow.created_at.isoformat(),
            "started_at": (
                workflow.started_at.isoformat() if workflow.started_at else None
            ),
            "completed_at": (
                workflow.completed_at.isoformat() if workflow.completed_at else None
            ),
            "steps": [
                {
                    "step_id": step.step_id,
                    "command": step.command,
                    "description": step.description,
                    "status": step.status.value,
                    "requires_confirmation": step.requires_confirmation,
                    "started_at": (
                        step.started_at.isoformat() if step.started_at else None
                    ),
                    "completed_at": (
                        step.completed_at.isoformat() if step.completed_at else None
                    ),
                }
                for step in workflow.steps
            ],
            "user_interventions": workflow.user_interventions,
        }

    def get_template_workflow(
        self, template_name: str, session_id: str
    ) -> List[WorkflowStep]:
        """Get workflow steps from a template"""
        return self.template_manager.get_template(template_name, session_id)

    def list_templates(self) -> List[str]:
        """List available workflow templates"""
        return self.template_manager.list_templates()
