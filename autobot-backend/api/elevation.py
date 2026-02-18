#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Elevation Management API
Handles privilege escalation requests through GUI dialogs
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(tags=["elevation"])

# Issue #380: Module-level frozenset for allowed elevated commands
_ALLOWED_ELEVATED_COMMANDS = frozenset(
    {"apt", "systemctl", "mount", "umount", "chmod", "chown"}
)

# In-memory storage for elevation sessions (in production, use Redis)
elevation_sessions: Dict[str, dict] = {}
pending_requests: Dict[str, dict] = {}

# Locks for thread-safe access
_elevation_sessions_lock = asyncio.Lock()
_pending_requests_lock = asyncio.Lock()


class ElevationRequest(BaseModel):
    operation: str
    command: str
    reason: str
    risk_level: str = "MEDIUM"


class ElevationAuthorization(BaseModel):
    request_id: str
    password: str
    remember_session: bool = False


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="request_elevation",
    error_code_prefix="ELEVATION",
)
@router.post("/request")
async def request_elevation(request: ElevationRequest):
    """Request elevation for a privileged operation"""
    request_id = str(uuid.uuid4())

    # Store the pending request (thread-safe)
    async with _pending_requests_lock:
        pending_requests[request_id] = {
            "operation": request.operation,
            "command": request.command,
            "reason": request.reason,
            "risk_level": request.risk_level,
            "timestamp": datetime.now(),
            "status": "pending",
        }

    logger.info("Elevation requested: %s - %s", request_id, request.operation)

    return {
        "success": True,
        "request_id": request_id,
        "message": "Elevation request created - awaiting user authorization",
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="authorize_elevation",
    error_code_prefix="ELEVATION",
)
@router.post("/authorize")
async def authorize_elevation(auth: ElevationAuthorization):
    """Authorize an elevation request with password"""
    request_id = auth.request_id

    async with _pending_requests_lock:
        if request_id not in pending_requests:
            raise HTTPException(status_code=404, detail="Elevation request not found")

    try:
        # Verify sudo password (safely)
        is_valid = await verify_sudo_password(auth.password)

        if not is_valid:
            logger.warning("Invalid sudo password for request %s", request_id)
            raise HTTPException(status_code=401, detail="Invalid password")

        # Create session token
        session_token = str(uuid.uuid4())
        session_data = {
            "token": session_token,
            "created": datetime.now(),
            "expires": (
                datetime.now() + timedelta(minutes=15 if auth.remember_session else 5)
            ),
            "request_id": request_id,
        }

        # Thread-safe updates
        async with _elevation_sessions_lock:
            elevation_sessions[session_token] = session_data

        # Mark request as authorized
        async with _pending_requests_lock:
            pending_requests[request_id]["status"] = "authorized"
            pending_requests[request_id]["session_token"] = session_token

        logger.info("Elevation authorized: %s", request_id)

        return {
            "success": True,
            "session_token": session_token,
            "expires_in": int(
                (session_data["expires"] - datetime.now()).total_seconds()
            ),
            "message": "Authorization successful",
        }

    except ValueError as e:
        logger.error("Elevation authorization failed due to invalid input: %s", e)
        raise HTTPException(status_code=400, detail="Invalid authorization data")
    except (OSError, IOError) as e:
        logger.error("Elevation authorization failed due to system error: %s", e)
        raise HTTPException(status_code=500, detail="System error during authorization")
    except Exception as e:
        logger.error("Elevation authorization failed: %s", e)
        raise HTTPException(status_code=500, detail="Authorization failed")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_elevation_status",
    error_code_prefix="ELEVATION",
)
@router.get("/status/{request_id}")
async def get_elevation_status(request_id: str):
    """Check the status of an elevation request"""
    async with _pending_requests_lock:
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_elevated_command",
    error_code_prefix="ELEVATION",
)
@router.post("/execute/{session_token}")
async def execute_elevated_command(session_token: str, command: str):
    """Execute a command with elevated privileges using session token"""
    async with _elevation_sessions_lock:
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

        logger.info("Elevated command executed: %s", command)

        return {
            "success": True,
            "output": result.get("stdout", ""),
            "error": result.get("stderr", ""),
            "return_code": result.get("return_code", 0),
        }

    except (OSError, IOError) as e:
        logger.error("Failed to execute elevated command due to system error: %s", e)
        raise HTTPException(
            status_code=500, detail="System error during command execution"
        )
    except asyncio.TimeoutError as e:
        logger.error("Failed to execute elevated command due to timeout: %s", e)
        raise HTTPException(status_code=408, detail="Command execution timed out")
    except Exception as e:
        logger.error("Failed to execute elevated command: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Command execution failed: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pending_requests",
    error_code_prefix="ELEVATION",
)
@router.get("/pending")
async def get_pending_requests_endpoint():
    """Get all pending elevation requests"""
    async with _pending_requests_lock:
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
    """Safely verify sudo password without command injection"""
    try:
        # SECURITY FIX: Use subprocess_exec instead of shell to prevent injection
        process = await asyncio.create_subprocess_exec(
            "sudo",
            "-S",
            "-k",
            "-v",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Send password safely through stdin
        stdout, stderr = await process.communicate(input=f"{password}\n".encode())
        return process.returncode == 0

    except (OSError, IOError) as e:
        logger.error("Password verification failed due to system error: %s", e)
        return False
    except asyncio.TimeoutError as e:
        logger.error("Password verification failed due to timeout: %s", e)
        return False
    except Exception as e:
        logger.error("Password verification failed: %s", e)
        return False


async def run_elevated_command(command: str) -> dict:
    """Run command with elevated privileges safely"""
    try:
        # SECURITY FIX: Parse command safely and use exec instead of shell
        import shlex

        cmd_parts = shlex.split(command)
        if not cmd_parts:
            raise ValueError("Empty command")

        # Validate command against allowlist for security (Issue #380)
        if cmd_parts[0] not in _ALLOWED_ELEVATED_COMMANDS:
            raise ValueError(f"Command '{cmd_parts[0]}' not in allowlist")

        process = await asyncio.create_subprocess_exec(
            "sudo",
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return {
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "return_code": process.returncode,
        }

    except (OSError, IOError) as e:
        logger.error("Command execution failed due to system error: %s", e)
        return {"stdout": "", "stderr": f"System error: {str(e)}", "return_code": 1}
    except asyncio.TimeoutError as e:
        logger.error("Command execution failed due to timeout: %s", e)
        return {"stdout": "", "stderr": "Command timed out", "return_code": 124}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "return_code": 1}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="revoke_elevation_session",
    error_code_prefix="ELEVATION",
)
@router.delete("/session/{session_token}")
async def revoke_elevation_session(session_token: str):
    """Revoke an elevation session"""
    if session_token in elevation_sessions:
        del elevation_sessions[session_token]
        logger.info("Elevation session revoked: %s", session_token)

    return {"success": True, "message": "Session revoked"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="elevation_health_check",
    error_code_prefix="ELEVATION",
)
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
