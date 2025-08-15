#!/usr/bin/env python3
"""
Elevation Management API
Handles privilege escalation requests through GUI dialogs
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["elevation"])

# In-memory storage for elevation sessions (in production, use Redis)
elevation_sessions: Dict[str, dict] = {}
pending_requests: Dict[str, dict] = {}


class ElevationRequest(BaseModel):
    operation: str
    command: str
    reason: str
    risk_level: str = "MEDIUM"


class ElevationAuthorization(BaseModel):
    request_id: str
    password: str
    remember_session: bool = False


@router.post("/request")
async def request_elevation(request: ElevationRequest):
    """Request elevation for a privileged operation"""
    request_id = str(uuid.uuid4())

    # Store the pending request
    pending_requests[request_id] = {
        "operation": request.operation,
        "command": request.command,
        "reason": request.reason,
        "risk_level": request.risk_level,
        "timestamp": datetime.now(),
        "status": "pending",
    }

    logger.info(f"Elevation requested: {request_id} - {request.operation}")

    return {
        "success": True,
        "request_id": request_id,
        "message": "Elevation request created - awaiting user authorization",
    }


@router.post("/authorize")
async def authorize_elevation(auth: ElevationAuthorization):
    """Authorize an elevation request with password"""
    request_id = auth.request_id

    if request_id not in pending_requests:
        raise HTTPException(status_code=404, detail="Elevation request not found")

    try:
        # Verify sudo password (safely)
        is_valid = await verify_sudo_password(auth.password)

        if not is_valid:
            logger.warning(f"Invalid sudo password for request {request_id}")
            raise HTTPException(status_code=401, detail="Invalid password")

        # Create session token
        session_token = str(uuid.uuid4())
        session_data = {
            "token": session_token,
            "created": datetime.now(),
            "expires": datetime.now()
            + timedelta(minutes=15 if auth.remember_session else 5),
            "request_id": request_id,
        }

        elevation_sessions[session_token] = session_data

        # Mark request as authorized
        pending_requests[request_id]["status"] = "authorized"
        pending_requests[request_id]["session_token"] = session_token

        logger.info(f"Elevation authorized: {request_id}")

        return {
            "success": True,
            "session_token": session_token,
            "expires_in": int(
                (session_data["expires"] - datetime.now()).total_seconds()
            ),
            "message": "Authorization successful",
        }

    except Exception as e:
        logger.error(f"Elevation authorization failed: {e}")
        raise HTTPException(status_code=500, detail="Authorization failed")


@router.get("/status/{request_id}")
async def get_elevation_status(request_id: str):
    """Check the status of an elevation request"""
    if request_id not in pending_requests:
        raise HTTPException(status_code=404, detail="Request not found")

    request_data = pending_requests[request_id]

    return {
        "success": True,
        "request_id": request_id,
        "status": request_data["status"],
        "operation": request_data["operation"],
        "timestamp": request_data["timestamp"],
    }


@router.post("/execute/{session_token}")
async def execute_elevated_command(session_token: str, command: str):
    """Execute a command with elevated privileges using session token"""
    if session_token not in elevation_sessions:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    session_data = elevation_sessions[session_token]

    # Check if session is expired
    if datetime.now() > session_data["expires"]:
        del elevation_sessions[session_token]
        raise HTTPException(status_code=401, detail="Session expired")

    try:
        # Execute command with sudo (using NOPASSWD for the session)
        # In production, implement proper security controls
        result = await run_elevated_command(command)

        logger.info(f"Elevated command executed: {command}")

        return {
            "success": True,
            "output": result.get("stdout", ""),
            "error": result.get("stderr", ""),
            "return_code": result.get("return_code", 0),
        }

    except Exception as e:
        logger.error(f"Failed to execute elevated command: {e}")
        raise HTTPException(
            status_code=500, detail=f"Command execution failed: {str(e)}"
        )


@router.get("/pending")
async def get_pending_requests():
    """Get all pending elevation requests"""
    active_requests = {
        req_id: req_data
        for req_id, req_data in pending_requests.items()
        if req_data["status"] == "pending"
    }

    return {
        "success": True,
        "pending_requests": active_requests,
        "count": len(active_requests),
    }


async def verify_sudo_password(password: str) -> bool:
    """Safely verify sudo password"""
    try:
        # Use sudo -k to clear cached credentials, then test with -v
        process = await asyncio.create_subprocess_shell(
            f'echo "{password}" | sudo -S -k -v',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        return process.returncode == 0

    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False


async def run_elevated_command(command: str) -> dict:
    """Run command with elevated privileges"""
    try:
        process = await asyncio.create_subprocess_shell(
            f"sudo {command}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return {
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "return_code": process.returncode,
        }

    except Exception as e:
        return {"stdout": "", "stderr": str(e), "return_code": 1}


@router.delete("/session/{session_token}")
async def revoke_elevation_session(session_token: str):
    """Revoke an elevation session"""
    if session_token in elevation_sessions:
        del elevation_sessions[session_token]
        logger.info(f"Elevation session revoked: {session_token}")

    return {"success": True, "message": "Session revoked"}


@router.get("/health")
async def elevation_health_check():
    """Health check for elevation system"""
    return {
        "status": "healthy",
        "service": "elevation",
        "active_sessions": len(elevation_sessions),
        "pending_requests": len(
            [r for r in pending_requests.values() if r["status"] == "pending"]
        ),
        "timestamp": datetime.now().isoformat(),
    }
