#!/usr/bin/env python3
"""
Workflow Automation API - Backend integration for session takeover and automated workflows
Handles workflow execution, step management, and user intervention points
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Issue #1009: Graceful fallback when orchestrator deps unavailable
try:
    from api.simple_terminal_websocket import SimpleTerminalWebSocket
    from enhanced_orchestrator import EnhancedOrchestrator
    from orchestrator import Orchestrator

    _WORKFLOW_DEPS_AVAILABLE = True
except ImportError:
    SimpleTerminalWebSocket = None
    EnhancedOrchestrator = None
    Orchestrator = None
    _WORKFLOW_DEPS_AVAILABLE = False
    logger.warning("Workflow automation deps unavailable (orchestrator not found)")

router = APIRouter(tags=["workflow_automation"])


class WorkflowStepStatus(Enum):
    PENDING = "pending"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    PAUSED = "paused"


class AutomationMode(Enum):
    MANUAL = "manual"
    SEMI_AUTOMATIC = "semi_automatic"  # Requires user confirmation
    AUTOMATIC = "automatic"  # Auto-execute safe commands


@dataclass
class WorkflowStep:
    """Individual step in an automated workflow"""

    step_id: str
    command: str
    description: str
    explanation: Optional[str] = None
    requires_confirmation: bool = True
    risk_level: str = "low"
    estimated_duration: float = 5.0
    dependencies: List[str] = None
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    execution_result: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class WorkflowStepRequest(BaseModel):
    command: str
    description: str
    explanation: Optional[str] = None
    requires_confirmation: bool = True
    risk_level: str = "low"
    dependencies: List[str] = []


class AutomatedWorkflowRequest(BaseModel):
    name: str
    description: Optional[str] = None
    steps: List[WorkflowStepRequest]
    session_id: str
    automation_mode: str = "semi_automatic"
    timeout_per_step: int = 300  # 5 minutes default


class WorkflowControlRequest(BaseModel):
    workflow_id: str
    action: str  # pause, resume, cancel, approve_step, skip_step
    step_id: Optional[str] = None
    user_input: Optional[str] = None


@dataclass
class ActiveWorkflow:
    """Active workflow session state"""

    workflow_id: str
    name: str
    description: str
    session_id: str
    steps: List[WorkflowStep]
    current_step_index: int = 0
    automation_mode: AutomationMode = AutomationMode.SEMI_AUTOMATIC
    is_paused: bool = False
    is_cancelled: bool = False
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    user_interventions: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.user_interventions is None:
            self.user_interventions = []


class WorkflowAutomationManager:
    """Manages automated workflow execution with user intervention points"""

    def __init__(self):
        self.active_workflows: Dict[str, ActiveWorkflow] = {}
        self.terminal_sessions: Dict[str, SimpleTerminalWebSocket] = {}
        self.orchestrator = Orchestrator()
        self.enhanced_orchestrator = EnhancedOrchestrator()

        # Workflow templates for common tasks
        self.workflow_templates = {
            "system_update": self._create_system_update_workflow,
            "dev_environment": self._create_dev_environment_workflow,
            "security_scan": self._create_security_scan_workflow,
            "backup_creation": self._create_backup_workflow,
        }

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
        # This would be enhanced based on step.action and step.agent_type
        if hasattr(step, "inputs") and step.inputs:
            command = step.inputs.get("command", "")
            if command:
                return command

        # Fallback: create command from action description
        action = step.action.lower()
        if "update" in action and "package" in action:
            return "sudo apt update"
        elif "install" in action:
            # Extract package names from action
            return "sudo apt install -y git curl wget"  # Default tools
        elif "search" in action:
            return "find . -name '*' -type "  # Generic search
        else:
            return f"echo 'Executing: {step.action}'"  # Safe fallback

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
        workflow.started_at = datetime.now()

        # Send workflow start message to frontend
        await self._send_workflow_message(
            workflow.session_id,
            {
                "type": "start_workflow",
                "workflow": {
                    "id": workflow_id,
                    "name": workflow.name,
                    "description": workflow.description,
                    "steps": [
                        {
                            "stepNumber": i + 1,
                            "totalSteps": len(workflow.steps),
                            "command": step.command,
                            "description": step.description,
                            "explanation": step.explanation,
                            "requiresConfirmation": step.requires_confirmation,
                        }
                        for i, step in enumerate(workflow.steps)
                    ],
                },
            },
        )

        # Start processing first step
        await self._process_next_workflow_step(workflow_id)
        return True

    async def _process_next_workflow_step(self, workflow_id: str):
        """Process the next step in workflow"""
        if workflow_id not in self.active_workflows:
            return

        workflow = self.active_workflows[workflow_id]

        if workflow.is_paused or workflow.is_cancelled:
            return

        if workflow.current_step_index >= len(workflow.steps):
            # Workflow completed
            await self._complete_workflow(workflow_id)
            return

        current_step = workflow.steps[workflow.current_step_index]

        # Check dependencies
        if not await self._check_step_dependencies(workflow_id, current_step):
            logger.warning(f"Step {current_step.step_id} dependencies not met")
            current_step.status = WorkflowStepStatus.SKIPPED
            workflow.current_step_index += 1
            await self._process_next_workflow_step(workflow_id)
            return

        # Update step status
        current_step.status = WorkflowStepStatus.WAITING_APPROVAL
        current_step.started_at = datetime.now()

        # Send step confirmation request to frontend
        await self._send_step_confirmation_request(workflow_id, current_step)

    async def _send_step_confirmation_request(
        self, workflow_id: str, step: WorkflowStep
    ):
        """Send step confirmation request to frontend"""
        workflow = self.active_workflows[workflow_id]

        step_data = {
            "stepNumber": workflow.current_step_index + 1,
            "totalSteps": len(workflow.steps),
            "command": step.command,
            "description": step.description,
            "explanation": step.explanation,
            "requiresConfirmation": step.requires_confirmation,
            "riskLevel": step.risk_level,
            "estimatedDuration": step.estimated_duration,
        }

        # Send to terminal for step confirmation
        await self._send_workflow_message(
            workflow.session_id,
            {
                "type": "step_confirmation_required",
                "workflow_id": workflow_id,
                "step_id": step.step_id,
                "step_data": step_data,
            },
        )

    async def handle_workflow_control(
        self, control_request: WorkflowControlRequest
    ) -> bool:
        """Handle workflow control actions from user"""
        workflow_id = control_request.workflow_id

        if workflow_id not in self.active_workflows:
            logger.error(f"Workflow {workflow_id} not found for control action")
            return False

        workflow = self.active_workflows[workflow_id]
        action = control_request.action.lower()

        # Log user intervention
        intervention = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "step_id": control_request.step_id,
            "user_input": control_request.user_input,
        }
        workflow.user_interventions.append(intervention)

        if action == "pause":
            workflow.is_paused = True
            await self._send_workflow_message(
                workflow.session_id,
                {"type": "workflow_paused", "workflow_id": workflow_id},
            )

        elif action == "resume":
            workflow.is_paused = False
            await self._send_workflow_message(
                workflow.session_id,
                {"type": "workflow_resumed", "workflow_id": workflow_id},
            )
            await self._process_next_workflow_step(workflow_id)

        elif action == "cancel":
            workflow.is_cancelled = True
            await self._cancel_workflow(workflow_id)

        elif action == "approve_step":
            await self._approve_and_execute_step(workflow_id, control_request.step_id)

        elif action == "skip_step":
            await self._skip_workflow_step(workflow_id, control_request.step_id)

        else:
            logger.warning(f"Unknown workflow control action: {action}")
            return False

        return True

    async def _approve_and_execute_step(self, workflow_id: str, step_id: str):
        """Approve and execute workflow step"""
        workflow = self.active_workflows[workflow_id]
        current_step = workflow.steps[workflow.current_step_index]

        if current_step.step_id != step_id:
            logger.error(
                f"Step ID mismatch: expected {current_step.step_id}, got {step_id}"
            )
            return

        current_step.status = WorkflowStepStatus.EXECUTING

        try:
            # Execute command via terminal
            result = await self._execute_workflow_command(
                workflow.session_id, current_step.command
            )

            current_step.status = WorkflowStepStatus.COMPLETED
            current_step.execution_result = result
            current_step.completed_at = datetime.now()

            # Move to next step
            workflow.current_step_index += 1

            # Small delay before next step
            await asyncio.sleep(2)
            await self._process_next_workflow_step(workflow_id)

        except Exception as e:
            logger.error(f"Step execution failed: {e}")
            current_step.status = WorkflowStepStatus.FAILED
            current_step.execution_result = {"error": str(e)}

            # Pause workflow on error
            workflow.is_paused = True
            await self._send_workflow_message(
                workflow.session_id,
                {
                    "type": "step_failed",
                    "workflow_id": workflow_id,
                    "step_id": step_id,
                    "error": str(e),
                },
            )

    async def _skip_workflow_step(self, workflow_id: str, step_id: str):
        """Skip current workflow step"""
        workflow = self.active_workflows[workflow_id]
        current_step = workflow.steps[workflow.current_step_index]

        if current_step.step_id == step_id:
            current_step.status = WorkflowStepStatus.SKIPPED
            current_step.completed_at = datetime.now()
            workflow.current_step_index += 1

            # Continue with next step
            await asyncio.sleep(1)
            await self._process_next_workflow_step(workflow_id)

    async def _execute_workflow_command(
        self, session_id: str, command: str
    ) -> Dict[str, Any]:
        """Execute command via terminal session"""
        # This would integrate with the existing terminal WebSocket system
        # For now, simulate command execution

        logger.info(f"Executing workflow command: {command}")

        # Simulate command execution delay
        await asyncio.sleep(1)

        return {
            "command": command,
            "exit_code": 0,
            "stdout": f"Simulated output for: {command}",
            "stderr": "",
            "execution_time": 1.0,
        }

    async def _check_step_dependencies(
        self, workflow_id: str, step: WorkflowStep
    ) -> bool:
        """Check if step dependencies are satisfied"""
        if not step.dependencies:
            return True

        workflow = self.active_workflows[workflow_id]

        for dep_step_id in step.dependencies:
            # Find dependency step
            dep_step = None
            for s in workflow.steps:
                if s.step_id == dep_step_id:
                    dep_step = s
                    break

            if not dep_step or dep_step.status != WorkflowStepStatus.COMPLETED:
                return False

        return True

    async def _complete_workflow(self, workflow_id: str):
        """Complete workflow execution"""
        workflow = self.active_workflows[workflow_id]
        workflow.completed_at = datetime.now()

        # Send completion message
        await self._send_workflow_message(
            workflow.session_id,
            {
                "type": "workflow_completed",
                "workflow_id": workflow_id,
                "name": workflow.name,
                "total_steps": len(workflow.steps),
                "completed_steps": len(
                    [
                        s
                        for s in workflow.steps
                        if s.status == WorkflowStepStatus.COMPLETED
                    ]
                ),
                "skipped_steps": len(
                    [
                        s
                        for s in workflow.steps
                        if s.status == WorkflowStepStatus.SKIPPED
                    ]
                ),
                "failed_steps": len(
                    [s for s in workflow.steps if s.status == WorkflowStepStatus.FAILED]
                ),
            },
        )

    async def _cancel_workflow(self, workflow_id: str):
        """Cancel workflow execution"""
        workflow = self.active_workflows[workflow_id]
        workflow.is_cancelled = True
        workflow.completed_at = datetime.now()

        await self._send_workflow_message(
            workflow.session_id,
            {"type": "workflow_cancelled", "workflow_id": workflow_id},
        )

    async def _send_workflow_message(self, session_id: str, message: Dict[str, Any]):
        """Send workflow control message to frontend terminal"""
        try:
            # This would integrate with the existing WebSocket system
            # For now, just log the message
            logger.info(f"Sending workflow message to {session_id}: {message}")

            # In real implementation, this would send via WebSocket to the terminal
            # websocket = self.terminal_sessions.get(session_id)
            # if websocket:
            #     await websocket.send_text(json.dumps(message))

        except Exception as e:
            logger.error(f"Failed to send workflow message: {e}")

    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
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

    # Workflow Templates
    def _create_system_update_workflow(self, session_id: str) -> List[WorkflowStep]:
        """Create system update workflow"""
        return [
            WorkflowStep(
                "update_repos", "sudo apt update", "Update package repositories"
            ),
            WorkflowStep(
                "upgrade_packages", "sudo apt upgrade -y", "Upgrade installed packages"
            ),
            WorkflowStep(
                "autoremove", "sudo apt autoremove -y", "Remove unnecessary packages"
            ),
            WorkflowStep(
                "verify", "apt list --upgradable", "Check for remaining updates"
            ),
        ]

    def _create_dev_environment_workflow(self, session_id: str) -> List[WorkflowStep]:
        """Create development environment setup workflow"""
        return [
            WorkflowStep("update_system", "sudo apt update", "Update system packages"),
            WorkflowStep(
                "install_git", "sudo apt install -y git", "Install Git version control"
            ),
            WorkflowStep(
                "install_nodejs",
                "curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -",
                "Setup Node.js repository",
            ),
            WorkflowStep(
                "install_nodejs_pkg",
                "sudo apt install -y nodejs",
                "Install Node.js and npm",
            ),
            WorkflowStep(
                "install_python",
                "sudo apt install -y python3 python3-pip",
                "Install Python 3 and pip",
            ),
            WorkflowStep(
                "verify_installs",
                "git --version && node --version && python3 --version",
                "Verify installations",
            ),
        ]


# Global workflow manager instance — only created when deps are available
workflow_manager = WorkflowAutomationManager() if _WORKFLOW_DEPS_AVAILABLE else None


def _require_workflow():
    """Raise 503 if workflow deps are unavailable (Issue #1009)."""
    if not _WORKFLOW_DEPS_AVAILABLE or workflow_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Workflow automation unavailable: missing dependencies",
        )


