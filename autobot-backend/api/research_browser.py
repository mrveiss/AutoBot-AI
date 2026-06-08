# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Research Browser API
Handles browser automation for research tasks with user interaction support
"""

import asyncio
import os

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api.schemas_common import DataResponse
from api.schemas_workflows import (
    BrowserInfoData,
    BrowserResearchRequest,
    BrowserSessionActionData,
    BrowserSessionCleanupData,
    BrowserSessionListData,
    BrowserSessionStatusData,
    ChatBrowserSessionData,
    CreateChatBrowserRequest,
    NavigationRequest,
    SessionAction,
)
from api.system_health import ComponentHealth, register_health_probe
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from config.manager import get_config_manager
from constants.error_constants import ERR_SESSION_NOT_FOUND

logger = get_logger(__name__)

# Issue #1009: Graceful fallback when playwright is not installed
try:
    from research_browser_manager import get_research_browser_manager

    _BROWSER_AVAILABLE = True
except ImportError:
    get_research_browser_manager = None  # type: ignore[assignment]
    _BROWSER_AVAILABLE = False
    logger.warning("research_browser_manager unavailable (playwright not installed)")

config = get_config_manager()

router = APIRouter(
    dependencies=[Depends(check_admin_permission)],
)


def _require_browser():
    """Raise 503 if playwright/browser manager is not available (Issue #1009)."""
    if not _BROWSER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Research browser unavailable: playwright not installed",
        )


@register_health_probe("research_browser")
async def probe_research_browser(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for research_browser module.

    Lightweight check: inspect the module-level ``_BROWSER_AVAILABLE`` flag
    set at import time. ``down`` when playwright is not installed; otherwise
    ``ok``. Skips the manager call the handler performs.
    """
    try:
        if not _BROWSER_AVAILABLE:
            return ComponentHealth(
                name="research_browser",
                status="down",
                detail="playwright not installed",
            )
        return ComponentHealth(name="research_browser", status="ok")
    except Exception as exc:
        return ComponentHealth(
            name="research_browser",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


@router.post("/url", response_model=DataResponse[BrowserSessionStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="research_url",
    error_code_prefix="RESEARCH_BROWSER",
)
async def research_url(request: BrowserResearchRequest):
    """Research a URL with automatic fallbacks and interaction handling"""
    _require_browser()
    result = await get_research_browser_manager().research_url(
        request.conversation_id, request.url, request.extract_content
    )

    return JSONResponse(status_code=200, content=result)


@router.post("/session/action", response_model=DataResponse[BrowserSessionActionData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="handle_session_action",
    error_code_prefix="RESEARCH_BROWSER",
)
async def handle_session_action(request: SessionAction):
    """Handle actions on a research session"""
    _require_browser()
    session = get_research_browser_manager().get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    result = {"success": True, "session_id": request.session_id}

    if request.action == "wait":
        # Wait for user interaction to complete
        interaction_complete = await session.wait_for_user_interaction(request.timeout_seconds or 300)
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


@router.get("/session/{session_id}/status", response_model=DataResponse[BrowserSessionStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_status",
    error_code_prefix="RESEARCH_BROWSER",
)
async def get_session_status(session_id: str):
    """Get the status of a research session"""
    _require_browser()
    session = get_research_browser_manager().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

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


@router.get("/session/{session_id}/mhtml/{filename}", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="download_mhtml",
    error_code_prefix="RESEARCH_BROWSER",
)
async def download_mhtml(session_id: str, filename: str):
    """Download an MHTML file from a research session"""
    _require_browser()
    session = get_research_browser_manager().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    # Find the MHTML file
    mhtml_path = None
    for path in session.mhtml_files:
        if filename in path:
            mhtml_path = path
            break

    # Issue #358 - avoid blocking
    mhtml_exists = await asyncio.to_thread(os.path.exists, mhtml_path) if mhtml_path else False
    if not mhtml_path or not mhtml_exists:
        raise HTTPException(status_code=404, detail="MHTML file not found")

    # Stream the file asynchronously
    async def generate():
        """Generate file chunks for streaming response."""
        try:
            async with aiofiles.open(mhtml_path, "rb") as f:
                while chunk := await f.read(8192):
                    yield chunk
        except OSError as e:
            logger.error("Failed to read MHTML file %s: %s", mhtml_path, e)
            # Yield empty to signal error - caller will handle
            return

    return StreamingResponse(
        generate(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.delete("/session/{session_id}", response_model=DataResponse[BrowserSessionCleanupData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_session",
    error_code_prefix="RESEARCH_BROWSER",
)
async def cleanup_session(session_id: str):
    """Clean up a research session"""
    _require_browser()
    await get_research_browser_manager().cleanup_session(session_id)

    return JSONResponse(
        status_code=200,
        content={"success": True, "message": f"Session {session_id} cleaned up"},
    )


@router.get("/sessions", response_model=DataResponse[BrowserSessionListData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_sessions",
    error_code_prefix="RESEARCH_BROWSER",
)
async def list_sessions():
    """List all active research sessions"""
    _require_browser()
    sessions_info = []

    for session_id, session in get_research_browser_manager().sessions.items():
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


@router.post("/session/{session_id}/navigate", response_model=DataResponse[BrowserSessionStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="navigate_session",
    error_code_prefix="RESEARCH_BROWSER",
)
async def navigate_session(session_id: str, request: NavigationRequest):
    """Navigate a research session to a specific URL"""
    _require_browser()
    session = get_research_browser_manager().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    result = await session.navigate_to(request.url)

    return JSONResponse(status_code=200, content=result)


# Browser integration endpoints for frontend
@router.get("/browser/{session_id}", response_model=DataResponse[BrowserInfoData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_browser_info",
    error_code_prefix="RESEARCH_BROWSER",
)
async def get_browser_info(session_id: str):
    """Get browser information for frontend integration (Issue #665: refactored)."""
    _require_browser()
    session = _get_or_create_browser_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail=ERR_SESSION_NOT_FOUND)

    docker_browser_info = await _get_docker_browser_info(session)

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
            "actions": _get_browser_actions(),
        },
    )


