# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VNC Manager API - Automatic VNC server lifecycle management
Ensures VNC server is always available when noVNC tab is accessed
Extended with desktop interaction controls (Issue #74)
"""

import asyncio
import base64
import logging
import subprocess  # nosec B404
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import with_error_handling
from backend.constants.network_constants import NetworkConstants
from backend.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for request bodies (Issue #74)
class MouseClickRequest(BaseModel):
    """Mouse click action request"""

    x: int = Field(..., ge=0, description="X coordinate")
    y: int = Field(..., ge=0, description="Y coordinate")
    button: str = Field(default="left", description="Mouse button: left, middle, right")


class KeyboardTypeRequest(BaseModel):
    """Keyboard typing action request"""

    text: str = Field(..., description="Text to type")


class SpecialKeyRequest(BaseModel):
    """Special key press request"""

    key: str = Field(..., description="Special key name (e.g., Return, Escape, ctrl+c)")


class MouseScrollRequest(BaseModel):
    """Mouse scroll action request"""

    direction: str = Field(..., description="Scroll direction: up or down")
    amount: int = Field(default=3, ge=1, le=10, description="Scroll amount (1-10)")


class MouseDragRequest(BaseModel):
    """Mouse drag action request"""

    x1: int = Field(..., ge=0, description="Start X coordinate")
    y1: int = Field(..., ge=0, description="Start Y coordinate")
    x2: int = Field(..., ge=0, description="End X coordinate")
    y2: int = Field(..., ge=0, description="End Y coordinate")


class ClipboardSyncRequest(BaseModel):
    """Clipboard sync request"""

    content: str = Field(..., description="Text content to copy to clipboard")


# Issue #74 - Area 4: Advanced Session Management
class ConnectionQualitySettings(BaseModel):
    """VNC connection quality settings"""

    compression_level: int = Field(
        default=6, ge=0, le=9, description="Compression level (0=none, 9=max)"
    )
    quality: int = Field(
        default=6, ge=0, le=9, description="JPEG quality (0=poor, 9=best)"
    )
    encoding: str = Field(
        default="tight", description="Encoding method: tight, hextile, raw"
    )


class ConnectionSettings(BaseModel):
    """VNC connection configuration"""

    auto_reconnect: bool = Field(
        default=True, description="Enable auto-reconnect on disconnect"
    )
    reconnect_delay_ms: int = Field(
        default=3000, ge=1000, le=30000, description="Delay before reconnect"
    )
    max_reconnect_attempts: int = Field(
        default=10, ge=1, le=100, description="Max reconnect attempts"
    )
    quality: ConnectionQualitySettings = Field(
        default_factory=ConnectionQualitySettings
    )


# Global connection settings storage (in-memory for now)
_connection_settings: Dict[str, ConnectionSettings] = {}
_settings_lock = asyncio.Lock()


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


# Desktop Interaction Controls (Issue #74)


def _run_xdotool_cmd(args: list[str], timeout: int = 5) -> Dict[str, str]:
    """
    Execute xdotool command for desktop interaction.

    Helper for desktop interaction endpoints (Issue #74).
    """
    try:
        result = subprocess.run(  # nosec B607
            ["xdotool"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            env={"DISPLAY": ":1"},
        )
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr or "Command failed"}
        return {"status": "success", "message": "Action completed"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Command timeout"}
    except FileNotFoundError:
        return {"status": "error", "message": "xdotool not installed"}
    except Exception as e:
        logger.error("Error running xdotool: %s", e)
        return {"status": "error", "message": str(e)}


@router.post("/click")
@with_error_handling(error_code_prefix="VNC_CLICK")
async def vnc_mouse_click(
    request: MouseClickRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Perform mouse click at specified coordinates.
    Issue #74: Desktop interaction controls.

    Args:
        request: MouseClickRequest with x, y coordinates and button type

    Returns:
        {"status": "success|error", "message": "..."}
    """
    button_map = {"left": "1", "middle": "2", "right": "3"}
    button_num = button_map.get(request.button, "1")

    return _run_xdotool_cmd(
        ["mousemove", str(request.x), str(request.y), "click", button_num]
    )


@router.post("/type")
@with_error_handling(error_code_prefix="VNC_TYPE")
async def vnc_keyboard_type(
    request: KeyboardTypeRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Type text via keyboard.
    Issue #74: Desktop interaction controls.

    Args:
        request: KeyboardTypeRequest with text to type

    Returns:
        {"status": "success|error", "message": "..."}
    """
    return _run_xdotool_cmd(["type", "--", request.text])


@router.post("/key")
@with_error_handling(error_code_prefix="VNC_KEY")
async def vnc_special_key(
    request: SpecialKeyRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Send special key or key combination.
    Issue #74: Desktop interaction controls.

    Args:
        request: SpecialKeyRequest with key name (e.g., "Return", "ctrl+c")

    Returns:
        {"status": "success|error", "message": "..."}
    """
    return _run_xdotool_cmd(["key", request.key])


@router.post("/scroll")
@with_error_handling(error_code_prefix="VNC_SCROLL")
async def vnc_mouse_scroll(
    request: MouseScrollRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Scroll mouse wheel.
    Issue #74: Desktop interaction controls.

    Args:
        request: MouseScrollRequest with direction and amount

    Returns:
        {"status": "success|error", "message": "..."}
    """
    # Mouse buttons: 4 = scroll up, 5 = scroll down
    button = "4" if request.direction == "up" else "5"

    # Perform multiple scroll clicks for smooth scrolling
    args = []
    for _ in range(request.amount):
        args.extend(["click", button])

    return _run_xdotool_cmd(args)


@router.post("/drag")
@with_error_handling(error_code_prefix="VNC_DRAG")
async def vnc_mouse_drag(
    request: MouseDragRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Perform mouse drag operation.
    Issue #74: Desktop interaction controls.

    Args:
        request: MouseDragRequest with start and end coordinates

    Returns:
        {"status": "success|error", "message": "..."}
    """
    return _run_xdotool_cmd(
        [
            "mousemove",
            str(request.x1),
            str(request.y1),
            "mousedown",
            "1",
            "mousemove",
            str(request.x2),
            str(request.y2),
            "mouseup",
            "1",
        ]
    )


@router.get("/screenshot")
@with_error_handling(error_code_prefix="VNC_SCREENSHOT")
async def vnc_screenshot(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Capture desktop screenshot.
    Issue #74: Desktop interaction controls.

    Returns:
        {
            "status": "success|error",
            "image_data": "base64-encoded PNG",
            "message": "..."
        }
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        # Use scrot to capture screenshot
        result = subprocess.run(  # nosec B607
            ["scrot", "-o", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
            env={"DISPLAY": ":1"},
        )

        if result.returncode != 0:
            # Fallback to import command if scrot fails
            result = subprocess.run(  # nosec B607
                ["import", "-window", "root", tmp_path],
                capture_output=True,
                text=True,
                timeout=10,
                env={"DISPLAY": ":1"},
            )

        if result.returncode != 0:
            return {
                "status": "error",
                "message": "Screenshot capture failed",
                "image_data": "",
            }

        # Read and encode image
        with open(tmp_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Cleanup
        Path(tmp_path).unlink(missing_ok=True)

        return {
            "status": "success",
            "message": "Screenshot captured",
            "image_data": image_data,
        }

    except Exception as e:
        logger.error("Error capturing screenshot: %s", e)
        return {"status": "error", "message": str(e), "image_data": ""}


@router.post("/clipboard")
@with_error_handling(error_code_prefix="VNC_CLIPBOARD")
async def vnc_clipboard_sync(
    request: ClipboardSyncRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Sync clipboard content to remote desktop.
    Issue #74: Desktop interaction controls.

    Args:
        request: ClipboardSyncRequest with text content

    Returns:
        {"status": "success|error", "message": "..."}
    """
    try:
        # Use xclip to set clipboard content
        proc = subprocess.Popen(  # nosec B607
            ["xclip", "-selection", "clipboard"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"DISPLAY": ":1"},
        )
        stdout, stderr = proc.communicate(
            input=request.content.encode("utf-8"), timeout=5
        )

        if proc.returncode != 0:
            return {"status": "error", "message": stderr.decode("utf-8")}

        return {"status": "success", "message": "Clipboard synced"}

    except FileNotFoundError:
        return {"status": "error", "message": "xclip not installed"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Clipboard sync timeout"}
    except Exception as e:
        logger.error("Error syncing clipboard: %s", e)
        return {"status": "error", "message": str(e)}


# Connection Settings Management (Issue #74 - Area 4)


@router.get("/connection/settings")
@with_error_handling(error_code_prefix="VNC_CONN_GET")
async def get_connection_settings(
    session_id: str = "default",
    admin_check: bool = Depends(check_admin_permission),
) -> ConnectionSettings:
    """
    Get VNC connection settings for a session.
    Issue #74 - Area 4: Advanced Session Management.

    Args:
        session_id: Session identifier (default: "default")

    Returns:
        Connection settings including quality and reconnect config
    """
    async with _settings_lock:
        if session_id not in _connection_settings:
            _connection_settings[session_id] = ConnectionSettings()
        return _connection_settings[session_id]


@router.post("/connection/settings")
@with_error_handling(error_code_prefix="VNC_CONN_SET")
async def update_connection_settings(
    settings: ConnectionSettings,
    session_id: str = "default",
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Update VNC connection settings for a session.
    Issue #74 - Area 4: Advanced Session Management.

    Args:
        settings: New connection settings
        session_id: Session identifier (default: "default")

    Returns:
        {"status": "success", "message": "..."}
    """
    async with _settings_lock:
        _connection_settings[session_id] = settings

    logger.info(
        "Updated connection settings for session %s: quality=%d, auto_reconnect=%s",
        session_id,
        settings.quality.quality,
        settings.auto_reconnect,
    )

    return {"status": "success", "message": "Connection settings updated"}


@router.get("/connection/quality-metrics")
@with_error_handling(error_code_prefix="VNC_QUALITY")
async def get_connection_quality_metrics(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, object]:
    """
    Get current connection quality metrics.
    Issue #74 - Area 4: Advanced Session Management.

    Returns:
        Connection quality stats (latency, bandwidth, packet loss)
    """
    metrics = {
        "vnc_running": is_vnc_running(),
        "timestamp": datetime.now().isoformat(),
    }

    # Check VNC port connectivity
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        start_time = datetime.now()
        result = sock.connect_ex(("localhost", 5901))
        latency_ms = (datetime.now() - start_time).total_seconds() * 1000
        sock.close()

        metrics["vnc_port_reachable"] = result == 0
        metrics["latency_ms"] = round(latency_ms, 2)
    except Exception as e:
        logger.warning("Failed to check VNC connectivity: %s", e)
        metrics["vnc_port_reachable"] = False

    # Get websockify process info
    try:
        result = subprocess.run(  # nosec B607
            ["pgrep", "-a", "websockify"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        metrics["websockify_running"] = result.returncode == 0
        if result.returncode == 0:
            metrics["websockify_processes"] = len(result.stdout.strip().split("\n"))
    except Exception as e:
        logger.warning("Failed to check websockify: %s", e)

    return metrics


# Desktop Context Info (Issue #74 - Area 3)


def _get_system_info() -> Dict[str, str]:
    """
    Get system information for desktop context panel.

    Helper for desktop context endpoint (Issue #74).
    """
    info = {}

    # CPU usage
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as f:
            load = f.read().split()
            info["cpu_load_1min"] = load[0]
            info["cpu_load_5min"] = load[1]
            info["cpu_load_15min"] = load[2]
    except Exception as e:
        logger.warning("Failed to get CPU load: %s", e)

    # Memory usage
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            lines = f.readlines()
            mem_info = {}
            for line in lines[:3]:  # MemTotal, MemFree, MemAvailable
                parts = line.split()
                if len(parts) >= 2:
                    mem_info[parts[0].rstrip(":")] = parts[1]

            if "MemTotal" in mem_info and "MemAvailable" in mem_info:
                total = int(mem_info["MemTotal"])
                available = int(mem_info["MemAvailable"])
                used = total - available
                percent = (used / total) * 100
                info["memory_used_mb"] = str(used // 1024)
                info["memory_total_mb"] = str(total // 1024)
                info["memory_percent"] = f"{percent:.1f}"
    except Exception as e:
        logger.warning("Failed to get memory info: %s", e)

    # Uptime
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            uptime_seconds = float(f.read().split()[0])
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            info["uptime"] = f"{hours}h {minutes}m"
    except Exception as e:
        logger.warning("Failed to get uptime: %s", e)

    return info


def _get_desktop_info() -> Dict[str, str]:
    """
    Get desktop environment information.

    Helper for desktop context endpoint (Issue #74).
    """
    info = {}

    # Screen resolution
    try:
        result = subprocess.run(  # nosec B607
            ["xdpyinfo"],
            capture_output=True,
            text=True,
            timeout=5,
            env={"DISPLAY": ":1"},
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "dimensions:" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        info["resolution"] = parts[1]
                        break
    except Exception as e:
        logger.warning("Failed to get resolution: %s", e)

    # Active window
    try:
        result = subprocess.run(  # nosec B607
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=5,
            env={"DISPLAY": ":1"},
        )
        if result.returncode == 0:
            info["active_window"] = result.stdout.strip()
    except Exception as e:
        logger.warning("Failed to get active window: %s", e)

    # Window count
    try:
        result = subprocess.run(  # nosec B607
            ["wmctrl", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            env={"DISPLAY": ":1"},
        )
        if result.returncode == 0:
            window_count = len(
                [line for line in result.stdout.split("\n") if line.strip()]
            )
            info["window_count"] = str(window_count)
    except Exception as e:
        logger.debug("Failed to get window count (wmctrl may not be installed): %s", e)

    return info


def _get_process_list() -> List[Dict[str, str]]:
    """
    Get list of running GUI applications.

    Helper for desktop context endpoint (Issue #74).
    """
    processes = []

    try:
        # Get process list with their display usage
        result = subprocess.run(  # nosec B607
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            lines = result.stdout.split("\n")[1:]  # Skip header
            for line in lines:
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    # Filter for X11/GUI apps (rough heuristic)
                    if any(
                        x in parts[10].lower()
                        for x in [
                            "x11",
                            "xorg",
                            "firefox",
                            "chrome",
                            "xfce",
                            "terminal",
                        ]
                    ):
                        processes.append(
                            {
                                "pid": parts[1],
                                "cpu": parts[2],
                                "mem": parts[3],
                                "command": parts[10][:50],  # Truncate long commands
                            }
                        )

            # Limit to top 10 by CPU
            processes.sort(key=lambda x: float(x.get("cpu", "0")), reverse=True)
            processes = processes[:10]

    except Exception as e:
        logger.warning("Failed to get process list: %s", e)

    return processes


@router.get("/desktop/context")
@with_error_handling(error_code_prefix="VNC_CONTEXT")
async def get_desktop_context(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, object]:
    """
    Get desktop context information for context panel.
    Issue #74 - Area 3: Desktop Context Panel.

    Returns:
        {
            "system": {...},      # CPU, memory, uptime
            "desktop": {...},     # Resolution, active window, window count
            "processes": [...],   # Running GUI apps
            "timestamp": "..."
        }
    """
    return {
        "system": _get_system_info(),
        "desktop": _get_desktop_info(),
        "processes": _get_process_list(),
        "timestamp": datetime.now().isoformat(),
    }
