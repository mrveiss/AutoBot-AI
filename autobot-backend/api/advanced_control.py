# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Advanced Control API for AutoBot Phase 8
Provides monitoring, desktop streaming, and takeover management endpoints
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from api.schemas_system import (
    StreamingSessionRequest,
    StreamingSessionResponse,
    SystemMonitoringResponse,
    TakeoverActionRequest,
    TakeoverApprovalRequest,
    TakeoverRequest,
)
from api.schemas_workflows import (
    AdvancedControlActiveTakeoversListResponse,
    AdvancedControlEmergencyStopResponse,
    AdvancedControlHealthResponse,
    AdvancedControlInfoResponse,
    AdvancedControlPendingTakeoversListResponse,
    AdvancedControlStreamingCapabilitiesResponse,
    AdvancedControlStreamingSessionListResponse,
    AdvancedControlStreamingTerminateResponse,
    AdvancedControlTakeoverActionResponse,
    AdvancedControlTakeoverApproveResponse,
    AdvancedControlTakeoverRequestResponse,
    AdvancedControlTakeoverSessionStatusResponse,
    AdvancedControlTakeoverSystemStatusResponse,
)
from api.ws_security import enforce_ws_admin, enforce_ws_origin
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.error_constants import ERR_SESSION_NOT_FOUND
from constants.threshold_constants import TimingConstants
from desktop_streaming_manager import get_desktop_streaming
from memory import TaskPriority  # canonical enum (#10626)
from metrics.system_monitor import evaluate_resource_thresholds
from takeover_manager import TakeoverTrigger, get_takeover_manager
from task_execution_tracker import get_task_tracker
from type_defs.common import Metadata

logger = get_logger(__name__)
router = APIRouter(tags=["advanced_control"])

# Map the resource classifier's verdict to this control plane's health vocabulary
# (#12243). "warning" (approaching a threshold) is a soft degrade; "critical"
# (over a threshold) is unhealthy.
_RESOURCE_STATUS_TO_HEALTH = {"ok": "healthy", "warning": "degraded", "critical": "unhealthy"}


