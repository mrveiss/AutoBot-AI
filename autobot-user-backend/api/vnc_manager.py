# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VNC Manager API - Automatic VNC server lifecycle management
Ensures VNC server is always available when noVNC tab is accessed
"""

import asyncio
import logging
import subprocess  # nosec B404
from typing import Dict

from fastapi import APIRouter, Depends

from auth_middleware import check_admin_permission
from constants.network_constants import NetworkConstants
from constants.threshold_constants import TimingConstants
from autobot_shared.error_boundaries import with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter()


def is_vnc_running() -> bool:
    """Check if VNC server is running on display :1"""
    try:
        # Check for Xtigervnc process on display :1
        result = subprocess.run(  # nosec B607
            ["pgrep", "-f", "Xtigervnc :1"],
            capture_output=True,
            timeout=5,
        )
        # pgrep returns 0 if process found, 1 if not found
        return result.returncode == 0
    except Exception as e:
        logger.error("Error checking VNC status: %s", e)
        return False


def start_vnc_server() -> Dict[str, str]:
    """Start VNC server on display :1 with full XFCE desktop"""
    try:
        # Start VNC server
        result = subprocess.run(  # nosec B607
            [
                "/usr/bin/vncserver",
                ":1",
                "-localhost",
                "no",
                "-SecurityTypes",
                "None",
                "-rfbport",
                "5901",
                "--I-KNOW-THIS-IS-INSECURE",
                "-geometry",
                "1920x1080",
                "-depth",
                "24",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"VNC server failed to start: {result.stderr}",
            }

        # Start websockify for noVNC access
        websockify_bind = (
            f"{NetworkConstants.BIND_ALL_INTERFACES}:{NetworkConstants.VNC_PORT}"
        )
        vnc_target = f"{NetworkConstants.LOCALHOST_NAME}:5901"
        subprocess.Popen(  # nosec B607
            [
                "/usr/bin/websockify",
                "--web",
                "/usr/share/novnc",
                websockify_bind,
                vnc_target,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return {"status": "started", "message": "VNC server started successfully"}

    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "VNC server start timeout"}
    except Exception as e:
        logger.error("Error starting VNC server: %s", e)
        return {"status": "error", "message": str(e)}


@router.get("/status")
@with_error_handling(error_code_prefix="VNC_STATUS")
async def get_vnc_status(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, bool]:
    """
    Check if VNC server is running
    Issue #744: Requires admin authentication.

    Returns:
        {"running": true/false}
    """
    running = is_vnc_running()
    return {"running": running}


@router.post("/ensure-running")
@with_error_handling(error_code_prefix="VNC_ENSURE")
async def ensure_vnc_running(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Ensure VNC server is running, start it if not
    Issue #744: Requires admin authentication.

    Returns:
        {"status": "running|started|error", "message": "..."}
    """
    if is_vnc_running():
        return {"status": "running", "message": "VNC server already running"}

    logger.info("VNC server not running, starting...")
    return start_vnc_server()


@router.post("/restart")
@with_error_handling(error_code_prefix="VNC_RESTART")
async def restart_vnc_server(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Restart VNC server (kill existing and start new)
    Issue #744: Requires admin authentication.

    Returns:
        {"status": "started|error", "message": "..."}
    """
    try:
        # Issue #379: Kill VNC server and websockify in parallel
        async def kill_vnc():
            """Kill VNC server with timeout handling."""
            proc = await asyncio.create_subprocess_exec(
                "vncserver",
                "-kill",
                ":1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

        async def kill_websockify():
            """Kill websockify with timeout handling."""
            proc = await asyncio.create_subprocess_exec(
                "pkill",
                "-9",
                "websockify",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

        # Run both kill operations in parallel
        await asyncio.gather(kill_vnc(), kill_websockify(), return_exceptions=True)

        # Wait a moment for cleanup (async to not block event loop)
        await asyncio.sleep(TimingConstants.STANDARD_DELAY)

        # Start fresh
        return start_vnc_server()

    except Exception as e:
        logger.error("Error restarting VNC server: %s", e)
        return {"status": "error", "message": str(e)}
