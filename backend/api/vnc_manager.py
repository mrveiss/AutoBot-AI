# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VNC Manager API - Automatic VNC server lifecycle management
Ensures VNC server is always available when noVNC tab is accessed
"""

import logging
import subprocess
from typing import Dict

from fastapi import APIRouter, HTTPException

from src.constants.network_constants import NetworkConstants
from src.utils.error_boundaries import with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter()


def is_vnc_running() -> bool:
    """Check if VNC server is running on display :1"""
    try:
        # Check for Xtigervnc process on display :1
        result = subprocess.run(
            ["pgrep", "-f", "Xtigervnc :1"],
            capture_output=True,
            timeout=5,
        )
        # pgrep returns 0 if process found, 1 if not found
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error checking VNC status: {e}")
        return False


def start_vnc_server() -> Dict[str, str]:
    """Start VNC server on display :1 with full XFCE desktop"""
    try:
        # Start VNC server
        result = subprocess.run(
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
        subprocess.Popen(
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
        logger.error(f"Error starting VNC server: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/status")
@with_error_handling(error_code_prefix="VNC_STATUS")
async def get_vnc_status() -> Dict[str, bool]:
    """
    Check if VNC server is running

    Returns:
        {"running": true/false}
    """
    running = is_vnc_running()
    return {"running": running}


@router.post("/ensure-running")
@with_error_handling(error_code_prefix="VNC_ENSURE")
async def ensure_vnc_running() -> Dict[str, str]:
    """
    Ensure VNC server is running, start it if not

    Returns:
        {"status": "running|started|error", "message": "..."}
    """
    if is_vnc_running():
        return {"status": "running", "message": "VNC server already running"}

    logger.info("VNC server not running, starting...")
    return start_vnc_server()


@router.post("/restart")
@with_error_handling(error_code_prefix="VNC_RESTART")
async def restart_vnc_server() -> Dict[str, str]:
    """
    Restart VNC server (kill existing and start new)

    Returns:
        {"status": "started|error", "message": "..."}
    """
    try:
        # Kill existing VNC server
        subprocess.run(
            ["vncserver", "-kill", ":1"],
            capture_output=True,
            timeout=5,
        )

        # Kill websockify
        subprocess.run(
            ["pkill", "-9", "websockify"],
            capture_output=True,
            timeout=5,
        )

        # Wait a moment for cleanup
        import time

        time.sleep(1)

        # Start fresh
        return start_vnc_server()

    except Exception as e:
        logger.error(f"Error restarting VNC server: {e}")
        return {"status": "error", "message": str(e)}