# Desktop Streaming Endpoints
@router.post("/streaming/create", response_model=StreamingSessionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_streaming_session",
    error_code_prefix="ADVANCED_CONTROL",
)
async def create_streaming_session(
    request: StreamingSessionRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Create a new desktop streaming session

    Issue #744: Requires admin authentication.
    """
    async with get_task_tracker().track_task(
        "Create Desktop Streaming Session",
        f"Creating streaming session for user {request.user_id}",
        agent_type="advanced_control",
        priority=TaskPriority.HIGH,
        inputs={"user_id": request.user_id, "resolution": request.resolution},
    ) as task_context:
        session_config = {"resolution": request.resolution, "depth": request.depth}

        result = await get_desktop_streaming().create_streaming_session(
            user_id=request.user_id, session_config=session_config
        )

        response = StreamingSessionResponse(**result)
        task_context.set_outputs({"session_id": response.session_id})

        logger.info("Desktop streaming session created: %s", response.session_id)
        return response


@router.delete("/streaming/{session_id}", response_model=AdvancedControlStreamingTerminateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="terminate_streaming_session",
    error_code_prefix="ADVANCED_CONTROL",
)
async def terminate_streaming_session(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Terminate a desktop streaming session

    Issue #744: Requires admin authentication.
    """
    success = await get_desktop_streaming().terminate_streaming_session(session_id)
    if success:
        logger.info("Desktop streaming session terminated: %s", session_id)
        return {"success": True, "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)


@router.get("/streaming/sessions", response_model=AdvancedControlStreamingSessionListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_streaming_sessions",
    error_code_prefix="ADVANCED_CONTROL",
)
async def list_streaming_sessions(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    List all active streaming sessions

    Issue #744: Requires admin authentication.
    """
    sessions = get_desktop_streaming().vnc_manager.list_active_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/streaming/capabilities", response_model=AdvancedControlStreamingCapabilitiesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_streaming_capabilities",
    error_code_prefix="ADVANCED_CONTROL",
)
async def get_streaming_capabilities(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get desktop streaming system capabilities

    Issue #744: Requires admin authentication.
    """
    capabilities = get_desktop_streaming().get_system_capabilities()
    return capabilities


# Takeover Management Endpoints
@router.post("/takeover/request", response_model=AdvancedControlTakeoverRequestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="request_takeover",
    error_code_prefix="ADVANCED_CONTROL",
)
async def request_takeover(
    request: TakeoverRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Request human takeover of autonomous operations

    Issue #744: Requires admin authentication.
    """
    # Convert request strings to enums via direct name lookup so each enum is the
    # single source of truth (#12208 — the old hand-maintained maps mirrored every
    # member by hand and silently dropped any new one, rejecting a valid trigger
    # with a 400). Enum member names are the UPPER strings the client sends.
    try:
        trigger = TakeoverTrigger[request.trigger.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid trigger: {request.trigger}") from None

    try:
        priority = TaskPriority[request.priority.upper()]
    except KeyError:
        priority = TaskPriority.HIGH  # preserve current default-on-unknown behaviour

    request_id = await get_takeover_manager().request_takeover(
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


@router.post("/takeover/{request_id}/approve", response_model=AdvancedControlTakeoverApproveResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve_takeover",
    error_code_prefix="ADVANCED_CONTROL",
)
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
        session_id = await get_takeover_manager().approve_takeover(
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


@router.post("/takeover/sessions/{session_id}/action", response_model=AdvancedControlTakeoverActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_takeover_action",
    error_code_prefix="ADVANCED_CONTROL",
)
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
        result = await get_takeover_manager().execute_takeover_action(
            session_id=session_id,
            action_type=action.action_type,
            action_data=action.action_data,
        )

        logger.info(f"Takeover action executed: {action.action_type} in session {session_id}")
        return {"success": True, "result": result}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/takeover/sessions/{session_id}/pause", response_model=AdvancedControlTakeoverSessionStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="pause_takeover_session",
    error_code_prefix="ADVANCED_CONTROL",
)
async def pause_takeover_session(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Pause an active takeover session

    Issue #744: Requires admin authentication.
    """
    success = await get_takeover_manager().pause_takeover_session(session_id)
    if success:
        return {"success": True, "session_id": session_id, "status": "paused"}
    else:
        raise HTTPException(status_code=404, detail="Session not found or not pausable")


@router.post("/takeover/sessions/{session_id}/resume", response_model=AdvancedControlTakeoverSessionStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resume_takeover_session",
    error_code_prefix="ADVANCED_CONTROL",
)
async def resume_takeover_session(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Resume a paused takeover session

    Issue #744: Requires admin authentication.
    """
    success = await get_takeover_manager().resume_takeover_session(session_id)
    if success:
        return {"success": True, "session_id": session_id, "status": "active"}
    else:
        raise HTTPException(status_code=404, detail="Session not found or not resumable")


@router.post("/takeover/sessions/{session_id}/complete", response_model=AdvancedControlTakeoverSessionStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="complete_takeover_session",
    error_code_prefix="ADVANCED_CONTROL",
)
async def complete_takeover_session(
    session_id: str,
    completion_data: Metadata,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Complete a takeover session and return control

    Issue #744: Requires admin authentication.
    """
    success = await get_takeover_manager().complete_takeover_session(
        session_id=session_id,
        resolution=completion_data.get("resolution", "Session completed"),
        handback_notes=completion_data.get("handback_notes"),
    )

    if success:
        return {"success": True, "session_id": session_id, "status": "completed"}
    else:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)


@router.get("/takeover/pending", response_model=AdvancedControlPendingTakeoversListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pending_takeovers",
    error_code_prefix="ADVANCED_CONTROL",
)
async def get_pending_takeovers(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get all pending takeover requests

    Issue #744: Requires admin authentication.
    """
    pending = await get_takeover_manager().get_pending_requests()
    return {"pending_requests": pending, "count": len(pending)}


@router.get("/takeover/active", response_model=AdvancedControlActiveTakeoversListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_active_takeovers",
    error_code_prefix="ADVANCED_CONTROL",
)
async def get_active_takeovers(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get all active takeover sessions

    Issue #744: Requires admin authentication.
    """
    active = await get_takeover_manager().get_active_sessions()
    return {"active_sessions": active, "count": len(active)}


@router.get("/takeover/status", response_model=AdvancedControlTakeoverSystemStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_takeover_status",
    error_code_prefix="ADVANCED_CONTROL",
)
async def get_takeover_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get takeover system status

    Issue #744: Requires admin authentication.
    """
    status = await get_takeover_manager().get_system_status()
    return status


# System Monitoring and Control
@router.get("/system/status", response_model=SystemMonitoringResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_status",
    error_code_prefix="ADVANCED_CONTROL",
)
async def get_system_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get comprehensive system monitoring status

    Issue #744: Requires admin authentication.
    """
    # Get resource usage
    import time

    import psutil

    resource_usage = {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage("/").percent,
        "process_count": len(psutil.pids()),
        "load_average": psutil.getloadavg() if hasattr(psutil, "getloadavg") else None,
    }

    # Get streaming sessions
    streaming_sessions = get_desktop_streaming().vnc_manager.list_active_sessions()

    # Get takeover data
    pending_takeovers = await get_takeover_manager().get_pending_requests()
    active_takeovers = await get_takeover_manager().get_active_sessions()
    # #12177: both fields were mistakenly set to psutil.boot_time() (an absolute
    # boot epoch). timestamp is when this snapshot was taken; uptime_seconds is a
    # duration (now - boot).
    now = time.time()
    # #12243: derive status from the metrics this response actually reports rather
    # than a hardcoded "healthy". Grade the already-collected resource_usage against
    # the canonical thresholds; if desktop streaming (this panel's core capability)
    # is unavailable, that is at least a degraded control plane.
    resource_verdict = evaluate_resource_thresholds(
        {
            "cpu_percent": resource_usage["cpu_percent"],
            "memory_percent": resource_usage["memory_percent"],
            "disk_percent": resource_usage["disk_usage"],
        }
    )
    status = _RESOURCE_STATUS_TO_HEALTH[resource_verdict["status"]]
    streaming_available = bool(get_desktop_streaming().vnc_manager.vnc_available)
    if not streaming_available and status == "healthy":
        status = "degraded"

    system_status = {
        "status": status,
        "timestamp": now,
        "uptime_seconds": now - psutil.boot_time(),
        "streaming_capabilities": get_desktop_streaming().get_system_capabilities(),
        "resource_alerts": resource_verdict["critical_alerts"] + resource_verdict["warnings"],
    }

    response = SystemMonitoringResponse(
        system_status=system_status,
        active_sessions=streaming_sessions,
        pending_takeovers=pending_takeovers,
        active_takeovers=active_takeovers,
        resource_usage=resource_usage,
    )

    return response


@router.post("/system/emergency-stop", response_model=AdvancedControlEmergencyStopResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="emergency_system_stop",
    error_code_prefix="ADVANCED_CONTROL",
)
async def emergency_system_stop(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Emergency stop for all autonomous operations

    Issue #744: Requires admin authentication.
    """
    # Request emergency takeover
    request_id = await get_takeover_manager().request_takeover(
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


@router.get("/system/health", response_model=AdvancedControlHealthResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_health",
    error_code_prefix="ADVANCED_CONTROL",
)
async def get_system_health(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Quick health check endpoint

    Issue #744: Requires admin authentication.
    """
    # C1: attributes removed in #11639 Redis refactor; use async helpers instead.
    try:
        dsm = get_desktop_streaming()
        tm = get_takeover_manager()
        # #12243: reflect the real subsystem state instead of a constant "healthy".
        # Desktop streaming (VNC) is this control plane's core capability — when it
        # is unavailable the panel is degraded, not healthy.
        streaming_available = dsm.vnc_manager.vnc_available
        health_status = {
            "status": "healthy" if streaming_available else "degraded",
            "desktop_streaming_available": streaming_available,
            "novnc_available": dsm.vnc_manager.novnc_available,
            "active_streaming_sessions": len(dsm.vnc_manager.active_sessions),
            "pending_takeovers": len(await tm.get_pending_requests()),
            "active_takeovers": len(await tm.get_active_sessions()),
            "paused_tasks": await tm._paused_count(),
        }

        return health_status

    except Exception as e:
        logger.error("Health check failed: %s", e)
        return {"status": "unhealthy", "error": "Internal server error"}


# WebSocket endpoint for real-time monitoring
@router.websocket("/ws/monitoring")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="monitoring_websocket",
    error_code_prefix="ADVANCED_CONTROL",
)
async def monitoring_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time system monitoring"""
    if not await enforce_ws_origin(websocket):
        return
    if not await enforce_ws_admin(websocket):
        return
    await websocket.accept()
    logger.info("Monitoring WebSocket client connected")

    try:
        while True:
            # Send periodic system updates
            try:
                health_data = await get_system_health()
                await websocket.send_json({"type": "system_health", "data": health_data})

                # Wait for next update cycle
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("Error in monitoring WebSocket: %s", e)
                await websocket.send_json({"type": "error", "message": "Operation failed"})
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
    if not await enforce_ws_origin(websocket):
        return
    if not await enforce_ws_admin(websocket):
        return
    await websocket.accept()

    try:
        # Use the desktop streaming manager's WebSocket handler
        await get_desktop_streaming().handle_websocket_client(websocket, f"/ws/desktop/{session_id}")
    except WebSocketDisconnect:
        logger.info("Desktop streaming WebSocket client disconnected: %s", session_id)


@router.get("/", response_model=AdvancedControlInfoResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="advanced_control_info",
    error_code_prefix="ADVANCED_CONTROL",
)
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
            "streaming": "/api/advanced-control/streaming/",
            "takeover": "/api/advanced-control/takeover/",
            "system": "/api/advanced-control/system/",
            "websockets": {
                "monitoring": "/api/advanced-control/ws/monitoring",
                "desktop": "/api/advanced-control/ws/desktop/{session_id}",
            },
        },
    }
