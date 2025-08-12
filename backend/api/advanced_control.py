"""
Advanced Control API for AutoBot Phase 8
Provides monitoring, desktop streaming, and takeover management endpoints
"""

import asyncio
import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request
from pydantic import BaseModel

from src.desktop_streaming_manager import desktop_streaming
from src.takeover_manager import takeover_manager, TakeoverTrigger
from src.enhanced_memory_manager import TaskPriority
from src.task_execution_tracker import task_tracker

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
    takeover_scope: Optional[Dict[str, Any]] = None


class TakeoverActionRequest(BaseModel):
    action_type: str
    action_data: Dict[str, Any]


class SystemMonitoringResponse(BaseModel):
    system_status: Dict[str, Any]
    active_sessions: List[Dict[str, Any]]
    pending_takeovers: List[Dict[str, Any]]
    active_takeovers: List[Dict[str, Any]]
    resource_usage: Dict[str, Any]


# Desktop Streaming Endpoints
@router.post("/streaming/create", response_model=StreamingSessionResponse)
async def create_streaming_session(request: StreamingSessionRequest):
    """Create a new desktop streaming session"""
    try:
        async with task_tracker.track_task(
            "Create Desktop Streaming Session",
            f"Creating streaming session for user {request.user_id}",
            agent_type="advanced_control",
            priority=TaskPriority.HIGH,
            inputs={"user_id": request.user_id, "resolution": request.resolution}
        ) as task_context:
            
            session_config = {
                "resolution": request.resolution,
                "depth": request.depth
            }
            
            result = await desktop_streaming.create_streaming_session(
                user_id=request.user_id,
                session_config=session_config
            )
            
            response = StreamingSessionResponse(**result)
            task_context.set_outputs({"session_id": response.session_id})
            
            logger.info(f"Desktop streaming session created: {response.session_id}")
            return response
            
    except Exception as e:
        logger.error(f"Failed to create streaming session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/streaming/{session_id}")
async def terminate_streaming_session(session_id: str):
    """Terminate a desktop streaming session"""
    try:
        success = await desktop_streaming.terminate_streaming_session(session_id)
        if success:
            logger.info(f"Desktop streaming session terminated: {session_id}")
            return {"success": True, "session_id": session_id}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        logger.error(f"Failed to terminate streaming session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/streaming/sessions")
async def list_streaming_sessions():
    """List all active streaming sessions"""
    try:
        sessions = desktop_streaming.vnc_manager.list_active_sessions()
        return {"sessions": sessions, "count": len(sessions)}
    except Exception as e:
        logger.error(f"Failed to list streaming sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/streaming/capabilities")
async def get_streaming_capabilities():
    """Get desktop streaming system capabilities"""
    try:
        capabilities = desktop_streaming.get_system_capabilities()
        return capabilities
    except Exception as e:
        logger.error(f"Failed to get streaming capabilities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Takeover Management Endpoints
@router.post("/takeover/request")
async def request_takeover(request: TakeoverRequest):
    """Request human takeover of autonomous operations"""
    try:
        # Convert string enum to TakeoverTrigger
        trigger_mapping = {
            "MANUAL_REQUEST": TakeoverTrigger.MANUAL_REQUEST,
            "CRITICAL_ERROR": TakeoverTrigger.CRITICAL_ERROR,
            "SECURITY_CONCERN": TakeoverTrigger.SECURITY_CONCERN,
            "USER_INTERVENTION_REQUIRED": TakeoverTrigger.USER_INTERVENTION_REQUIRED,
            "SYSTEM_OVERLOAD": TakeoverTrigger.SYSTEM_OVERLOAD,
            "APPROVAL_REQUIRED": TakeoverTrigger.APPROVAL_REQUIRED,
            "TIMEOUT_EXCEEDED": TakeoverTrigger.TIMEOUT_EXCEEDED
        }
        
        trigger = trigger_mapping.get(request.trigger.upper())
        if not trigger:
            raise HTTPException(status_code=400, detail=f"Invalid trigger: {request.trigger}")
        
        # Convert priority string to TaskPriority
        priority_mapping = {
            "LOW": TaskPriority.LOW,
            "MEDIUM": TaskPriority.MEDIUM,
            "HIGH": TaskPriority.HIGH,
            "CRITICAL": TaskPriority.CRITICAL
        }
        
        priority = priority_mapping.get(request.priority.upper(), TaskPriority.HIGH)
        
        request_id = await takeover_manager.request_takeover(
            trigger=trigger,
            reason=request.reason,
            requesting_agent=request.requesting_agent,
            affected_tasks=request.affected_tasks,
            priority=priority,
            timeout_minutes=request.timeout_minutes,
            auto_approve=request.auto_approve
        )
        
        logger.info(f"Takeover requested: {request_id}")
        return {"success": True, "request_id": request_id}
        
    except Exception as e:
        logger.error(f"Failed to request takeover: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/takeover/{request_id}/approve")
async def approve_takeover(request_id: str, approval: TakeoverApprovalRequest):
    """Approve a takeover request and start session"""
    try:
        session_id = await takeover_manager.approve_takeover(
            request_id=request_id,
            human_operator=approval.human_operator,
            takeover_scope=approval.takeover_scope
        )
        
        logger.info(f"Takeover approved: {request_id} -> {session_id}")
        return {"success": True, "session_id": session_id}
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to approve takeover: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/takeover/sessions/{session_id}/action")
async def execute_takeover_action(session_id: str, action: TakeoverActionRequest):
    """Execute an action during a takeover session"""
    try:
        result = await takeover_manager.execute_takeover_action(
            session_id=session_id,
            action_type=action.action_type,
            action_data=action.action_data
        )
        
        logger.info(f"Takeover action executed: {action.action_type} in session {session_id}")
        return {"success": True, "result": result}
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to execute takeover action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/takeover/sessions/{session_id}/pause")
async def pause_takeover_session(session_id: str):
    """Pause an active takeover session"""
    try:
        success = await takeover_manager.pause_takeover_session(session_id)
        if success:
            return {"success": True, "session_id": session_id, "status": "paused"}
        else:
            raise HTTPException(status_code=404, detail="Session not found or not pausable")
    except Exception as e:
        logger.error(f"Failed to pause takeover session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/takeover/sessions/{session_id}/resume")
async def resume_takeover_session(session_id: str):
    """Resume a paused takeover session"""
    try:
        success = await takeover_manager.resume_takeover_session(session_id)
        if success:
            return {"success": True, "session_id": session_id, "status": "active"}
        else:
            raise HTTPException(status_code=404, detail="Session not found or not resumable")
    except Exception as e:
        logger.error(f"Failed to resume takeover session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/takeover/sessions/{session_id}/complete")
async def complete_takeover_session(
    session_id: str, 
    completion_data: Dict[str, Any]
):
    """Complete a takeover session and return control"""
    try:
        success = await takeover_manager.complete_takeover_session(
            session_id=session_id,
            resolution=completion_data.get("resolution", "Session completed"),
            handback_notes=completion_data.get("handback_notes")
        )
        
        if success:
            return {"success": True, "session_id": session_id, "status": "completed"}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        logger.error(f"Failed to complete takeover session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/takeover/pending")
async def get_pending_takeovers():
    """Get all pending takeover requests"""
    try:
        pending = takeover_manager.get_pending_requests()
        return {"pending_requests": pending, "count": len(pending)}
    except Exception as e:
        logger.error(f"Failed to get pending takeovers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/takeover/active")
async def get_active_takeovers():
    """Get all active takeover sessions"""
    try:
        active = takeover_manager.get_active_sessions()
        return {"active_sessions": active, "count": len(active)}
    except Exception as e:
        logger.error(f"Failed to get active takeovers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/takeover/status")
async def get_takeover_status():
    """Get takeover system status"""
    try:
        status = takeover_manager.get_system_status()
        return status
    except Exception as e:
        logger.error(f"Failed to get takeover status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# System Monitoring and Control
@router.get("/system/status", response_model=SystemMonitoringResponse)
async def get_system_status():
    """Get comprehensive system monitoring status"""
    try:
        # Get resource usage
        import psutil
        
        resource_usage = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "process_count": len(psutil.pids()),
            "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
        }
        
        # Get streaming sessions
        streaming_sessions = desktop_streaming.vnc_manager.list_active_sessions()
        
        # Get takeover data
        pending_takeovers = takeover_manager.get_pending_requests()
        active_takeovers = takeover_manager.get_active_sessions()
        takeover_status = takeover_manager.get_system_status()
        
        system_status = {
            "status": "healthy",
            "timestamp": psutil.boot_time(),
            "uptime_seconds": psutil.boot_time(),
            "streaming_capabilities": desktop_streaming.get_system_capabilities()
        }
        
        response = SystemMonitoringResponse(
            system_status=system_status,
            active_sessions=streaming_sessions,
            pending_takeovers=pending_takeovers,
            active_takeovers=active_takeovers,
            resource_usage=resource_usage
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system/emergency-stop")
async def emergency_system_stop():
    """Emergency stop for all autonomous operations"""
    try:
        # Request emergency takeover
        request_id = await takeover_manager.request_takeover(
            trigger=TakeoverTrigger.CRITICAL_ERROR,
            reason="Emergency stop activated",
            requesting_agent="emergency_system",
            priority=TaskPriority.CRITICAL,
            auto_approve=True
        )
        
        logger.warning(f"Emergency stop activated: {request_id}")
        return {
            "success": True, 
            "message": "Emergency stop activated",
            "takeover_request_id": request_id
        }
        
    except Exception as e:
        logger.error(f"Emergency stop failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/health")
async def get_system_health():
    """Quick health check endpoint"""
    try:
        health_status = {
            "status": "healthy",
            "desktop_streaming_available": desktop_streaming.vnc_manager.vnc_available,
            "novnc_available": desktop_streaming.vnc_manager.novnc_available,
            "active_streaming_sessions": len(desktop_streaming.vnc_manager.active_sessions),
            "pending_takeovers": len(takeover_manager.pending_requests),
            "active_takeovers": len(takeover_manager.active_sessions),
            "paused_tasks": len(takeover_manager.paused_tasks)
        }
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# WebSocket endpoint for real-time monitoring
@router.websocket("/ws/monitoring")
async def monitoring_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time system monitoring"""
    await websocket.accept()
    logger.info("Monitoring WebSocket client connected")
    
    try:
        while True:
            # Send periodic system updates
            try:
                health_data = await get_system_health()
                await websocket.send_json({
                    "type": "system_health",
                    "data": health_data
                })
                
                # Wait for next update cycle
                await asyncio.sleep(5)
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in monitoring WebSocket: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
                break
                
    except WebSocketDisconnect:
        logger.info("Monitoring WebSocket client disconnected")
    except Exception as e:
        logger.error(f"Monitoring WebSocket error: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass


# WebSocket handler for desktop streaming
@router.websocket("/ws/desktop/{session_id}")
async def desktop_streaming_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for desktop streaming control"""
    await websocket.accept()
    
    try:
        # Use the desktop streaming manager's WebSocket handler
        await desktop_streaming.handle_websocket_client(
            websocket, 
            f"/ws/desktop/{session_id}"
        )
    except WebSocketDisconnect:
        logger.info(f"Desktop streaming WebSocket client disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Desktop streaming WebSocket error: {e}")


@router.get("/")
async def advanced_control_info():
    """Get information about advanced control capabilities"""
    return {
        "name": "Advanced Control Interface",
        "version": "1.0.0",
        "features": [
            "Desktop streaming with NoVNC",
            "Human-in-the-loop takeover management", 
            "Real-time system monitoring",
            "WebSocket-based control interfaces",
            "Emergency stop capabilities"
        ],
        "endpoints": {
            "streaming": "/api/control/streaming/",
            "takeover": "/api/control/takeover/",
            "system": "/api/control/system/",
            "websockets": {
                "monitoring": "/api/control/ws/monitoring",
                "desktop": "/api/control/ws/desktop/{session_id}"
            }
        }
    }