"""
Research Browser API
Handles browser automation for research tasks with user interaction support
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.research_browser_manager import research_browser_manager

logger = logging.getLogger(__name__)

router = APIRouter()


class ResearchRequest(BaseModel):
    conversation_id: str
    url: str
    extract_content: bool = True


class SessionAction(BaseModel):
    session_id: str
    action: str  # "wait", "manual_intervention", "save_mhtml", "extract_content"
    timeout_seconds: Optional[int] = 300


@router.post("/url")
async def research_url(request: ResearchRequest):
    """Research a URL with automatic fallbacks and interaction handling"""
    try:
        result = await research_browser_manager.research_url(
            request.conversation_id,
            request.url,
            request.extract_content
        )

        return JSONResponse(status_code=200, content=result)

    except Exception as e:
        logger.error(f"Research URL failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.post("/session/action")
async def handle_session_action(request: SessionAction):
    """Handle actions on a research session"""
    try:
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

    except Exception as e:
        logger.error(f"Session action failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Get the status of a research session"""
    try:
        session = research_browser_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return JSONResponse(status_code=200, content={
            "session_id": session_id,
            "conversation_id": session.conversation_id,
            "status": session.status,
            "current_url": session.current_url,
            "interaction_required": session.interaction_required,
            "interaction_message": session.interaction_message,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "mhtml_files_count": len(session.mhtml_files)
        })

    except Exception as e:
        logger.error(f"Get session status failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.get("/session/{session_id}/mhtml/{filename}")
async def download_mhtml(session_id: str, filename: str):
    """Download an MHTML file from a research session"""
    try:
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

        # Stream the file
        def generate():
            with open(mhtml_path, 'rb') as f:
                while chunk := f.read(8192):
                    yield chunk

        return StreamingResponse(
            generate(),
            media_type='application/octet-stream',
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Download MHTML failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session/{session_id}")
async def cleanup_session(session_id: str):
    """Clean up a research session"""
    try:
        await research_browser_manager.cleanup_session(session_id)

        return JSONResponse(status_code=200, content={
            "success": True,
            "message": f"Session {session_id} cleaned up"
        })

    except Exception as e:
        logger.error(f"Cleanup session failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.get("/sessions")
async def list_sessions():
    """List all active research sessions"""
    try:
        sessions_info = []

        for session_id, session in research_browser_manager.sessions.items():
            sessions_info.append({
                "session_id": session_id,
                "conversation_id": session.conversation_id,
                "status": session.status,
                "current_url": session.current_url,
                "interaction_required": session.interaction_required,
                "created_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat()
            })

        return JSONResponse(status_code=200, content={
            "sessions": sessions_info,
            "total_sessions": len(sessions_info)
        })

    except Exception as e:
        logger.error(f"List sessions failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


class NavigationRequest(BaseModel):
    url: str


@router.post("/session/{session_id}/navigate")
async def navigate_session(session_id: str, request: NavigationRequest):
    """Navigate a research session to a specific URL"""
    try:
        session = research_browser_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        result = await session.navigate_to(request.url)

        return JSONResponse(status_code=200, content=result)

    except Exception as e:
        logger.error(f"Navigate session failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# Browser integration endpoints for frontend
@router.get("/browser/{session_id}")
async def get_browser_info(session_id: str):
    """Get browser information for frontend integration"""
    try:
        session = research_browser_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Check if we have a Docker browser container available
        docker_browser_info = None
        try:
            # Try to detect Playwright container
            # This would integrate with your existing browser setup
            docker_browser_info = {
                "available": True,
                "vnc_url": "http://localhost:6080",  # NoVNC port
                "direct_url": "vnc://localhost:5900",  # Direct VNC
                "session_active": session.status == "active"
            }
        except Exception:
            docker_browser_info = {"available": False}

        return JSONResponse(status_code=200, content={
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
                    "description": "Wait for user to complete interaction"
                },
                {
                    "action": "manual_intervention",
                    "label": "Manual Control",
                    "description": "Take manual control of browser"
                },
                {
                    "action": "save_mhtml",
                    "label": "Save Page",
                    "description": "Save current page as MHTML backup"
                },
                {
                    "action": "extract_content",
                    "label": "Extract Content",
                    "description": "Extract text content from current page"
                }
            ]
        })

    except Exception as e:
        logger.error(f"Get browser info failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )
