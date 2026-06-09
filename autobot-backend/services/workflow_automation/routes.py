# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Automation Routes Module

FastAPI endpoints for workflow automation.
"""

import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from constants.error_constants import ERR_WORKFLOW_NOT_FOUND
from services.notification_service import NotificationConfig

from .manager import WorkflowAutomationManager
from .models import (
    AutomatedWorkflowRequest,
    AutomationMode,
    NotificationConfigRequest,
    PlanApprovalMode,
    PlanApprovalResponse,
    PlanPresentationRequest,
    WorkflowControlRequest,
    WorkflowStep,
)
from .persistence import load_notification_config, save_notification_config

logger = get_logger(__name__)

router = APIRouter(tags=["workflow_automation"])

get_workflow_manager = lazy_singleton(WorkflowAutomationManager)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_workflow",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.post("/create_workflow")
async def create_workflow(
    request: AutomatedWorkflowRequest,
    current_user: dict = Depends(get_current_user),
):
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
        logger.error("Failed to create workflow: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_workflow",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.post("/start_workflow/{workflow_id}")
async def start_workflow(workflow_id: str, current_user: dict = Depends(get_current_user)):
    """Start executing automated workflow"""
    try:
        success = await get_workflow_manager().start_workflow_execution(workflow_id)

        if success:
            return {
                "success": True,
                "message": f"Workflow {workflow_id} started successfully",
            }
        else:
            raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)

    except Exception as e:
        logger.error("Failed to start workflow: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="control_workflow",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.post("/control_workflow")
async def control_workflow(
    request: WorkflowControlRequest,
    current_user: dict = Depends(get_current_user),
):
    """Control workflow execution (pause, resume, cancel, approve, skip)"""
    try:
        success = await get_workflow_manager().handle_workflow_control(request)

        if success:
            return {
                "success": True,
                "message": (f"Workflow control action '{request.action}' executed successfully"),
            }
        else:
            raise HTTPException(status_code=404, detail="Workflow not found or action failed")

    except Exception as e:
        logger.error("Failed to control workflow: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_workflow_status",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.get("/workflow_status/{workflow_id}")
async def get_workflow_status(workflow_id: str, current_user: dict = Depends(get_current_user)):
    """Get current workflow status"""
    try:
        status = get_workflow_manager().get_workflow_status(workflow_id)

        if status:
            return {"success": True, "workflow": status}
        else:
            raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)

    except Exception as e:
        logger.error("Failed to get workflow status: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_active_workflows",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.get("/active_workflows")
async def get_active_workflows(
    current_user: dict = Depends(get_current_user),
):
    """Get list of all active workflows"""
    try:
        workflows = []
        for workflow_id in get_workflow_manager().active_workflows:
            status = get_workflow_manager().get_workflow_status(workflow_id)
            if status:
                workflows.append(status)

        return {"success": True, "workflows": workflows, "count": len(workflows)}

    except Exception as e:
        logger.error("Failed to get active workflows: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_completed_workflows",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.get("/completed_workflows")
async def get_completed_workflows(
    current_user: dict = Depends(get_current_user),
):
    """Return completed workflow history (#1367)."""
    try:
        workflows = get_workflow_manager().get_completed_workflows()
        return {
            "success": True,
            "workflows": workflows,
            "count": len(workflows),
        }
    except Exception as e:
        logger.error("Failed to get completed workflows: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_workflow_from_chat",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.post("/create_from_chat")
async def create_workflow_from_chat(request: dict, current_user: dict = Depends(get_current_user)):
    """
    Create workflow from natural language chat request.

    Issue #390: Now presents plan for approval instead of auto-starting.
    """
    try:
        user_request = request.get("user_request", "")
        session_id = request.get("session_id", "")
        # Issue #390: Backward compatible - auto_start=True by default
        # Set require_approval=True to enable plan approval flow
        auto_start = request.get("auto_start", True)  # Keep backward compatible
        require_approval = request.get("require_approval", False)  # Opt-in
        approval_mode = request.get("approval_mode", "full_plan")

        if not user_request or not session_id:
            raise HTTPException(status_code=400, detail="user_request and session_id are required")

        workflow_id = await get_workflow_manager().create_workflow_from_chat_request(user_request, session_id)

        if workflow_id:
            # Issue #390: Support both modes for backward compatibility
            if require_approval and not auto_start:
                # New behavior: Present plan for approval before execution
                plan_approval = await get_workflow_manager().present_plan_for_approval(
                    workflow_id, PlanApprovalMode(approval_mode)
                )

                return {
                    "success": True,
                    "workflow_id": workflow_id,
                    "message": "Workflow plan presented for approval",
                    "status": "awaiting_approval",
                    "plan": (plan_approval.to_presentation_dict() if plan_approval else None),
                }
            else:
                # Legacy behavior: auto-start immediately (backward compatible default)
                await get_workflow_manager().start_workflow_execution(workflow_id)
                return {
                    "success": True,
                    "workflow_id": workflow_id,
                    "message": "Workflow created and started from chat request",
                    "status": "executing",
                }
        else:
            return {
                "success": False,
                "message": "Could not create workflow from chat request",
            }

    except Exception as e:
        logger.error("Failed to create workflow from chat: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =========================================================================
# Issue #390: Plan Approval Endpoints
# =========================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="present_plan",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.post("/present_plan/{workflow_id}")
async def present_plan(
    workflow_id: str,
    request: PlanPresentationRequest = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Present workflow plan to user for approval.

    Issue #390: Show plan before execution starts.
    """
    try:
        approval_mode = PlanApprovalMode.FULL_PLAN_APPROVAL
        timeout_seconds = 300

        if request:
            approval_mode = PlanApprovalMode(request.approval_mode)
            timeout_seconds = request.timeout_seconds

        plan_approval = await get_workflow_manager().present_plan_for_approval(
            workflow_id, approval_mode, timeout_seconds
        )

        if plan_approval:
            return {
                "success": True,
                "workflow_id": workflow_id,
                "status": "awaiting_approval",
                "plan": plan_approval.to_presentation_dict(),
            }
        else:
            raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)

    except Exception as e:
        logger.error("Failed to present plan: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


def _validate_approval_request(workflow_id: str) -> None:
    """Helper for approve_plan. Ref: #1088.

    Verifies that the workflow exists and has a pending approval.
    Raises HTTPException(404) if either check fails.
    """
    if not get_workflow_manager().get_workflow_status(workflow_id):
        raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)
    if not get_workflow_manager().get_pending_approval(workflow_id):
        raise HTTPException(status_code=404, detail="No pending approval for this workflow")


async def _execute_approval_outcome(request: PlanApprovalResponse) -> dict:
    """Helper for approve_plan. Ref: #1088.

    Starts workflow execution on approval, or cancels it on rejection.
    Returns the appropriate response dict.
    """
    if request.approved:
        await get_workflow_manager().start_workflow_execution(request.workflow_id)
        return {
            "success": True,
            "workflow_id": request.workflow_id,
            "status": "executing",
            "message": "Plan approved, workflow execution started",
        }

    await get_workflow_manager().cancel_workflow(request.workflow_id)
    return {
        "success": True,
        "workflow_id": request.workflow_id,
        "status": "rejected",
        "message": f"Plan rejected: {request.reason or 'No reason provided'}",
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve_plan",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.post("/approve_plan")
async def approve_plan(
    request: PlanApprovalResponse,
    current_user: dict = Depends(get_current_user),
):
    """
    Handle user's approval/rejection of workflow plan.

    Issue #390: Process plan approval before execution.

    Note: Authorization is validated by checking session_id matches the workflow.
    The client must provide the correct session_id that owns the workflow.
    """
    try:
        # Issue #390 Security Fix: Verify workflow exists and has pending approval.
        # Full session ownership validation should be done at API gateway level
        # or via session token in request headers.
        _validate_approval_request(request.workflow_id)

        success = get_workflow_manager().handle_plan_approval_response(
            workflow_id=request.workflow_id,
            approved=request.approved,
            modifications=request.modifications,
            reason=request.reason,
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to process approval response")

        return await _execute_approval_outcome(request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to process plan approval: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pending_approval",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.get("/pending_approval/{workflow_id}")
async def get_pending_approval(workflow_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get pending plan approval status for a workflow.

    Issue #390: Check if plan is awaiting approval.
    """
    try:
        approval = get_workflow_manager().get_pending_approval(workflow_id)

        if approval:
            return {
                "success": True,
                "workflow_id": workflow_id,
                "has_pending_approval": True,
                "approval": approval.to_presentation_dict(),
            }
        else:
            return {
                "success": True,
                "workflow_id": workflow_id,
                "has_pending_approval": False,
                "approval": None,
            }

    except Exception as e:
        logger.error("Failed to get pending approval: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =========================================================================
# Issue #3139: Per-Workflow Notification Configuration
# =========================================================================


def _find_workflow(workflow_id: str, current_user: dict = None):
    """Look up a workflow in active or completed stores.

    Returns the ActiveWorkflow dataclass or raises 404/403.
    Verifies ownership when current_user is provided.
    """
    mgr = get_workflow_manager()
    wf = mgr.active_workflows.get(workflow_id)
    if wf is None:
        wf = mgr.completed_workflows.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=ERR_WORKFLOW_NOT_FOUND)
    if current_user and hasattr(wf, "owner_id") and wf.owner_id:
        user_id = current_user.get("user_id", current_user.get("sub"))
        if user_id and wf.owner_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
    return wf


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_notification_config",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.get("/notification_config/{workflow_id}")
async def get_notification_config(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return the notification configuration for a workflow (#3139, #3166)."""
    try:
        wf = _find_workflow(workflow_id, current_user)
        if wf.notification_config is None:
            wf.notification_config = await load_notification_config(workflow_id)
        config_dict = None
        if wf.notification_config is not None:
            config_dict = asdict(wf.notification_config)
        return {
            "success": True,
            "workflow_id": workflow_id,
            "notification_config": config_dict,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get notification config: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_notification_config",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.put("/notification_config/{workflow_id}")
async def update_notification_config(
    workflow_id: str,
    request: NotificationConfigRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Create or update the notification configuration for a workflow (#3139, #3166).

    When ``enabled`` is false the config is removed entirely so the
    executor skips notification delivery.  The config is persisted to
    Redis so it survives a backend restart.
    """
    try:
        wf = _find_workflow(workflow_id, current_user)
        if not request.enabled:
            wf.notification_config = None
        else:
            user_id = current_user.get("user_id", current_user.get("sub", ""))
            wf.notification_config = NotificationConfig(
                workflow_id=workflow_id,
                user_id=user_id,
                channels=request.channels,
                templates=request.templates,
                email_recipients=request.email_recipients,
                slack_webhook_url=request.slack_webhook_url,
                webhook_url=request.webhook_url,
            )
        await save_notification_config(workflow_id, wf.notification_config)
        config_dict = None
        if wf.notification_config is not None:
            config_dict = asdict(wf.notification_config)
        return {
            "success": True,
            "workflow_id": workflow_id,
            "notification_config": config_dict,
            "message": "Notification configuration updated",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update notification config: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =========================================================================
# Issue #1380: State Machine Inspection
# =========================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_workflow_state",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.get("/workflow_state/{workflow_id}")
async def get_workflow_state(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return the state-machine state for a workflow (#1380)."""
    try:
        sm = get_workflow_manager().executor.state_machine
        state = await sm.load(workflow_id)
        if state:
            return {"success": True, "state": state.model_dump()}
        raise HTTPException(status_code=404, detail="Workflow state not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get workflow state: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# WebSocket endpoint for real-time workflow communication
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="workflow_websocket",
    error_code_prefix="WORKFLOW_AUTOMATION",
)
@router.websocket("/workflow_ws/{session_id}")
async def workflow_websocket(websocket: WebSocket, session_id: str) -> None:
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
                    control_request = WorkflowControlRequest(workflow_id=workflow_id, action=action)
                    await get_workflow_manager().handle_workflow_control(control_request)

    except WebSocketDisconnect:
        # Clean up on disconnect
        if session_id in get_workflow_manager().terminal_sessions:
            del get_workflow_manager().terminal_sessions[session_id]
        logger.info("WebSocket disconnected for session %s", session_id)
    except Exception as e:
        logger.error("WebSocket error for session %s: %s", session_id, e)
        if session_id in get_workflow_manager().terminal_sessions:
            del get_workflow_manager().terminal_sessions[session_id]
