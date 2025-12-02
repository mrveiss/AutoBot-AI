# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Research Browser API
Handles browser automation for research tasks with user interaction support
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import aiofiles
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.constants.network_constants import NetworkConstants
from src.research_browser_manager import research_browser_manager
from src.unified_config_manager import UnifiedConfigManager
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Create singleton config instance
config = UnifiedConfigManager()

router = APIRouter()


class ResearchRequest(BaseModel):
    conversation_id: str
    url: str
    extract_content: bool = True


class SessionAction(BaseModel):
    session_id: str
    action: str  # "wait", "manual_intervention", "save_mhtml", "extract_content"
    timeout_seconds: Optional[int] = 300


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="health_check",
    error_code_prefix="RESEARCH_BROWSER",
)
@router.get("/health")
async def health_check():
    """Health check endpoint for research browser service"""
    # Check if browser manager is initialized
    status = "healthy" if research_browser_manager else "not_initialized"

    # Get browser service URL from config
    try:
        browser_service_url = config.get_service_url("browser_service")
    except Exception:
        browser_service_url = (
            f"http://localhost:{NetworkConstants.BROWSER_SERVICE_PORT}"
        )

    return {
        "status": status,
        "service": "research_browser",
        "browser_service_url": browser_service_url,
        "timestamp": datetime.now().isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="research_url",
    error_code_prefix="RESEARCH_BROWSER",
)
@router.post("/url")
async def research_url(request: ResearchRequest):
    """Research a URL with automatic fallbacks and interaction handling"""
    result = await research_browser_manager.research_url(
        request.conversation_id, request.url, request.extract_content
    )

    return JSONResponse(status_code=200, content=result)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="handle_session_action",
    error_code_prefix="RESEARCH_BROWSER",
)
@router.post("/session/action")
async def handle_session_action(request: SessionAction):
    """Handle actions on a research session"""
    session = research_browser_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = {"success": True, "session_id": request.session_id}

    if request.action == "wait":
        # Wait for user interaction to complete
        interaction_complete = await session.wait_for_user_interaction(
            request.timeout_seconds or 300
        )
        result["interaction_complete"] = interaction_complete
        result["status"] = session.status

    elif request.action == "manual_intervention":
        # User is taking over manually - just update status
        result["message"] = "Manual intervention acknowledged"
        result["browser_accessible"] = True
        result["current_url"] = session.current_url

    elif request.action == "save_mhtml":
        # Save current page as MHTML
        mhtml_path = await session.save_mhtml()
        if mhtml_path:
            result["mhtml_path"] = mhtml_path
            result["message"] = "Page saved as MHTML"
        else:
            result["success"] = False
            result["error"] = "Failed to save MHTML"

    elif request.action == "extract_content":
        # Extract content from current page
        content_result = await session.extract_content()
        result["content"] = content_result

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")

    return JSONResponse(status_code=200, content=result)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_status",
    error_code_prefix="RESEARCH_BROWSER",
)
@router.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Get the status of a research session"""
    session = research_browser_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return JSONResponse(
        status_code=200,
        content={
            "session_id": session_id,
            "conversation_id": session.conversation_id,
            "status": session.status,
            "current_url": session.current_url,
            "interaction_required": session.interaction_required,
            "interaction_message": session.interaction_message,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "mhtml_files_count": len(session.mhtml_files),
        },
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="download_mhtml",
    error_code_prefix="RESEARCH_BROWSER",
)
@router.get("/session/{session_id}/mhtml/{filename}")
async def download_mhtml(session_id: str, filename: str):
    """Download an MHTML file from a research session"""
    session = research_browser_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Find the MHTML file
    mhtml_path = None
    for path in session.mhtml_files:
        if filename in path:
            mhtml_path = path
            break

    if not mhtml_path or not os.path.exists(mhtml_path):
        raise HTTPException(status_code=404, detail="MHTML file not found")

    # Stream the file asynchronously
    async def generate():
        async with aiofiles.open(mhtml_path, "rb") as f:
            while chunk := await f.read(8192):
                yield chunk

    return StreamingResponse(
        generate(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_session",
    error_code_prefix="RESEARCH_BROWSER",
)
@router.delete("/session/{session_id}")
async def cleanup_session(session_id: str):
    """Clean up a research session"""
    await research_browser_manager.cleanup_session(session_id)

    return JSONResponse(
        status_code=200,
        content={"success": True, "message": f"Session {session_id} cleaned up"},
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_sessions",
    error_code_prefix="RESEARCH_BROWSER",
)
@router.get("/sessions")
async def list_sessions():
    """List all active research sessions"""
    sessions_info = []

    for session_id, session in research_browser_manager.sessions.items():
        sessions_info.append(
            {
                "session_id": session_id,
                "conversation_id": session.conversation_id,
                "status": session.status,
                "current_url": session.current_url,
                "interaction_required": session.interaction_required,
                "created_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat(),
            }
        )

    return JSONResponse(
        status_code=200,
        content={"sessions": sessions_info, "total_sessions": len(sessions_info)},
    )


class NavigationRequest(BaseModel):
    url: str


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="navigate_session",
    error_code_prefix="RESEARCH_BROWSER",
)
@router.post("/session/{session_id}/navigate")
async def navigate_session(session_id: str, request: NavigationRequest):
    """Navigate a research session to a specific URL"""
    session = research_browser_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await session.navigate_to(request.url)

    return JSONResponse(status_code=200, content=result)


# Browser integration endpoints for frontend
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_browser_info",
    error_code_prefix="RESEARCH_BROWSER",
)
@router.get("/browser/{session_id}")
async def get_browser_info(session_id: str):
    """Get browser information for frontend integration"""
    session = research_browser_manager.get_session(session_id)

    # Special handling for chat-browser - create default session if needed
    if not session and session_id == "chat-browser":
        logger.info("Creating default chat-browser session for frontend integration")
        # Create a default research session for chat integration
        session = research_browser_manager.create_session(
            conversation_id="default-chat",
            interaction_settings={
                "captcha": False,
                "cloudflare": False,
                "cookies": False,
                "js": False,
            },
        )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check if we have a Docker browser container available
    docker_browser_info = None
    try:
        # Try to detect Playwright container
        # Import centralized configuration with intelligent port detection
        from src.unified_config_manager import (
            PLAYWRIGHT_VNC_URL,
            get_vnc_direct_url,
        )

        # This would integrate with your existing browser setup
        docker_browser_info = {
            "available": True,
            "vnc_url": PLAYWRIGHT_VNC_URL.replace(
                "vnc.html", ""
            ),  # NoVNC web interface
            "direct_url": (
                get_vnc_direct_url()
            ),  # Intelligent VNC connection (5900 or 5901)
            "session_active": session.status == "active",
            "environment": "container" if await asyncio.to_thread(os.path.exists, "/.dockerenv") else "host",
        }
    except Exception:
        docker_browser_info = {"available": False}

    return JSONResponse(
        status_code=200,
        content={
            "session_id": session_id,
            "conversation_id": session.conversation_id,
            "status": session.status,
            "current_url": session.current_url,
            "interaction_required": session.interaction_required,
            "interaction_message": session.interaction_message,
            "docker_browser": docker_browser_info,
            "actions": [
                {
                    "action": "wait",
                    "label": "Wait for Interaction",
                    "description": "Wait for user to complete interaction",
                },
                {
                    "action": "manual_intervention",
                    "label": "Manual Control",
                    "description": "Take manual control of browser",
                },
                {
                    "action": "save_mhtml",
                    "label": "Save Page",
                    "description": "Save current page as MHTML backup",
                },
                {
                    "action": "extract_content",
                    "label": "Extract Content",
                    "description": "Extract text content from current page",
                },
            ],
        },
    )
