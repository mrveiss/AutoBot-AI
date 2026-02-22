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

# Issue #74 - Area 5: Human-like behavior helpers
from api.vnc_humanization import (
    humanize_action_delay,
    humanize_click_position,
    humanize_pause_duration,
    humanize_typing_speed,
    should_add_human_pause,
    simulate_mouse_curve,
)
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
    Perform mouse click at specified coordinates with human-like behavior.
    Issue #74: Desktop interaction controls + Area 5 (humanization).

    Args:
        request: MouseClickRequest with x, y coordinates and button type

    Returns:
        {"status": "success|error", "message": "..."}
    """
    # Add human-like randomness to click position (Issue #74 - Area 5)
    humanized_x, humanized_y = humanize_click_position(request.x, request.y)

    button_map = {"left": "1", "middle": "2", "right": "3"}
    button_num = button_map.get(request.button, "1")

    # Add realistic delay before action
    delay = humanize_action_delay()
    await asyncio.sleep(delay)

    return _run_xdotool_cmd(
        ["mousemove", str(humanized_x), str(humanized_y), "click", button_num]
    )


@router.post("/type")
@with_error_handling(error_code_prefix="VNC_TYPE")
async def vnc_keyboard_type(
    request: KeyboardTypeRequest,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Type text via keyboard with human-like speed and pauses.
    Issue #74: Desktop interaction controls + Area 5 (humanization).

    Args:
        request: KeyboardTypeRequest with text to type

    Returns:
        {"status": "success|error", "message": "..."}
    """
    # Get humanized typing delay in milliseconds for xdotool
    delay_seconds = humanize_typing_speed()
    delay_ms = int(delay_seconds * 1000)

    # Add realistic delay before starting to type
    pre_delay = humanize_action_delay()
    await asyncio.sleep(pre_delay)

    # Add random pause during typing if needed
    if should_add_human_pause():
        # Split text roughly in half for mid-typing pause
        mid_point = len(request.text) // 2
        first_half = request.text[:mid_point]
        second_half = request.text[mid_point:]

        # Type first half
        result = _run_xdotool_cmd(["type", "--delay", str(delay_ms), "--", first_half])
        if result["status"] == "error":
            return result

        # Human pause
        pause = humanize_pause_duration()
        await asyncio.sleep(pause)

        # Type second half
        return _run_xdotool_cmd(["type", "--delay", str(delay_ms), "--", second_half])
    else:
        # Type all at once with humanized delay
        return _run_xdotool_cmd(["type", "--delay", str(delay_ms), "--", request.text])


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
    Perform mouse drag operation with curved, human-like movement.
    Issue #74: Desktop interaction controls + Area 5 (humanization).

    Args:
        request: MouseDragRequest with start and end coordinates

    Returns:
        {"status": "success|error", "message": "..."}
    """
    # Add realistic delay before starting drag
    pre_delay = humanize_action_delay()
    await asyncio.sleep(pre_delay)

    # Generate curved path for realistic mouse movement
    path_points = simulate_mouse_curve(request.x1, request.y1, request.x2, request.y2)

    # Move to start position and press mouse button
    result = _run_xdotool_cmd(
        ["mousemove", str(request.x1), str(request.y1), "mousedown", "1"]
    )
    if result["status"] == "error":
        return result

    # Move through the curved path with small delays
    for x, y in path_points[1:]:  # Skip first point (already there)
        _run_xdotool_cmd(["mousemove", str(x), str(y)])
        # Small delay between movements for smooth curve
        await asyncio.sleep(0.01)

    # Release mouse button at end position
    return _run_xdotool_cmd(["mouseup", "1"])


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


# Area 5: Automation Features - Macro Recording/Playback


class MacroAction(BaseModel):
    """Single macro action"""

    action_type: str = Field(
        ..., description="Action type: click, type, key, scroll, drag"
    )
    params: Dict = Field(default_factory=dict, description="Action parameters")
    timestamp: float = Field(..., description="Timestamp when action was recorded")


class MacroRecording(BaseModel):
    """Recorded macro sequence"""

    name: str = Field(..., description="Macro name")
    actions: List[MacroAction] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# Global macro storage (in-memory for now)
_macros: Dict[str, MacroRecording] = {}
_recording_session: Dict[str, MacroRecording] = {}
_macros_lock = asyncio.Lock()


@router.post("/macro/record/start")
@with_error_handling(error_code_prefix="VNC_MACRO_START")
async def start_macro_recording(
    name: str, admin_check: bool = Depends(check_admin_permission)
) -> Dict[str, str]:
    """
    Start recording a macro sequence.
    Issue #74 - Area 5: Automation Features.

    Args:
        name: Macro name

    Returns:
        {"status": "success|error", "message": "..."}
    """
    async with _macros_lock:
        if name in _recording_session:
            return {"status": "error", "message": f"Macro '{name}' already recording"}

        _recording_session[name] = MacroRecording(name=name)
        logger.info("Started recording macro: %s", name)

    return {"status": "success", "message": f"Started recording macro '{name}'"}


@router.post("/macro/record/stop")
@with_error_handling(error_code_prefix="VNC_MACRO_STOP")
async def stop_macro_recording(
    name: str, admin_check: bool = Depends(check_admin_permission)
) -> Dict[str, str]:
    """
    Stop recording a macro and save it.
    Issue #74 - Area 5: Automation Features.

    Args:
        name: Macro name

    Returns:
        {"status": "success|error", "message": "...", "action_count": N}
    """
    async with _macros_lock:
        if name not in _recording_session:
            return {"status": "error", "message": f"Macro '{name}' not recording"}

        macro = _recording_session.pop(name)
        _macros[name] = macro
        logger.info(
            "Stopped recording macro: %s (%d actions)", name, len(macro.actions)
        )

    return {
        "status": "success",
        "message": f"Saved macro '{name}'",
        "action_count": len(macro.actions),
    }


@router.get("/macros")
@with_error_handling(error_code_prefix="VNC_MACROS_LIST")
async def list_macros(
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, List[Dict]]:
    """
    List all saved macros.
    Issue #74 - Area 5: Automation Features.

    Returns:
        {"macros": [{name, action_count, created_at}, ...]}
    """
    async with _macros_lock:
        macro_list = [
            {
                "name": name,
                "action_count": len(macro.actions),
                "created_at": macro.created_at,
            }
            for name, macro in _macros.items()
        ]

    return {"macros": macro_list}


@router.post("/macro/playback")
@with_error_handling(error_code_prefix="VNC_MACRO_PLAY")
async def playback_macro(
    name: str, admin_check: bool = Depends(check_admin_permission)
) -> Dict[str, str]:
    """
    Play back a recorded macro.
    Issue #74 - Area 5: Automation Features.

    Args:
        name: Macro name

    Returns:
        {"status": "success|error", "message": "..."}
    """
    async with _macros_lock:
        if name not in _macros:
            return {"status": "error", "message": f"Macro '{name}' not found"}

        macro = _macros[name]

    logger.info("Playing back macro: %s (%d actions)", name, len(macro.actions))

    # Replay actions with timing delays
    start_time = datetime.now()
    for i, action in enumerate(macro.actions):
        # Calculate delay since previous action
        if i > 0:
            prev_time = macro.actions[i - 1].timestamp
            delay = action.timestamp - prev_time
            await asyncio.sleep(min(delay, 2.0))  # Cap delays at 2s

        # Execute action based on type
        try:
            if action.action_type == "click":
                await vnc_mouse_click(MouseClickRequest(**action.params))
            elif action.action_type == "type":
                await vnc_keyboard_type(KeyboardTypeRequest(**action.params))
            elif action.action_type == "key":
                await vnc_special_key(SpecialKeyRequest(**action.params))
            elif action.action_type == "scroll":
                await vnc_mouse_scroll(MouseScrollRequest(**action.params))
            elif action.action_type == "drag":
                await vnc_mouse_drag(MouseDragRequest(**action.params))
        except Exception as e:
            logger.error("Error executing macro action %d: %s", i, e)
            return {
                "status": "error",
                "message": f"Failed at action {i + 1}/{len(macro.actions)}: {e}",
            }

    elapsed = (datetime.now() - start_time).total_seconds()
    return {
        "status": "success",
        "message": f"Played macro '{name}' ({len(macro.actions)} actions in {elapsed:.1f}s)",
    }


@router.delete("/macro/{name}")
@with_error_handling(error_code_prefix="VNC_MACRO_DELETE")
async def delete_macro(
    name: str, admin_check: bool = Depends(check_admin_permission)
) -> Dict[str, str]:
    """
    Delete a saved macro.
    Issue #74 - Area 5: Automation Features.

    Args:
        name: Macro name

    Returns:
        {"status": "success|error", "message": "..."}
    """
    async with _macros_lock:
        if name not in _macros:
            return {"status": "error", "message": f"Macro '{name}' not found"}

        del _macros[name]
        logger.info("Deleted macro: %s", name)

    return {"status": "success", "message": f"Deleted macro '{name}'"}


# Area 5: Automation Features - OCR Text Recognition


class OCRRequest(BaseModel):
    """OCR text recognition request"""

    region: Dict[str, int] = Field(
        default_factory=dict,
        description="Optional region {x, y, width, height}, empty for full screen",
    )


@router.post("/ocr")
@with_error_handling(error_code_prefix="VNC_OCR")
async def vnc_ocr_text(
    request: OCRRequest, admin_check: bool = Depends(check_admin_permission)
) -> Dict[str, object]:
    """
    Perform OCR text recognition on desktop screenshot.
    Issue #74 - Area 5: Automation Features.

    Args:
        request: OCRRequest with optional region

    Returns:
        {"status": "success|error", "text": "recognized text", "message": "..."}
    """
    try:
        # Check if pytesseract is available
        import pytesseract
        from PIL import Image
    except ImportError:
        return {
            "status": "error",
            "text": "",
            "message": "pytesseract not installed. Run: pip install pytesseract pillow",
        }

    try:
        # Capture screenshot
        screenshot_result = await vnc_screenshot()
        if screenshot_result["status"] != "success":
            return {"status": "error", "text": "", "message": "Screenshot failed"}

        # Decode image
        image_data = base64.b64decode(screenshot_result["image_data"])
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            tmp_file.write(image_data)
            tmp_path = tmp_file.name

        # Load image
        image = Image.open(tmp_path, encoding="utf-8")

        # Crop to region if specified
        if request.region and all(
            k in request.region for k in ["x", "y", "width", "height"]
        ):
            box = (
                request.region["x"],
                request.region["y"],
                request.region["x"] + request.region["width"],
                request.region["y"] + request.region["height"],
            )
            image = image.crop(box)

        # Perform OCR
        text = pytesseract.image_to_string(image)

        # Cleanup
        Path(tmp_path).unlink(missing_ok=True)

        return {"status": "success", "text": text.strip(), "message": "OCR completed"}

    except Exception as e:
        logger.error("OCR failed: %s", e)
        return {"status": "error", "text": "", "message": str(e)}


# Area 5: Automation Features - Image Template Matching


class FindImageRequest(BaseModel):
    """Find image on screen request"""

    template_data: str = Field(..., description="Base64-encoded template image (PNG)")
    threshold: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Match confidence threshold (0-1)"
    )


@router.post("/find-image")
@with_error_handling(error_code_prefix="VNC_FIND_IMAGE")
async def vnc_find_image(
    request: FindImageRequest, admin_check: bool = Depends(check_admin_permission)
) -> Dict[str, object]:
    """
    Find template image on desktop screenshot.
    Issue #74 - Area 5: Automation Features.

    Args:
        request: FindImageRequest with template and threshold

    Returns:
        {
            "status": "success|error",
            "found": true/false,
            "x": center_x,
            "y": center_y,
            "confidence": 0.95,
            "message": "..."
        }
    """
    try:
        # Check if opencv is available
        import cv2
        import numpy as np
    except ImportError:
        return {
            "status": "error",
            "found": False,
            "message": "opencv not installed. Run: pip install opencv-python",
        }

    try:
        # Capture screenshot
        screenshot_result = await vnc_screenshot()
        if screenshot_result["status"] != "success":
            return {"status": "error", "found": False, "message": "Screenshot failed"}

        # Decode images
        screen_data = base64.b64decode(screenshot_result["image_data"])
        template_data = base64.b64decode(request.template_data)

        # Convert to cv2 images
        screen_array = np.frombuffer(screen_data, dtype=np.uint8)
        template_array = np.frombuffer(template_data, dtype=np.uint8)

        screen_img = cv2.imdecode(screen_array, cv2.IMREAD_COLOR)
        template_img = cv2.imdecode(template_array, cv2.IMREAD_COLOR)

        if screen_img is None or template_img is None:
            return {"status": "error", "found": False, "message": "Invalid image data"}

        # Template matching
        result = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= request.threshold:
            # Calculate center coordinates
            template_h, template_w = template_img.shape[:2]
            center_x = max_loc[0] + template_w // 2
            center_y = max_loc[1] + template_h // 2

            return {
                "status": "success",
                "found": True,
                "x": center_x,
                "y": center_y,
                "confidence": float(max_val),
                "message": "Template found",
            }
        else:
            return {
                "status": "success",
                "found": False,
                "confidence": float(max_val),
                "message": f"Template not found (best match: {max_val:.2f} < {request.threshold})",
            }

    except Exception as e:
        logger.error("Image template matching failed: %s", e)
        return {"status": "error", "found": False, "message": str(e)}


# Area 5: Automation Features - Wait Conditions


class WaitForTextRequest(BaseModel):
    """Wait for text to appear request"""

    text: str = Field(..., description="Text to wait for")
    timeout_seconds: int = Field(
        default=30, ge=1, le=300, description="Timeout in seconds"
    )
    region: Dict[str, int] = Field(
        default_factory=dict, description="Optional region to search"
    )


@router.post("/wait-for-text")
@with_error_handling(error_code_prefix="VNC_WAIT_TEXT")
async def vnc_wait_for_text(
    request: WaitForTextRequest, admin_check: bool = Depends(check_admin_permission)
) -> Dict[str, object]:
    """
    Wait for text to appear on screen using OCR.
    Issue #74 - Area 5: Automation Features.

    Args:
        request: WaitForTextRequest with text and timeout

    Returns:
        {"status": "success|timeout", "found": true/false, "message": "..."}
    """
    start_time = datetime.now()
    poll_interval = 2.0  # Check every 2 seconds

    while (datetime.now() - start_time).total_seconds() < request.timeout_seconds:
        # Perform OCR
        ocr_result = await vnc_ocr_text(OCRRequest(region=request.region))

        if ocr_result["status"] == "success":
            recognized_text = ocr_result["text"]

            if request.text.lower() in recognized_text.lower():
                return {
                    "status": "success",
                    "found": True,
                    "message": f"Text '{request.text}' found",
                }

        # Wait before next check
        await asyncio.sleep(poll_interval)

    return {
        "status": "timeout",
        "found": False,
        "message": f"Text '{request.text}' not found within {request.timeout_seconds}s",
    }


class WaitForImageRequest(BaseModel):
    """Wait for image to appear request"""

    template_data: str = Field(..., description="Base64-encoded template image")
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)


@router.post("/wait-for-image")
@with_error_handling(error_code_prefix="VNC_WAIT_IMAGE")
async def vnc_wait_for_image(
    request: WaitForImageRequest, admin_check: bool = Depends(check_admin_permission)
) -> Dict[str, object]:
    """
    Wait for image template to appear on screen.
    Issue #74 - Area 5: Automation Features.

    Args:
        request: WaitForImageRequest with template and timeout

    Returns:
        {
            "status": "success|timeout",
            "found": true/false,
            "x": center_x,
            "y": center_y,
            "message": "..."
        }
    """
    start_time = datetime.now()
    poll_interval = 2.0  # Check every 2 seconds

    while (datetime.now() - start_time).total_seconds() < request.timeout_seconds:
        # Find image
        find_result = await vnc_find_image(
            FindImageRequest(
                template_data=request.template_data, threshold=request.threshold
            )
        )

        if find_result["status"] == "success" and find_result["found"]:
            return {
                "status": "success",
                "found": True,
                "x": find_result["x"],
                "y": find_result["y"],
                "confidence": find_result["confidence"],
                "message": "Template found",
            }

        # Wait before next check
        await asyncio.sleep(poll_interval)

    return {
        "status": "timeout",
        "found": False,
        "message": f"Template not found within {request.timeout_seconds}s",
    }


# Area 6: Session-Tied Desktop Views


class DesktopSessionState(BaseModel):
    """Desktop state tied to a chat session"""

    session_id: str = Field(..., description="Chat session ID")
    window_layout: Dict = Field(
        default_factory=dict, description="Window positions and sizes"
    )
    active_applications: List[str] = Field(
        default_factory=list, description="Running applications"
    )
    screenshots: List[str] = Field(
        default_factory=list, description="Screenshot file paths"
    )
    action_log: List[Dict] = Field(
        default_factory=list, description="VNC actions performed"
    )
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat())


class SessionActionLog(BaseModel):
    """Log entry for VNC action in a session"""

    action_type: str = Field(..., description="Type of action performed")
    params: Dict = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    result: str = Field(default="success", description="Action result: success/error")


# Global session state storage (in-memory for now, should be Redis-backed in production)
_session_states: Dict[str, DesktopSessionState] = {}
_session_lock = asyncio.Lock()


@router.post("/session/save-state")
@with_error_handling(error_code_prefix="VNC_SESSION_SAVE")
async def save_session_desktop_state(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Save current desktop state to a chat session.
    Issue #74 - Area 6: Session-Tied Desktop Views.

    Args:
        session_id: Chat session ID

    Returns:
        {"status": "success|error", "message": "..."}
    """
    async with _session_lock:
        # Get or create session state
        if session_id not in _session_states:
            _session_states[session_id] = DesktopSessionState(session_id=session_id)

        state = _session_states[session_id]

        # Capture current desktop context
        context = await get_desktop_context()

        # Save window layout (from desktop info)
        if "desktop" in context:
            state.window_layout = context["desktop"]

        # Save running apps (from processes)
        if "processes" in context:
            state.active_applications = [
                proc["command"] for proc in context["processes"]
            ]

        # Update timestamp
        state.last_updated = datetime.now().isoformat()

        logger.info("Saved desktop state for session: %s", session_id)

    return {
        "status": "success",
        "message": f"Desktop state saved for session {session_id}",
    }