# API Endpoints
@router.post("/create_workflow")
async def create_workflow(
    request: AutomatedWorkflowRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create new automated workflow.

    Issue #744: Requires authenticated user.
    """
    _require_workflow()
    try:
        workflow_steps = [
            WorkflowStep(
                step_id=f"step_{i+1}",
                command=step.command,
                description=step.description,
                explanation=step.explanation,
                requires_confirmation=step.requires_confirmation,
                risk_level=step.risk_level,
                dependencies=step.dependencies,
            )
            for i, step in enumerate(request.steps)
        ]

        automation_mode = AutomationMode(request.automation_mode)

        workflow_id = await workflow_manager.create_automated_workflow(
            name=request.name,
            description=request.description or "",
            steps=workflow_steps,
            session_id=request.session_id,
            automation_mode=automation_mode,
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "message": f"Workflow '{request.name}' created successfully",
        }

    except Exception as e:
        logger.error(f"Failed to create workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start_workflow/{workflow_id}")
async def start_workflow(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Start executing automated workflow.

    Issue #744: Requires authenticated user.
    """
    _require_workflow()
    try:
        success = await workflow_manager.start_workflow_execution(workflow_id)

        if success:
            return {
                "success": True,
                "message": f"Workflow {workflow_id} started successfully",
            }
        else:
            raise HTTPException(status_code=404, detail="Workflow not found")

    except Exception as e:
        logger.error(f"Failed to start workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/control_workflow")
async def control_workflow(
    request: WorkflowControlRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Control workflow execution (pause, resume, cancel, approve, skip).

    Issue #744: Requires authenticated user.
    """
    _require_workflow()
    try:
        success = await workflow_manager.handle_workflow_control(request)

        if success:
            return {
                "success": True,
                "message": f"Workflow control action '{request.action}' executed successfully",
            }
        else:
            raise HTTPException(
                status_code=404, detail="Workflow not found or action failed"
            )

    except Exception as e:
        logger.error(f"Failed to control workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow_status/{workflow_id}")
async def get_workflow_status(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get current workflow status.

    Issue #744: Requires authenticated user.
    """
    _require_workflow()
    try:
        status = workflow_manager.get_workflow_status(workflow_id)

        if status:
            return {"success": True, "workflow": status}
        else:
            raise HTTPException(status_code=404, detail="Workflow not found")

    except Exception as e:
        logger.error(f"Failed to get workflow status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active_workflows")
async def get_active_workflows(
    current_user: dict = Depends(get_current_user),
):
    """
    Get list of all active workflows.

    Issue #744: Requires authenticated user.
    """
    _require_workflow()
    try:
        workflows = []
        for workflow_id in workflow_manager.active_workflows:
            status = workflow_manager.get_workflow_status(workflow_id)
            if status:
                workflows.append(status)

        return {"success": True, "workflows": workflows, "count": len(workflows)}

    except Exception as e:
        logger.error(f"Failed to get active workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create_from_chat")
async def create_workflow_from_chat(
    request: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Create workflow from natural language chat request.

    Issue #744: Requires authenticated user.
    """
    _require_workflow()
    try:
        user_request = request.get("user_request", "")
        session_id = request.get("session_id", "")

        if not user_request or not session_id:
            raise HTTPException(
                status_code=400, detail="user_request and session_id are required"
            )

        workflow_id = await workflow_manager.create_workflow_from_chat_request(
            user_request, session_id
        )

        if workflow_id:
            # Auto-start the workflow
            await workflow_manager.start_workflow_execution(workflow_id)

            return {
                "success": True,
                "workflow_id": workflow_id,
                "message": "Workflow created and started from chat request",
            }
        else:
            return {
                "success": False,
                "message": "Could not create workflow from chat request",
            }

    except Exception as e:
        logger.error(f"Failed to create workflow from chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint for real-time workflow communication
@router.websocket("/workflow_ws/{session_id}")
async def workflow_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time workflow communication"""
    if not _WORKFLOW_DEPS_AVAILABLE or workflow_manager is None:
        await websocket.close(code=1013, reason="Workflow automation unavailable")
        return
    await websocket.accept()

    # Register WebSocket connection
    workflow_manager.terminal_sessions[session_id] = websocket

    try:
        while True:
            # Listen for workflow control messages from frontend
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "automation_control":
                # Handle automation control from terminal
                action = message.get("action")
                workflow_id = message.get("workflow_id")

                if workflow_id and action:
                    control_request = WorkflowControlRequest(
                        workflow_id=workflow_id, action=action
                    )
                    await workflow_manager.handle_workflow_control(control_request)

    except WebSocketDisconnect:
        # Clean up on disconnect
        if session_id in workflow_manager.terminal_sessions:
            del workflow_manager.terminal_sessions[session_id]
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        if session_id in workflow_manager.terminal_sessions:
            del workflow_manager.terminal_sessions[session_id]
