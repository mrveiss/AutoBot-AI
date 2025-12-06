# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Automation Routes Module

FastAPI endpoints for workflow automation.
"""

import json
import logging
import threading

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from .manager import WorkflowAutomationManager
from .models import (
    AutomatedWorkflowRequest,
    AutomationMode,
    WorkflowControlRequest,
    WorkflowStep,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow_automation", tags=["workflow_automation"])

# Global workflow manager instance (lazy initialization, thread-safe)
# REUSABLE PATTERN: Lazy initialization avoids creating async resources at module import time
_workflow_manager = None
_workflow_manager_lock = threading.Lock()


def get_workflow_manager() -> WorkflowAutomationManager:
    """
    Get or create the global workflow manager instance (thread-safe).

    REUSABLE PATTERN: Lazy singleton initialization with double-checked locking
    - Avoids creating async resources at module import time
    - Ensures event loop exists before instantiation
    - Thread-safe for FastAPI async context via double-checked locking
    """
    global _workflow_manager
    if _workflow_manager is None:
        with _workflow_manager_lock:
            # Double-check after acquiring lock
            if _workflow_manager is None:
                _workflow_manager = WorkflowAutomationManager()
    return _workflow_manager


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_workflow",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.post("/create_workflow")
async def create_workflow(request: AutomatedWorkflowRequest):
    """Create new automated workflow"""
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

        workflow_id = await get_workflow_manager().create_automated_workflow(
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_workflow",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.post("/start_workflow/{workflow_id}")
async def start_workflow(workflow_id: str):
    """Start executing automated workflow"""
    try:
        success = await get_workflow_manager().start_workflow_execution(workflow_id)

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="control_workflow",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.post("/control_workflow")
async def control_workflow(request: WorkflowControlRequest):
    """Control workflow execution (pause, resume, cancel, approve, skip)"""
    try:
        success = await get_workflow_manager().handle_workflow_control(request)

        if success:
            return {
                "success": True,
                "message": (
                    f"Workflow control action '{request.action}' executed successfully"
                ),
            }
        else:
            raise HTTPException(
                status_code=404, detail="Workflow not found or action failed"
            )

    except Exception as e:
        logger.error(f"Failed to control workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_workflow_status",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.get("/workflow_status/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Get current workflow status"""
    try:
        status = get_workflow_manager().get_workflow_status(workflow_id)

        if status:
            return {"success": True, "workflow": status}
        else:
            raise HTTPException(status_code=404, detail="Workflow not found")

    except Exception as e:
        logger.error(f"Failed to get workflow status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_active_workflows",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.get("/active_workflows")
async def get_active_workflows():
    """Get list of all active workflows"""
    try:
        workflows = []
        for workflow_id in get_workflow_manager().active_workflows:
            status = get_workflow_manager().get_workflow_status(workflow_id)
            if status:
                workflows.append(status)

        return {"success": True, "workflows": workflows, "count": len(workflows)}

    except Exception as e:
        logger.error(f"Failed to get active workflows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_workflow_from_chat",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.post("/create_from_chat")
async def create_workflow_from_chat(request: dict):
    """Create workflow from natural language chat request"""
    try:
        user_request = request.get("user_request", "")
        session_id = request.get("session_id", "")

        if not user_request or not session_id:
            raise HTTPException(
                status_code=400, detail="user_request and session_id are required"
            )

        workflow_id = await get_workflow_manager().create_workflow_from_chat_request(
            user_request, session_id
        )

        if workflow_id:
            # Auto-start the workflow
            await get_workflow_manager().start_workflow_execution(workflow_id)

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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="workflow_websocket",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.websocket("/workflow_ws/{session_id}")
async def workflow_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time workflow communication"""
    await websocket.accept()

    # Register WebSocket connection
    get_workflow_manager().terminal_sessions[session_id] = websocket

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
                    await get_workflow_manager().handle_workflow_control(
                        control_request
                    )

    except WebSocketDisconnect:
        # Clean up on disconnect
        if session_id in get_workflow_manager().terminal_sessions:
            del get_workflow_manager().terminal_sessions[session_id]
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        if session_id in get_workflow_manager().terminal_sessions:
            del get_workflow_manager().terminal_sessions[session_id]