def _get_or_create_browser_session(session_id: str):
    """Get existing session or create default for chat-browser (Issue #665: extracted helper)."""
    session = get_research_browser_manager().get_session(session_id)

    # Special handling for chat-browser - create default session if needed
    if not session and session_id == "chat-browser":
        logger.info("Creating default chat-browser session for frontend integration")
        session = get_research_browser_manager().create_session(
            conversation_id="default-chat",
            interaction_settings={
                "captcha": False,
                "cloudflare": False,
                "cookies": False,
                "js": False,
            },
        )

    return session


async def _get_docker_browser_info(session) -> dict:
    """Get Docker browser container info (Issue #665: extracted helper)."""
    try:
        from config import PLAYWRIGHT_VNC_URL, get_vnc_direct_url

        return {
            "available": True,
            "vnc_url": PLAYWRIGHT_VNC_URL.replace("vnc.html", ""),
            "direct_url": get_vnc_direct_url(),
            "session_active": session.status == "active",
            "environment": ("container" if await asyncio.to_thread(os.path.exists, "/.dockerenv") else "host"),
        }
    except Exception:
        return {"available": False}


def _get_browser_actions() -> list:
    """Get available browser actions list (Issue #665: extracted helper)."""
    return [
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
    ]


# Chat Browser Session Management (Issue #73)
# These endpoints tie browser sessions to chat conversations like terminal


@router.post("/chat-session", response_model=DataResponse[ChatBrowserSessionData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_or_create_chat_browser_session",
    error_code_prefix="RESEARCH_BROWSER",
)
async def get_or_create_chat_browser_session(request: CreateChatBrowserRequest):
    """
    Get existing or create new browser session for a chat conversation.

    Similar to how terminal sessions are tied to chat via agent-terminal API,
    this endpoint ties browser sessions to chat conversations.

    Issue #73: Browser sessions tied to chat like terminal
    """
    _require_browser()
    # Check for existing session for this conversation
    existing_session = get_research_browser_manager().get_session_by_conversation(request.conversation_id)

    if existing_session and existing_session.status != "closed":
        logger.info(
            f"Found existing browser session {existing_session.session_id} "
            f"for conversation {request.conversation_id}"
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "existing",
                "session_id": existing_session.session_id,
                "conversation_id": existing_session.conversation_id,
                "browser_status": existing_session.status,
                "current_url": existing_session.current_url,
                "interaction_required": existing_session.interaction_required,
            },
        )

    # Create new session
    logger.info(f"Creating new browser session for conversation {request.conversation_id}")
    session_id = await get_research_browser_manager().create_session(request.conversation_id, headless=request.headless)

    if not session_id:
        raise HTTPException(status_code=500, detail="Failed to create browser session")

    session = get_research_browser_manager().get_session(session_id)

    # Navigate to initial URL if provided
    if request.initial_url and session:
        await session.navigate_to(request.initial_url)

    return JSONResponse(
        status_code=201,
        content={
            "status": "created",
            "session_id": session_id,
            "conversation_id": request.conversation_id,
            "browser_status": session.status if session else "unknown",
            "current_url": session.current_url if session else None,
            "interaction_required": session.interaction_required if session else False,
        },
    )


@router.get("/chat-session/{conversation_id}", response_model=DataResponse[ChatBrowserSessionData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_chat_browser_session",
    error_code_prefix="RESEARCH_BROWSER",
)
async def get_chat_browser_session(conversation_id: str):
    """
    Get browser session info for a chat conversation.

    Issue #73: Browser sessions tied to chat like terminal
    """
    _require_browser()
    session = get_research_browser_manager().get_session_by_conversation(conversation_id)

    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"No browser session found for conversation {conversation_id}",
        )

    # Get VNC info for frontend integration
    docker_browser_info = None
    try:
        from config import PLAYWRIGHT_VNC_URL, get_vnc_direct_url

        docker_browser_info = {
            "available": True,
            "vnc_url": PLAYWRIGHT_VNC_URL.replace("vnc.html", ""),
            "direct_url": get_vnc_direct_url(),
            "session_active": session.status == "active",
        }
    except Exception:
        docker_browser_info = {"available": False}

    return JSONResponse(
        status_code=200,
        content={
            "session_id": session.session_id,
            "conversation_id": session.conversation_id,
            "browser_status": session.status,
            "current_url": session.current_url,
            "interaction_required": session.interaction_required,
            "interaction_message": session.interaction_message,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "docker_browser": docker_browser_info,
        },
    )


@router.delete("/chat-session/{conversation_id}", response_model=DataResponse[BrowserSessionCleanupData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_chat_browser_session",
    error_code_prefix="RESEARCH_BROWSER",
)
async def delete_chat_browser_session(conversation_id: str):
    """
    Close browser session for a chat conversation.

    Issue #73: Browser sessions tied to chat like terminal
    """
    _require_browser()
    session = get_research_browser_manager().get_session_by_conversation(conversation_id)

    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"No browser session found for conversation {conversation_id}",
        )

    session_id = session.session_id
    await get_research_browser_manager().cleanup_session(session_id)

    return JSONResponse(
        status_code=200,
        content={
            "status": "deleted",
            "session_id": session_id,
            "conversation_id": conversation_id,
        },
    )
