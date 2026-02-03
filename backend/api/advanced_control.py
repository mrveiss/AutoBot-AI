# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Control API for AutoBot Phase 8
Provides monitoring, desktop streaming, and takeover management endpoints
"""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.type_defs.common import Metadata
from src.auth_middleware import check_admin_permission
from src.constants.threshold_constants import TimingConstants
from src.desktop_streaming_manager import desktop_streaming
from src.enhanced_memory_manager_async import TaskPriority
from src.takeover_manager import TakeoverTrigger, takeover_manager
from src.task_execution_tracker import task_tracker
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["advanced_control"])


# Request/Response Models
class StreamingSessionRequest(BaseModel):
    user_id: str
    resolution: str = "1024x768"
    depth: int = 24


class StreamingSessionResponse(BaseModel):
    session_id: str
    vnc_port: int
    novnc_port: Optional[int]
    display: str
    vnc_url: str
    web_url: Optional[str]
    websocket_endpoint: str


class TakeoverRequest(BaseModel):
    trigger: str
    reason: str
    requesting_agent: Optional[str] = None
    affected_tasks: Optional[List[str]] = None
    priority: str = "HIGH"
    timeout_minutes: Optional[int] = None
    auto_approve: bool = False


class TakeoverApprovalRequest(BaseModel):
    human_operator: str
    takeover_scope: Optional[Metadata] = None


class TakeoverActionRequest(BaseModel):
    action_type: str
    action_data: Metadata


class SystemMonitoringResponse(BaseModel):
    system_status: Metadata
    active_sessions: List[Metadata]
    pending_takeovers: List[Metadata]
    active_takeovers: List[Metadata]
    resource_usage: Metadata


# Desktop Streaming Endpoints
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_streaming_session",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.post("/streaming/create", response_model=StreamingSessionResponse)
async def create_streaming_session(
    request: StreamingSessionRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Create a new desktop streaming session

    Issue #744: Requires admin authentication.
    """
    async with task_tracker.track_task(
        "Create Desktop Streaming Session",
        f"Creating streaming session for user {request.user_id}",
        agent_type="advanced_control",
        priority=TaskPriority.HIGH,
        inputs={"user_id": request.user_id, "resolution": request.resolution},
    ) as task_context:
        session_config = {"resolution": request.resolution, "depth": request.depth}

        result = await desktop_streaming.create_streaming_session(
            user_id=request.user_id, session_config=session_config
        )

        response = StreamingSessionResponse(**result)
        task_context.set_outputs({"session_id": response.session_id})

        logger.info("Desktop streaming session created: %s", response.session_id)
        return response


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="terminate_streaming_session",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.delete("/streaming/{session_id}")
async def terminate_streaming_session(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Terminate a desktop streaming session

    Issue #744: Requires admin authentication.
    """
    success = await desktop_streaming.terminate_streaming_session(session_id)
    if success:
        logger.info("Desktop streaming session terminated: %s", session_id)
        return {"success": True, "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail="Session not found")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_streaming_sessions",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.get("/streaming/sessions")
async def list_streaming_sessions(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    List all active streaming sessions

    Issue #744: Requires admin authentication.
    """
    sessions = desktop_streaming.vnc_manager.list_active_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_streaming_capabilities",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.get("/streaming/capabilities")
async def get_streaming_capabilities(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get desktop streaming system capabilities

    Issue #744: Requires admin authentication.
    """
    capabilities = desktop_streaming.get_system_capabilities()
    return capabilities


# Takeover Management Endpoints
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="request_takeover",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.post("/takeover/request")
async def request_takeover(
    request: TakeoverRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Request human takeover of autonomous operations

    Issue #744: Requires admin authentication.
    """
    # Convert string enum to TakeoverTrigger
    trigger_mapping = {
        "MANUAL_REQUEST": TakeoverTrigger.MANUAL_REQUEST,
        "CRITICAL_ERROR": TakeoverTrigger.CRITICAL_ERROR,
        "SECURITY_CONCERN": TakeoverTrigger.SECURITY_CONCERN,
        "USER_INTERVENTION_REQUIRED": TakeoverTrigger.USER_INTERVENTION_REQUIRED,
        "SYSTEM_OVERLOAD": TakeoverTrigger.SYSTEM_OVERLOAD,
        "APPROVAL_REQUIRED": TakeoverTrigger.APPROVAL_REQUIRED,
        "TIMEOUT_EXCEEDED": TakeoverTrigger.TIMEOUT_EXCEEDED,
    }

    trigger = trigger_mapping.get(request.trigger.upper())
    if not trigger:
        raise HTTPException(
            status_code=400, detail=f"Invalid trigger: {request.trigger}"
        )

    # Convert priority string to TaskPriority
    priority_mapping = {
        "LOW": TaskPriority.LOW,
        "MEDIUM": TaskPriority.MEDIUM,
        "HIGH": TaskPriority.HIGH,
        "CRITICAL": TaskPriority.CRITICAL,
    }

    priority = priority_mapping.get(request.priority.upper(), TaskPriority.HIGH)

    request_id = await takeover_manager.request_takeover(
        trigger=trigger,
        reason=request.reason,
        requesting_agent=request.requesting_agent,
        affected_tasks=request.affected_tasks,
        priority=priority,
        timeout_minutes=request.timeout_minutes,
        auto_approve=request.auto_approve,
    )

    logger.info("Takeover requested: %s", request_id)
    return {"success": True, "request_id": request_id}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve_takeover",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.post("/takeover/{request_id}/approve")
async def approve_takeover(
    request_id: str,
    approval: TakeoverApprovalRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Approve a takeover request and start session

    Issue #744: Requires admin authentication.
    """
    try:
        session_id = await takeover_manager.approve_takeover(
            request_id=request_id,
            human_operator=approval.human_operator,
            takeover_scope=approval.takeover_scope,
        )

        logger.info("Takeover approved: %s -> %s", request_id, session_id)
        return {"success": True, "session_id": session_id}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_takeover_action",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.post("/takeover/sessions/{session_id}/action")
async def execute_takeover_action(
    session_id: str,
    action: TakeoverActionRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Execute an action during a takeover session

    Issue #744: Requires admin authentication.
    """
    try:
        result = await takeover_manager.execute_takeover_action(
            session_id=session_id,
            action_type=action.action_type,
            action_data=action.action_data,
        )

        logger.info(
            f"Takeover action executed: {action.action_type} in session {session_id}"
        )
        return {"success": True, "result": result}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="pause_takeover_session",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.post("/takeover/sessions/{session_id}/pause")
async def pause_takeover_session(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Pause an active takeover session

    Issue #744: Requires admin authentication.
    """
    success = await takeover_manager.pause_takeover_session(session_id)
    if success:
        return {"success": True, "session_id": session_id, "status": "paused"}
    else:
        raise HTTPException(status_code=404, detail="Session not found or not pausable")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resume_takeover_session",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.post("/takeover/sessions/{session_id}/resume")
async def resume_takeover_session(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Resume a paused takeover session

    Issue #744: Requires admin authentication.
    """
    success = await takeover_manager.resume_takeover_session(session_id)
    if success:
        return {"success": True, "session_id": session_id, "status": "active"}
    else:
        raise HTTPException(
            status_code=404, detail="Session not found or not resumable"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="complete_takeover_session",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.post("/takeover/sessions/{session_id}/complete")
async def complete_takeover_session(
    session_id: str,
    completion_data: Metadata,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Complete a takeover session and return control

    Issue #744: Requires admin authentication.
    """
    success = await takeover_manager.complete_takeover_session(
        session_id=session_id,
        resolution=completion_data.get("resolution", "Session completed"),
        handback_notes=completion_data.get("handback_notes"),
    )

    if success:
        return {"success": True, "session_id": session_id, "status": "completed"}
    else:
        raise HTTPException(status_code=404, detail="Session not found")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pending_takeovers",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.get("/takeover/pending")
async def get_pending_takeovers(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get all pending takeover requests

    Issue #744: Requires admin authentication.
    """
    pending = takeover_manager.get_pending_requests()
    return {"pending_requests": pending, "count": len(pending)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_active_takeovers",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.get("/takeover/active")
async def get_active_takeovers(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get all active takeover sessions

    Issue #744: Requires admin authentication.
    """
    active = takeover_manager.get_active_sessions()
    return {"active_sessions": active, "count": len(active)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_takeover_status",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.get("/takeover/status")
async def get_takeover_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get takeover system status

    Issue #744: Requires admin authentication.
    """
    status = takeover_manager.get_system_status()
    return status


# System Monitoring and Control
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_status",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.get("/system/status", response_model=SystemMonitoringResponse)
async def get_system_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get comprehensive system monitoring status

    Issue #744: Requires admin authentication.
    """
    # Get resource usage
    import psutil

    resource_usage = {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage("/").percent,
        "process_count": len(psutil.pids()),
        "load_average": psutil.getloadavg() if hasattr(psutil, "getloadavg") else None,
    }

    # Get streaming sessions
    streaming_sessions = desktop_streaming.vnc_manager.list_active_sessions()

    # Get takeover data
    pending_takeovers = takeover_manager.get_pending_requests()
    active_takeovers = takeover_manager.get_active_sessions()
    system_status = {
        "status": "healthy",
        "timestamp": psutil.boot_time(),
        "uptime_seconds": psutil.boot_time(),
        "streaming_capabilities": desktop_streaming.get_system_capabilities(),
    }

    response = SystemMonitoringResponse(
        system_status=system_status,
        active_sessions=streaming_sessions,
        pending_takeovers=pending_takeovers,
        active_takeovers=active_takeovers,
        resource_usage=resource_usage,
    )

    return response


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="emergency_system_stop",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.post("/system/emergency-stop")
async def emergency_system_stop(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Emergency stop for all autonomous operations

    Issue #744: Requires admin authentication.
    """
    # Request emergency takeover
    request_id = await takeover_manager.request_takeover(
        trigger=TakeoverTrigger.CRITICAL_ERROR,
        reason="Emergency stop activated",
        requesting_agent="emergency_system",
        priority=TaskPriority.CRITICAL,
        auto_approve=True,
    )

    logger.warning("Emergency stop activated: %s", request_id)
    return {
        "success": True,
        "message": "Emergency stop activated",
        "takeover_request_id": request_id,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_health",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.get("/system/health")
async def get_system_health(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Quick health check endpoint

    Issue #744: Requires admin authentication.
    """
    try:
        health_status = {
            "status": "healthy",
            "desktop_streaming_available": desktop_streaming.vnc_manager.vnc_available,
            "novnc_available": desktop_streaming.vnc_manager.novnc_available,
            "active_streaming_sessions": len(
                desktop_streaming.vnc_manager.active_sessions
            ),
            "pending_takeovers": len(takeover_manager.pending_requests),
            "active_takeovers": len(takeover_manager.active_sessions),
            "paused_tasks": len(takeover_manager.paused_tasks),
        }

        return health_status

    except Exception as e:
        logger.error("Health check failed: %s", e)
        return {"status": "unhealthy", "error": str(e)}


# WebSocket endpoint for real-time monitoring
@router.websocket("/ws/monitoring")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="monitoring_websocket",
    error_code_prefix="ADVANCED_CONTROL",
)
async def monitoring_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time system monitoring"""
    await websocket.accept()
    logger.info("Monitoring WebSocket client connected")

    try:
        while True:
            # Send periodic system updates
            try:
                health_data = await get_system_health()
                await websocket.send_json(
                    {"type": "system_health", "data": health_data}
                )

                # Wait for next update cycle
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("Error in monitoring WebSocket: %s", e)
                await websocket.send_json({"type": "error", "message": str(e)})
                break

    except WebSocketDisconnect:
        logger.info("Monitoring WebSocket client disconnected")
    finally:
        try:
            await websocket.close()
        except Exception as e:
            logger.debug("WebSocket cleanup on disconnect: %s", e)


# WebSocket handler for desktop streaming
@router.websocket("/ws/desktop/{session_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="desktop_streaming_websocket",
    error_code_prefix="ADVANCED_CONTROL",
)
async def desktop_streaming_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for desktop streaming control"""
    await websocket.accept()

    try:
        # Use the desktop streaming manager's WebSocket handler
        await desktop_streaming.handle_websocket_client(
            websocket, f"/ws/desktop/{session_id}"
        )
    except WebSocketDisconnect:
        logger.info("Desktop streaming WebSocket client disconnected: %s", session_id)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="advanced_control_info",
    error_code_prefix="ADVANCED_CONTROL",
)
@router.get("/")
async def advanced_control_info(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get information about advanced control capabilities

    Issue #744: Requires admin authentication.
    """
    return {
        "name": "Advanced Control Interface",
        "version": "1.0.0",
        "features": [
            "Desktop streaming with NoVNC",
            "Human-in-the-loop takeover management",
            "Real-time system monitoring",
            "WebSocket-based control interfaces",
            "Emergency stop capabilities",
        ],
        "endpoints": {
            "streaming": "/api/control/streaming/",
            "takeover": "/api/control/takeover/",
            "system": "/api/control/system/",
            "websockets": {
                "monitoring": "/api/control/ws/monitoring",
                "desktop": "/api/control/ws/desktop/{session_id}",
            },
        },
    }