@router.get("/session/restore-state")
@with_error_handling(error_code_prefix="VNC_SESSION_RESTORE")
async def restore_session_desktop_state(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, object]:
    """
    Restore desktop state for a chat session.
    Issue #74 - Area 6: Session-Tied Desktop Views.

    Args:
        session_id: Chat session ID

    Returns:
        {
            "status": "success|not_found",
            "state": {...},  # Desktop state if found
            "message": "..."
        }
    """
    async with _session_lock:
        if session_id not in _session_states:
            return {
                "status": "not_found",
                "message": f"No saved state for session {session_id}",
            }

        state = _session_states[session_id]

    return {
        "status": "success",
        "state": state.dict(),
        "message": "Desktop state restored",
    }


@router.post("/session/log-action")
@with_error_handling(error_code_prefix="VNC_SESSION_LOG")
async def log_session_action(
    session_id: str,
    action: SessionActionLog,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Log a VNC action to a chat session.
    Issue #74 - Area 6: Session-Tied Desktop Views.

    Args:
        session_id: Chat session ID
        action: Action log entry

    Returns:
        {"status": "success", "message": "..."}
    """
    async with _session_lock:
        # Get or create session state
        if session_id not in _session_states:
            _session_states[session_id] = DesktopSessionState(session_id=session_id)

        state = _session_states[session_id]
        state.action_log.append(action.dict())
        state.last_updated = datetime.now().isoformat()

    return {"status": "success", "message": "Action logged to session"}


@router.get("/session/action-log")
@with_error_handling(error_code_prefix="VNC_SESSION_LOG_GET")
async def get_session_action_log(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, object]:
    """
    Get VNC action log for a chat session.
    Issue #74 - Area 6: Session-Tied Desktop Views.

    Args:
        session_id: Chat session ID

    Returns:
        {
            "status": "success|not_found",
            "actions": [...],  # Action log entries
            "message": "..."
        }
    """
    async with _session_lock:
        if session_id not in _session_states:
            return {
                "status": "not_found",
                "actions": [],
                "message": f"No action log for session {session_id}",
            }

        state = _session_states[session_id]
        actions = state.action_log

    return {
        "status": "success",
        "actions": actions,
        "message": f"Retrieved {len(actions)} actions",
    }


@router.post("/session/save-screenshot")
@with_error_handling(error_code_prefix="VNC_SESSION_SCREENSHOT")
async def save_session_screenshot(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Capture and save screenshot to a chat session.
    Issue #74 - Area 6: Session-Tied Desktop Views.

    Args:
        session_id: Chat session ID

    Returns:
        {
            "status": "success|error",
            "screenshot_path": "path/to/screenshot.png",
            "message": "..."
        }
    """
    # Capture screenshot
    screenshot_result = await vnc_screenshot()
    if screenshot_result["status"] != "success":
        return {"status": "error", "message": "Screenshot capture failed"}

    # Save screenshot to session-specific directory
    screenshot_dir = Path(f"/tmp/vnc_sessions/{session_id}")  # nosec B108
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = screenshot_dir / f"screenshot_{timestamp}.png"

    # Decode and save
    image_data = base64.b64decode(screenshot_result["image_data"])
    with open(screenshot_path, "wb") as f:
        f.write(image_data)

    # Add to session state
    async with _session_lock:
        if session_id not in _session_states:
            _session_states[session_id] = DesktopSessionState(session_id=session_id)

        state = _session_states[session_id]
        state.screenshots.append(str(screenshot_path))
        state.last_updated = datetime.now().isoformat()

    logger.info("Saved screenshot for session %s: %s", session_id, screenshot_path)

    return {
        "status": "success",
        "screenshot_path": str(screenshot_path),
        "message": "Screenshot saved to session",
    }


@router.get("/session/screenshots")
@with_error_handling(error_code_prefix="VNC_SESSION_SCREENSHOTS")
async def get_session_screenshots(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, object]:
    """
    Get all screenshots for a chat session.
    Issue #74 - Area 6: Session-Tied Desktop Views.

    Args:
        session_id: Chat session ID

    Returns:
        {
            "status": "success|not_found",
            "screenshots": ["path1.png", "path2.png", ...],
            "message": "..."
        }
    """
    async with _session_lock:
        if session_id not in _session_states:
            return {
                "status": "not_found",
                "screenshots": [],
                "message": f"No screenshots for session {session_id}",
            }

        state = _session_states[session_id]
        screenshots = state.screenshots

    return {
        "status": "success",
        "screenshots": screenshots,
        "message": f"Retrieved {len(screenshots)} screenshots",
    }


@router.delete("/session/clear-state")
@with_error_handling(error_code_prefix="VNC_SESSION_CLEAR")
async def clear_session_state(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
) -> Dict[str, str]:
    """
    Clear desktop state for a chat session.
    Issue #74 - Area 6: Session-Tied Desktop Views.

    Args:
        session_id: Chat session ID

    Returns:
        {"status": "success", "message": "..."}
    """
    async with _session_lock:
        if session_id in _session_states:
            del _session_states[session_id]
            logger.info("Cleared session state: %s", session_id)
            return {
                "status": "success",
                "message": f"Cleared state for session {session_id}",
            }
        else:
            return {"status": "success", "message": "No state to clear"}
