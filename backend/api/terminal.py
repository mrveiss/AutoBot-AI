"""
Terminal API endpoints for AutoBot
Provides REST API for terminal operations and WebSocket connections
"""

from fastapi import APIRouter, WebSocket, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import logging

from backend.api.terminal_websocket import (
    terminal_websocket_endpoint,
    system_command_agent,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class CommandRequest(BaseModel):
    command: str
    description: Optional[str] = None
    require_confirmation: Optional[bool] = True
    timeout: Optional[float] = None


class ToolInstallRequest(BaseModel):
    tool_name: str
    package_name: Optional[str] = None
    install_method: Optional[str] = "auto"
    custom_command: Optional[str] = None
    update_first: Optional[bool] = True


class TerminalInputRequest(BaseModel):
    text: str
    is_password: Optional[bool] = False


@router.websocket("/ws/terminal/{chat_id}")
async def websocket_terminal(websocket: WebSocket, chat_id: str):
    """WebSocket endpoint for terminal sessions"""
    await terminal_websocket_endpoint(websocket, chat_id)


@router.post("/terminal/command")
async def execute_command(request: CommandRequest, req: Request):
    """Execute a command with terminal streaming"""
    try:
        # Get chat_id from request or generate one
        chat_id = req.headers.get("X-Chat-ID", "default")

        result = await system_command_agent.execute_interactive_command(
            command=request.command,
            chat_id=chat_id,
            description=request.description,
            require_confirmation=request.require_confirmation,
            timeout=request.timeout,
        )

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error executing command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal/install-tool")
async def install_tool(request: ToolInstallRequest, req: Request):
    """Install a tool with terminal streaming"""
    try:
        chat_id = req.headers.get("X-Chat-ID", "default")

        tool_info = {
            "name": request.tool_name,
            "package_name": request.package_name or request.tool_name,
            "install_method": request.install_method,
            "custom_command": request.custom_command,
            "update_first": request.update_first,
        }

        result = await system_command_agent.install_tool(tool_info, chat_id)

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error installing tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal/check-tool")
async def check_tool_installed(tool_name: str):
    """Check if a tool is installed"""
    try:
        result = await system_command_agent.check_tool_installed(tool_name)
        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error checking tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal/validate-command")
async def validate_command(command: str):
    """Validate command safety"""
    try:
        result = await system_command_agent.validate_command_safety(command)
        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error validating command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/terminal/package-managers")
async def get_package_managers():
    """Get available package managers"""
    try:
        detected = await system_command_agent.detect_package_manager()
        all_managers = list(system_command_agent.PACKAGE_MANAGERS.keys())

        return JSONResponse(
            content={
                "detected": detected,
                "available": all_managers,
                "package_managers": system_command_agent.PACKAGE_MANAGERS,
            }
        )

    except Exception as e:
        logger.error(f"Error getting package managers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal/sessions")
async def create_terminal_session():
    """Create a new terminal session"""
    try:
        import uuid

        session_id = str(uuid.uuid4())
        logger.info(f"Created new terminal session: {session_id}")
        return JSONResponse(content={"session_id": session_id})
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/terminal/sessions")
async def get_active_sessions():
    """Get list of active terminal sessions"""
    try:
        sessions = await system_command_agent.get_active_sessions()
        return JSONResponse(content={"sessions": sessions})

    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/terminal/sessions/{session_id}")
async def get_session_info(session_id: str):
    """Get information about a specific terminal session"""
    try:
        # For now, return basic session info
        session_info = {
            "session_id": session_id,
            "status": "active",
            "created_at": "2025-08-09T01:00:00Z",
            "shell": "/bin/bash",
            "working_directory": "/home/user",
        }
        return JSONResponse(content=session_info)
    except Exception as e:
        logger.error(f"Error getting session info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/terminal/sessions/{session_id}")
async def delete_terminal_session(session_id: str):
    """Delete a terminal session"""
    try:
        # For now, just return success - the WebSocket disconnect handles cleanup
        logger.info(f"Terminal session {session_id} marked for deletion")
        return JSONResponse(content={"message": f"Session {session_id} deleted"})
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal/{chat_id}/input")
async def send_terminal_input(chat_id: str, request: TerminalInputRequest):
    """Send input to an active terminal session"""
    try:
        await system_command_agent.send_input_to_session(
            chat_id=chat_id, user_input=request.text, is_password=request.is_password
        )

        return JSONResponse(
            content={"status": "success", "message": "Input sent to terminal"}
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending input: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal/{chat_id}/control/take")
async def take_terminal_control(chat_id: str):
    """Take control of terminal session"""
    try:
        await system_command_agent.take_control_of_session(chat_id)

        return JSONResponse(
            content={
                "status": "success",
                "message": "Terminal control transferred to user",
            }
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error taking control: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal/{chat_id}/control/return")
async def return_terminal_control(chat_id: str):
    """Return control of terminal session to agent"""
    try:
        await system_command_agent.return_control_of_session(chat_id)

        return JSONResponse(
            content={
                "status": "success",
                "message": "Terminal control returned to agent",
            }
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error returning control: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/terminal/{chat_id}/signal/{signal_type}")
async def send_terminal_signal(chat_id: str, signal_type: str):
    """Send signal to terminal session"""
    try:
        valid_signals = ["interrupt", "quit", "suspend", "kill"]
        if signal_type not in valid_signals:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid signal type. Must be one of: {valid_signals}",
            )

        await system_command_agent.send_signal_to_session(chat_id, signal_type)

        return JSONResponse(
            content={
                "status": "success",
                "message": f"Signal {signal_type} sent to terminal",
            }
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error sending signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))
