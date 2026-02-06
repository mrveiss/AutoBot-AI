# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Startup Status API
Provides friendly startup messages and status updates for the frontend
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["startup", "status"])

# Thread lock for synchronous access to startup_state
import threading

_startup_lock = threading.Lock()

# Async lock for WebSocket client access
_ws_lock = asyncio.Lock()


class StartupPhase(Enum):
    INITIALIZING = "initializing"
    STARTING_SERVICES = "starting_services"
    CONNECTING_BACKEND = "connecting_backend"
    LOADING_KNOWLEDGE = "loading_knowledge"
    READY = "ready"
    ERROR = "error"


class StartupMessage(BaseModel):
    """Startup status message"""

    phase: StartupPhase
    message: str
    progress: int  # 0-100
    timestamp: str
    icon: str
    details: Optional[str] = None


# Global startup state
startup_state = {
    "current_phase": StartupPhase.INITIALIZING,
    "progress": 0,
    "messages": [],
    "start_time": time.time(),
    "websocket_clients": set(),
}


def add_startup_message(
    phase: StartupPhase,
    message: str,
    progress: int,
    icon: str = "🚀",
    details: str = None,
):
    """Add a startup message and broadcast to connected clients"""
    msg = StartupMessage(
        phase=phase,
        message=message,
        progress=progress,
        timestamp=datetime.now().isoformat(),
        icon=icon,
        details=details,
    )

    with _startup_lock:
        startup_state["current_phase"] = phase
        startup_state["progress"] = progress
        startup_state["messages"].append(msg.dict())

        # Keep only last 20 messages
        if len(startup_state["messages"]) > 20:
            startup_state["messages"] = startup_state["messages"][-20:]

    logger.info("Startup: [%s] %s (%s%%)", phase.value, message, progress)

    # Broadcast to connected WebSocket clients (only if event loop is running)
    try:
        # Check if event loop is running - get_running_loop raises RuntimeError if not
        asyncio.get_running_loop()
        asyncio.create_task(broadcast_startup_message(msg))
    except RuntimeError:
        # No running event loop - this is expected during module import
        # The message is still stored and will be sent when clients connect
        logger.debug("No running event loop, message queued for later broadcast")


async def broadcast_startup_message(message: StartupMessage):
    """Broadcast startup message to all connected WebSocket clients"""
    async with _ws_lock:
        if not startup_state["websocket_clients"]:
            return

        message_json = json.dumps(message.dict())
        disconnected = []

        for websocket in startup_state["websocket_clients"]:
            try:
                await websocket.send_text(message_json)
            except Exception:
                disconnected.append(websocket)

        # Remove disconnected clients
        for ws in disconnected:
            startup_state["websocket_clients"].discard(ws)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_startup_status",
    error_code_prefix="STARTUP",
)
@router.get("/status")
async def get_startup_status():
    """Get current startup status"""
    with _startup_lock:
        elapsed_time = time.time() - startup_state["start_time"]
        current_phase = startup_state["current_phase"]
        progress = startup_state["progress"]
        messages = list(startup_state["messages"][-10:])  # Last 10 messages

    return {
        "current_phase": current_phase.value,
        "progress": progress,
        "messages": messages,
        "elapsed_time": round(elapsed_time, 1),
        "is_ready": current_phase == StartupPhase.READY,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="startup_websocket",
    error_code_prefix="STARTUP",
)
@router.websocket("/ws")
async def startup_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time startup messages"""
    await websocket.accept()

    async with _ws_lock:
        startup_state["websocket_clients"].add(websocket)

    try:
        # Send current status immediately
        current_status = await get_startup_status()
        await websocket.send_text(
            json.dumps({"type": "status", "data": current_status})
        )

        # Send recent messages (get copy under lock)
        with _startup_lock:
            recent_messages = list(startup_state["messages"][-5:])

        for message in recent_messages:
            await websocket.send_text(json.dumps({"type": "message", "data": message}))

        # Keep connection alive
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.error("Startup WebSocket error: %s", e)
    finally:
        async with _ws_lock:
            startup_state["websocket_clients"].discard(websocket)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_startup_phase",
    error_code_prefix="STARTUP",
)
@router.post("/phase")
async def update_startup_phase(
    phase: str, message: str, progress: int, icon: str = "🚀", details: str = None
):
    """Update startup phase (called by startup script or other services)"""
    try:
        phase_enum = StartupPhase(phase)
        add_startup_message(phase_enum, message, progress, icon, details)

        return {"success": True, "phase": phase, "progress": progress}
    except ValueError:
        return {"success": False, "error": f"Invalid phase: {phase}"}


# Initialize startup messages
def init_startup_messages():
    """Initialize startup sequence with welcome messages"""
    add_startup_message(
        StartupPhase.INITIALIZING,
        "🤖 Welcome to AutoBot!",
        0,
        "🤖",
        "Initializing the AutoBot intelligence system...",
    )

    add_startup_message(
        StartupPhase.INITIALIZING, "Preparing system components...", 5, "🔍"
    )


# Initialize on import - this provides initial messages immediately
init_startup_messages()


# Additional function to reset/clear startup state (useful for restarts)
def reset_startup_state():
    """Reset startup state for fresh restart"""
    with _startup_lock:
        startup_state["current_phase"] = StartupPhase.INITIALIZING
        startup_state["progress"] = 0
        startup_state["messages"] = []
        startup_state["start_time"] = time.time()
    # Don't clear websocket_clients as they might be connected
    init_startup_messages()
    logger.info("Startup state reset for new startup sequence")
