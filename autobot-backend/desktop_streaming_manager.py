# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Desktop Streaming Manager for AutoBot Phase 8.

Provides NoVNC integration and WebSocket-based desktop streaming capabilities
for remote desktop access and control.

Issue #358: Converted blocking subprocess.Popen to asyncio.create_subprocess_exec.
Issue #401: Improved code quality - proper imports, type hints, security fixes.
Issue #11639: Session metadata moved to Redis for cross-worker visibility;
    cross-worker broadcast via Redis pub/sub relay.
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import websockets

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import config
from config import config_manager
from constants.threshold_constants import TimingConstants
from task_execution_tracker import TaskPriority, get_task_tracker

# Type aliases for clarity
SessionDict = dict[str, Any]
ProcessType = asyncio.subprocess.Process

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Cross-worker constants — env-var-backed, never hard-coded (#11639)
# ---------------------------------------------------------------------------
_DESKTOP_EVENTS_CHANNEL: str = os.environ.get("AUTOBOT_DESKTOP_EVENTS_CHANNEL", "autobot:desktop:events")
_DESKTOP_SESSIONS_KEY: str = "autobot:desktop:sessions"  # HASH: session_id -> JSON metadata
_WORKER_ID: str = str(uuid.uuid4())  # unique per-process; set once at import time

# Performance optimization: O(1) lookup for VNC process keys (Issue #326)
ALL_VNC_PROCESS_KEYS: frozenset[str] = frozenset({"novnc_process", "vnc_process", "xvfb_process"})
CORE_VNC_PROCESS_KEYS: frozenset[str] = frozenset({"xvfb_process", "vnc_process"})


def _get_x_lock_directory() -> Path:
    """
    Get the directory for X display lock files.

    Issue #401: Security fix - use tempfile.gettempdir() instead of hardcoded /tmp.

    Returns:
        Path to the X lock file directory.
    """
    return Path(tempfile.gettempdir())


@dataclass
class VNCSessionData:
    """
    Data class for VNC session information.

    Issue #399: Reduces _build_session_data from 11 parameters to a single object.
    Groups all session-related data into a cohesive structure.
    """

    session_id: str
    user_id: str
    display_num: int
    vnc_port: int
    novnc_port: int
    resolution: str
    depth: int
    xvfb_process: asyncio.subprocess.Process
    vnc_process: asyncio.subprocess.Process
    novnc_process: asyncio.subprocess.Process | None = None
    created_at: float = field(default_factory=time.time)
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage in active_sessions."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "display_num": self.display_num,
            "vnc_port": self.vnc_port,
            "novnc_port": self.novnc_port,
            "resolution": self.resolution,
            "depth": self.depth,
            "created_at": self.created_at,
            "xvfb_process": self.xvfb_process,
            "vnc_process": self.vnc_process,
            "novnc_process": self.novnc_process,
            "status": self.status,
        }


def _terminate_process_safely(process: subprocess.Popen[bytes] | None, process_key: str) -> bool:
    """
    Terminate a process safely with fallback to kill.

    Issue #315: Extracted from inline code.

    Args:
        process: The subprocess to terminate.
        process_key: Name of the process for logging.

    Returns:
        True if termination succeeded, False otherwise.
    """
    if not process:
        return False
    try:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        return True
    except OSError as e:
        logger.warning("Error terminating %s: %s", process_key, e)
        return False


async def _terminate_async_process_safely(process: ProcessType | None, process_key: str) -> bool:
    """
    Terminate an async subprocess safely.

    Issue #358: Async process handling.

    Args:
        process: The async subprocess to terminate.
        process_key: Name of the process for logging.

    Returns:
        True if termination succeeded, False otherwise.
    """
    if not process:
        return False
    try:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        return True
    except OSError as e:
        logger.warning("Error terminating async %s: %s", process_key, e)
        return False


async def _run_xdotool_command(display: int, *args: str) -> bool:
    """
    Run xdotool command on specified display.

    Issue #315: Extracted from inline code.

    Args:
        display: X11 display number.
        *args: xdotool command arguments.

    Returns:
        True if command succeeded, False otherwise.
    """
    try:
        env = {
            **config_manager.get("system.environment", os.environ),
            "DISPLAY": f":{display}",
        }
        proc = await asyncio.create_subprocess_exec("xdotool", *args, env=env)
        await proc.wait()
        return proc.returncode == 0
    except OSError as e:
        logger.error("xdotool command failed: %s", e)
        return False


class VNCServerManager:
    """
    Manages VNC server instances for desktop streaming.

    Provides lifecycle management for Xvfb, x11vnc, and NoVNC processes,
    including session creation, termination, and cleanup.

    Attributes:
        display_base: Starting X display number.
        port_base: Starting VNC port number.
        novnc_port_base: Starting NoVNC port number.
        active_sessions: Dictionary of active VNC sessions.
        vnc_available: Whether VNC server is available.
        novnc_available: Whether NoVNC is available.
    """

    def __init__(
        self,
        display_base: int = 10,
        port_base: int = 5900,
        novnc_port_base: int = 6080,
    ) -> None:
        """
        Initialize VNC server manager.

        Args:
            display_base: Starting X display number (default: 10).
            port_base: Starting VNC port (default: 5900).
            novnc_port_base: Starting NoVNC port (default: 6080).
        """
        self.display_base = display_base
        self.port_base = port_base
        self.novnc_port_base = novnc_port_base
        self.active_sessions: dict[str, SessionDict] = {}

        # Check for VNC server availability
        self.vnc_available = self._check_vnc_availability()
        self.novnc_available = self._check_novnc_availability()

        logger.info(
            "VNC Server Manager initialized: VNC=%s, NoVNC=%s",
            self.vnc_available,
            self.novnc_available,
        )

    def _check_vnc_availability(self) -> bool:
        """
        Check if VNC server components are available.

        Issue #401: Uses shutil.which() instead of subprocess for security.

        Returns:
            True if VNC or Xvfb is available, False otherwise.
        """
        # Check for tigervnc or tightvnc using shutil.which (more secure)
        if shutil.which("vncserver"):
            return True
        # Check for Xvfb (alternative)
        return shutil.which("Xvfb") is not None

    def _check_novnc_availability(self) -> bool:
        """
        Check if NoVNC components are available.

        Returns:
            True if NoVNC is found, False otherwise.
        """
        # Common NoVNC installation paths. #13076: /usr/share/novnc dropped —
        # roles/vnc removes that distro package (#13069), and where it survives
        # it serves a stale pre-VeNCrypt 1.0.0 client (#13060). config.path.novnc_path
        # is the canonical install location (default /opt/novnc).
        novnc_paths = [config.path.novnc_path, "~/novnc", "./novnc"]

        for path in novnc_paths:
            if Path(path).expanduser().exists():
                return True

        return False

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        resolution: str = "1024x768",
        depth: int = 24,
    ) -> SessionDict:
        """
        Create a new VNC session for desktop streaming.

        Issue #281: Refactored to use extracted helpers.
        Issue #398: Further refactored to reduce method length.

        Args:
            session_id: Unique session identifier.
            user_id: User requesting the session.
            resolution: Display resolution (default: "1024x768").
            depth: Color depth in bits (default: 24).

        Returns:
            Dictionary with session connection details.

        Raises:
            RuntimeError: If VNC is not available or session creation fails.
        """
        async with get_task_tracker().track_task(
            "Create VNC Session",
            f"Creating desktop streaming session for user {user_id}",
            agent_type="desktop_streaming",
            priority=TaskPriority.HIGH,
            inputs={
                "session_id": session_id,
                "user_id": user_id,
                "resolution": resolution,
            },
        ) as task_context:
            return await self._create_session_impl(session_id, user_id, resolution, depth, task_context)

    async def _create_session_impl(
        self,
        session_id: str,
        user_id: str,
        resolution: str,
        depth: int,
        task_context: Any,
    ) -> SessionDict:
        """
        Internal implementation of session creation.

        Issue #398: Extracted from create_session to reduce method length.

        Args:
            session_id: Unique session identifier.
            user_id: User requesting the session.
            resolution: Display resolution.
            depth: Color depth in bits.
            task_context: Task tracking context.

        Returns:
            Dictionary with session connection details.
        """
        if not self.vnc_available:
            error_msg = "VNC server not available on system"
            task_context.set_outputs({"error": error_msg})
            raise RuntimeError(error_msg)

        display_num = self._find_available_display()
        vnc_port = self.port_base + display_num
        novnc_port = self.novnc_port_base + display_num

        try:
            vnc_session = await self._start_vnc_stack(
                session_id,
                user_id,
                display_num,
                vnc_port,
                novnc_port,
                resolution,
                depth,
            )
            self.active_sessions[session_id] = self._build_session_data(vnc_session)

            outputs = self._build_session_output(session_id, display_num, vnc_port, novnc_port)
            task_context.set_outputs(outputs)
            logger.info("VNC session created: %s on display :%d", session_id, display_num)
            return outputs

        except Exception as e:
            logger.error("Failed to create VNC session: %s", e)
            task_context.set_outputs({"error": "VNC session creation failed"})
            raise RuntimeError("Failed to create VNC session") from e

    async def _start_vnc_stack(
        self,
        session_id: str,
        user_id: str,
        display_num: int,
        vnc_port: int,
        novnc_port: int,
        resolution: str,
        depth: int,
    ) -> VNCSessionData:
        """
        Start the complete VNC stack (Xvfb, VNC server, NoVNC).

        Issue #398: Extracted from create_session to reduce method length.

        Args:
            session_id: Session identifier.
            user_id: User ID.
            display_num: X display number.
            vnc_port: VNC server port.
            novnc_port: NoVNC web port.
            resolution: Display resolution.
            depth: Color depth.

        Returns:
            VNCSessionData with all process references.
        """
        xvfb_process = await self._start_xvfb(display_num, resolution, depth)
        vnc_process = await self._start_vnc_server(display_num, vnc_port)
        novnc_process = await self._start_novnc(vnc_port, novnc_port) if self.novnc_available else None

        return VNCSessionData(
            session_id=session_id,
            user_id=user_id,
            display_num=display_num,
            vnc_port=vnc_port,
            novnc_port=novnc_port,
            resolution=resolution,
            depth=depth,
            xvfb_process=xvfb_process,
            vnc_process=vnc_process,
            novnc_process=novnc_process,
        )

    def _find_websockify_command(self) -> str | None:
        """
        Find websockify executable path.

        Issue #398: Extracted from _start_novnc to reduce method length.
        Issue #401: Uses shutil.which for security.

        Returns:
            Path to websockify, or None if not found.
        """
        websockify_cmd = shutil.which("websockify")
        if websockify_cmd:
            return websockify_cmd

        # Check additional paths if not in PATH
        additional_paths = ["/usr/bin/websockify", "/usr/local/bin/websockify"]
        for path in additional_paths:
            expanded = Path(path).expanduser()
            if expanded.exists():
                return str(expanded)

        return None

    async def _start_novnc(self, vnc_port: int, novnc_port: int) -> ProcessType | None:
        """
        Start NoVNC web proxy.

        Issue #398: Refactored to extract websockify lookup.

        Args:
            vnc_port: VNC server port to proxy.
            novnc_port: NoVNC web port.

        Returns:
            The NoVNC process, or None if unavailable.
        """
        try:
            websockify_cmd = self._find_websockify_command()
            if not websockify_cmd:
                logger.warning("Websockify not found, NoVNC will not be available")
                return None

            novnc_command = [
                websockify_cmd,
                "--web",
                config.path.novnc_path,
                "--cert=/etc/autobot/certs/server-cert.pem",
                "--key=/etc/autobot/certs/server-key.pem",
                "--ssl-only",
                f"localhost:{novnc_port}",
                f"localhost:{vnc_port}",
            ]

            novnc_process = await asyncio.create_subprocess_exec(
                *novnc_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            logger.info("NoVNC started on port %d", novnc_port)
            return novnc_process

        except OSError as e:
            logger.error("Failed to start NoVNC: %s", e)
            return None

    def _find_available_display(self) -> int:
        """
        Find an available X display number.

        Issue #401: Uses tempfile.gettempdir() instead of hardcoded /tmp.

        Returns:
            Available X display number.

        Raises:
            RuntimeError: If no display is available.
        """
        lock_dir = _get_x_lock_directory()
        for i in range(self.display_base, self.display_base + 100):
            lock_file = lock_dir / f".X{i}-lock"
            if not lock_file.exists():
                return i

        raise RuntimeError("No available X display numbers")

    async def _start_xvfb(self, display_num: int, resolution: str, depth: int) -> ProcessType:
        """
        Start Xvfb virtual display.

        Issue #281: Extracted helper method.

        Args:
            display_num: X display number.
            resolution: Display resolution.
            depth: Color depth.

        Returns:
            The Xvfb subprocess.
        """
        xvfb_command = [
            "Xvfb",
            f":{display_num}",
            "-screen",
            "0",
            f"{resolution}x{depth}",
            "-nolisten",
            "tcp",
            "-dpi",
            "96",
        ]

        xvfb_process = await asyncio.create_subprocess_exec(
            *xvfb_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for display to be ready
        await asyncio.sleep(TimingConstants.STANDARD_DELAY)
        return xvfb_process

    async def _start_vnc_server(self, display_num: int, vnc_port: int) -> ProcessType:
        """
        Start VNC server on display.

        Issue #281: Extracted helper method.

        Args:
            display_num: X display number.
            vnc_port: VNC server port.

        Returns:
            The VNC server subprocess.
        """
        vnc_command = [
            "x11vnc",
            "-display",
            f":{display_num}",
            "-rfbport",
            str(vnc_port),
            "-rfbauth",
            str(config.path.vnc_passwd_path),
            "-shared",
            "-forever",
            "-noxdamage",
            "-noxfixes",
            "-noxcomposite",
        ]

        return await asyncio.create_subprocess_exec(
            *vnc_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    def _build_session_data(self, session_data: VNCSessionData) -> SessionDict:
        """
        Build session data dictionary from VNCSessionData.

        Issue #281: Extracted helper method.
        Issue #399: Reduced from 11 parameters to 1 using VNCSessionData dataclass.

        Args:
            session_data: VNCSessionData object containing all session information.

        Returns:
            Dictionary representation for storage in active_sessions.
        """
        return session_data.to_dict()

    def _build_session_output(self, session_id: str, display_num: int, vnc_port: int, novnc_port: int) -> SessionDict:
        """
        Build session output dictionary.

        Issue #281: Extracted helper method.

        Args:
            session_id: Session identifier.
            display_num: X display number.
            vnc_port: VNC port.
            novnc_port: NoVNC port.

        Returns:
            Dictionary with connection details.
        """
        return {
            "session_id": session_id,
            "vnc_port": vnc_port,
            "novnc_port": novnc_port if self.novnc_available else None,
            "display": f":{display_num}",
            "vnc_url": f"vnc://localhost:{vnc_port}",
            "web_url": (f"http://localhost:{novnc_port}" if self.novnc_available else None),
        }

    async def terminate_session(self, session_id: str) -> bool:
        """
        Terminate a VNC session.

        Issue #315, #358: Async process handling.

        Args:
            session_id: Session to terminate.

        Returns:
            True if termination succeeded, False otherwise.
        """
        if session_id not in self.active_sessions:
            return False

        session = self.active_sessions[session_id]

        try:
            # Terminate all VNC processes using async helper (Issue #358)
            for process_key in ALL_VNC_PROCESS_KEYS:
                process = session.get(process_key)
                if process:
                    await _terminate_async_process_safely(process, process_key)

            del self.active_sessions[session_id]
            logger.info("VNC session terminated: %s", session_id)
            return True
        except OSError as e:
            logger.error("Error terminating session %s: %s", session_id, e)
            return False

    def get_session_info(self, session_id: str) -> SessionDict | None:
        """
        Get information about a VNC session.

        Args:
            session_id: Session to query.

        Returns:
            Session info dictionary, or None if not found.
        """
        if session_id not in self.active_sessions:
            return None

        session = self.active_sessions[session_id].copy()
        # Remove process objects from returned data
        for key in ALL_VNC_PROCESS_KEYS:
            session.pop(key, None)

        return session

    def list_active_sessions(self) -> list[SessionDict]:
        """
        List all active VNC sessions.

        Returns:
            List of session info dictionaries.
        """
        sessions = []
        for session_id in self.active_sessions:
            session_info = self.get_session_info(session_id)
            if session_info:
                sessions.append(session_info)

        return sessions

    async def cleanup_stale_sessions(self) -> int:
        """
        Clean up stale or orphaned sessions.

        Returns:
            Number of sessions cleaned up.
        """
        cleanup_count = 0
        stale_sessions: list[str] = []

        for session_id, session_data in self.active_sessions.items():
            if not self._has_running_processes(session_data):
                stale_sessions.append(session_id)

        # Cleanup stale sessions
        for session_id in stale_sessions:
            await self.terminate_session(session_id)
            cleanup_count += 1

        if cleanup_count > 0:
            logger.info("Cleaned up %d stale VNC sessions", cleanup_count)

        return cleanup_count

    def _has_running_processes(self, session_data: SessionDict) -> bool:
        """
        Check if session has running core processes.

        Args:
            session_data: Session data dictionary.

        Returns:
            True if any core process is running, False otherwise.
        """
        for process_key in CORE_VNC_PROCESS_KEYS:
            process = session_data.get(process_key)
            if process and process.returncode is None:
                return True
        return False


class DesktopStreamingManager:
    """
    High-level desktop streaming manager with WebSocket integration.

    Provides a unified interface for creating and managing desktop streaming
    sessions with VNC backend and WebSocket client communication.

    Issue #11639: session metadata (active_sessions) stored in Redis so every
    worker can list/validate sessions.  WebSocket connection objects stay
    per-worker in session_clients (sockets cannot be serialized).
    Cross-worker broadcast: publish events to Redis pub/sub; a background
    subscriber relays foreign events to local WebSocket clients.

    Attributes:
        vnc_manager: VNC server manager instance.
        websocket_clients: Connected WebSocket clients (per-worker).
        session_clients: Mapping of session IDs to client IDs (per-worker).
    """

    def __init__(self, _redis=None) -> None:
        """Initialize desktop streaming manager.

        Args:
            _redis: Optional Redis client override (for tests / single-worker dev).
        """
        self.vnc_manager = VNCServerManager()
        self.websocket_clients: dict[str, websockets.WebSocketServerProtocol] = {}
        self.session_clients: dict[str, list[str]] = {}
        self._redis = _redis  # None = use get_async_redis_client(); set in tests
        # H2: per-process latch — once any Redis op fails, stay in fallback mode.
        # None = not yet probed; True = working; False = latched to fallback.
        self._redis_available: bool | None = None
        self._redis_warning_logged = False
        self._subscriber_task: asyncio.Task | None = None

        logger.info("Desktop Streaming Manager initialized (worker=%s)", _WORKER_ID)

    # ------------------------------------------------------------------
    # Lifecycle (start/stop subscriber)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the cross-worker pub/sub subscriber task."""
        if self._subscriber_task is None or self._subscriber_task.done():
            self._subscriber_task = asyncio.create_task(self._pubsub_relay_loop(), name="desktop-pubsub-relay")
            # Register for construct-free shutdown via stop_desktop_relay()
            global _relay_manager
            _relay_manager = self
            logger.info("Desktop streaming pub/sub relay started (worker=%s)", _WORKER_ID)

    async def stop(self) -> None:
        """Stop the cross-worker pub/sub subscriber task."""
        if self._subscriber_task and not self._subscriber_task.done():
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                pass
            self._subscriber_task = None
            logger.info("Desktop streaming pub/sub relay stopped (worker=%s)", _WORKER_ID)

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """Return a Redis client, or None if unavailable."""
        if self._redis is not None:
            return self._redis
        try:
            from autobot_shared.redis_client import get_async_redis_client

            return await get_async_redis_client()
        except Exception:
            return None

    async def _redis_client(self):
        """Return a usable Redis client, or None when latched to fallback.

        H2: Once any Redis op raises, _redis_available is set False and we
        stay in local-only mode for the lifetime of this worker process.
        """
        if self._redis_available is False:
            return None
        r = await self._get_redis()
        if r is None:
            if not self._redis_warning_logged:
                logger.warning(
                    "DesktopStreamingManager: Redis unavailable — sessions not shared "
                    "across workers; cross-worker broadcast disabled"
                )
                self._redis_warning_logged = True
            self._redis_available = False
            return None
        if self._redis_available is None:
            self._redis_available = True
        return r

    def _latch_redis_fallback(self, exc: Exception) -> None:
        """H2: Log once and latch this process to local-only mode."""
        if self._redis_available is not False:
            logger.warning(
                "DesktopStreamingManager: Redis op failed (%s) — latching to local-only "
                "mode for the lifetime of this worker",
                exc,
            )
            self._redis_available = False

    # ------------------------------------------------------------------
    # Session metadata (Redis-backed)
    # ------------------------------------------------------------------

    async def _meta_set(self, session_id: str, meta: dict) -> None:
        """Store session metadata in Redis hash."""
        r = await self._redis_client()
        if r is None:
            return
        try:
            await r.hset(_DESKTOP_SESSIONS_KEY, session_id, json.dumps(meta, ensure_ascii=False))
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)

    async def _meta_get(self, session_id: str) -> dict | None:
        """Retrieve session metadata from Redis hash."""
        r = await self._redis_client()
        if r is None:
            return None
        try:
            raw = await r.hget(_DESKTOP_SESSIONS_KEY, session_id)
            if raw is None:
                return None
            return json.loads(raw)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return None

    async def _meta_delete(self, session_id: str) -> None:
        """Remove session metadata from Redis hash."""
        r = await self._redis_client()
        if r is None:
            return
        try:
            await r.hdel(_DESKTOP_SESSIONS_KEY, session_id)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)

    async def _meta_all(self) -> dict[str, dict]:
        """Return all session metadata from Redis."""
        r = await self._redis_client()
        if r is None:
            return {}
        try:
            raw_map = await r.hgetall(_DESKTOP_SESSIONS_KEY)
            result = {}
            for k, v in raw_map.items():
                key = k.decode() if isinstance(k, bytes) else k
                result[key] = json.loads(v)
            return result
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)
            return {}

    # ------------------------------------------------------------------
    # Cross-worker broadcast (pub/sub)
    # ------------------------------------------------------------------

    async def _publish_event(self, event_type: str, payload: dict) -> None:
        """Publish a desktop event to all workers via Redis pub/sub."""
        r = await self._redis_client()
        if r is None:
            return
        msg = json.dumps(
            {"worker_id": _WORKER_ID, "type": event_type, "payload": payload},
            ensure_ascii=False,
        )
        try:
            await r.publish(_DESKTOP_EVENTS_CHANNEL, msg)
        except (ConnectionError, TimeoutError, OSError) as exc:
            self._latch_redis_fallback(exc)

    async def _pubsub_relay_loop(self) -> None:
        """Subscribe to desktop events and relay foreign ones to local clients.

        M5: sleep on clean return too (prevents hot-loop when the subscription
        ends immediately, e.g. when the fake stub's listen() drains in tests).
        """
        _RETRY_DELAY = 5
        while True:
            try:
                await self._run_pubsub_subscription()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    "Desktop pub/sub relay error (worker=%s): %s — retrying in %ds",
                    _WORKER_ID,
                    e,
                    _RETRY_DELAY,
                )
            # M5: always sleep between subscription passes (error or clean exit)
            await asyncio.sleep(_RETRY_DELAY)

    async def _run_pubsub_subscription(self) -> None:
        """Run one pub/sub subscription session (called from relay loop).

        M5: wrap unsubscribe and close each in separate try/except so a
        failure in one does not skip the other.  Use aclose() when available.
        """
        r = await self._get_redis()
        if r is None:
            return
        pubsub = r.pubsub()
        await pubsub.subscribe(_DESKTOP_EVENTS_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                await self._handle_pubsub_message(message.get("data", b""))
        finally:
            try:
                await pubsub.unsubscribe(_DESKTOP_EVENTS_CHANNEL)
            except Exception as e:
                logger.warning("Desktop pubsub unsubscribe error (worker=%s): %s", _WORKER_ID, e)
            try:
                # M5: prefer aclose() when available (redis-py >= 4.2)
                close_fn = getattr(pubsub, "aclose", None) or pubsub.close
                await close_fn()
            except Exception as e:
                logger.warning("Desktop pubsub close error (worker=%s): %s", _WORKER_ID, e)

    async def _handle_pubsub_message(self, data: bytes | str) -> None:
        """Relay a received pub/sub message to local clients if from another worker.

        H3: Handles the special 'session_terminate_requested' event: if this
        worker owns the session locally it runs the full local terminate path
        (kill processes, notify clients, delete Redis metadata, publish
        'session_terminated').  All other message types are relayed to local
        WebSocket clients as before.
        """
        try:
            msg = json.loads(data)
            if msg.get("worker_id") == _WORKER_ID:
                return  # local event already delivered directly
            msg_type = msg.get("type", "")
            session_id = msg.get("payload", {}).get("session_id", "")

            if msg_type == "session_terminate_requested":
                # H3: only act if this worker owns the session
                if session_id in self.session_clients or session_id in self.vnc_manager.active_sessions:
                    logger.info(
                        "Desktop relay: terminate_requested for owned session %s (worker=%s)",
                        session_id,
                        _WORKER_ID,
                    )
                    await self._local_terminate(session_id)
                return

            if session_id not in self.session_clients:
                return
            outbound = json.dumps({"type": msg_type, "data": msg["payload"]})
            await self._broadcast_to_local_clients(session_id, outbound)
        except Exception as e:
            logger.warning("Desktop pub/sub message decode error: %s", e)

    async def _local_terminate(self, session_id: str) -> None:
        """Full local terminate: kill processes, notify clients, delete metadata.

        H3: Used by the pub/sub relay when this worker is the session owner and
        another worker requested termination.
        """
        if session_id in self.session_clients:
            await self._notify_session_clients_terminated(session_id)
            del self.session_clients[session_id]
        await self._meta_delete(session_id)
        await self.vnc_manager.terminate_session(session_id)
        await self._publish_event("session_terminated", {"session_id": session_id})
        logger.info("Desktop relay: locally terminated session %s (worker=%s)", session_id, _WORKER_ID)

    async def create_streaming_session(self, user_id: str, session_config: SessionDict | None = None) -> SessionDict:
        """
        Create a new desktop streaming session.

        Issue #11639: Session metadata also written to Redis so other workers
        can validate sessions without a local entry.

        Args:
            user_id: User requesting the session.
            session_config: Optional configuration overrides.

        Returns:
            Dictionary with session details and endpoints.
        """
        cfg = session_config or {}
        session_id = f"stream_{user_id}_{int(time.time())}"

        # Lazy-start the cross-worker relay with the first session (#11639) —
        # idempotent; avoids a standing Redis subscription on idle backends.
        await self.start()

        # Create VNC session
        vnc_info = await self.vnc_manager.create_session(
            session_id=session_id,
            user_id=user_id,
            resolution=cfg.get("resolution", "1024x768"),
            depth=cfg.get("depth", 24),
        )

        # Initialize per-worker client tracking
        self.session_clients[session_id] = []

        # Persist metadata to Redis for cross-worker visibility (#11639)
        meta = {
            "session_id": session_id,
            "user_id": user_id,
            "worker_id": _WORKER_ID,
            "created_at": time.time(),
            **{k: v for k, v in vnc_info.items() if isinstance(v, (str, int, float, bool, type(None)))},
        }
        await self._meta_set(session_id, meta)

        return {
            **vnc_info,
            "streaming_available": True,
            "websocket_endpoint": f"/ws/desktop/{session_id}",
        }

    async def handle_websocket_client(self, websocket: websockets.WebSocketServerProtocol, path: str) -> None:
        """
        Handle WebSocket connections for desktop streaming.

        Issue #401: Refactored to reduce complexity from C(11) to A.

        Args:
            websocket: WebSocket connection.
            path: Connection path.
        """
        client_id = ""
        session_id = ""

        try:
            # Validate and extract session (Issue #401: extracted)
            session_id = self._extract_session_from_path(path)
            if not session_id:
                await websocket.close(code=1008, reason="Invalid path")
                return

            if not self._validate_session(session_id):
                await websocket.close(code=1008, reason="Session not found")
                return

            # Register client
            client_id = self._register_client(websocket, session_id)
            logger.info("WebSocket client connected: %s to session %s", client_id, session_id)

            # Send initial session info
            await self._send_session_info(websocket, session_id)

            # Handle client messages
            async for message in websocket:
                await self._handle_client_message(client_id, session_id, message)

        except websockets.exceptions.ConnectionClosed:
            if client_id:
                logger.info("WebSocket client disconnected: %s", client_id)
        except Exception as e:
            logger.error("WebSocket error: %s", e)
        finally:
            self._cleanup_client(client_id, session_id)

    def _extract_session_from_path(self, path: str) -> str:
        """
        Extract session ID from WebSocket path.

        Args:
            path: WebSocket connection path.

        Returns:
            Session ID, or empty string if invalid.
        """
        path_parts = path.strip("/").split("/")
        if len(path_parts) >= 3 and path_parts[1] == "desktop":
            return path_parts[2]
        return ""

    def _validate_session(self, session_id: str) -> bool:
        """
        Validate that session exists locally (per-worker check).

        Issue #11639: For cross-worker validation use _validate_session_redis().
        Local check is sufficient for WebSocket path since the WS connects to
        the worker that owns the session.

        Args:
            session_id: Session to validate.

        Returns:
            True if session exists locally, False otherwise.
        """
        return session_id in self.session_clients

    def _register_client(self, websocket: websockets.WebSocketServerProtocol, session_id: str) -> str:
        """
        Register a WebSocket client.

        Args:
            websocket: WebSocket connection.
            session_id: Session to join.

        Returns:
            Generated client ID.
        """
        client_id = f"client_{id(websocket)}"
        self.websocket_clients[client_id] = websocket
        self.session_clients[session_id].append(client_id)
        return client_id

    def _cleanup_client(self, client_id: str, session_id: str) -> None:
        """
        Clean up client on disconnect.

        Args:
            client_id: Client to clean up.
            session_id: Session the client was in.
        """
        if client_id in self.websocket_clients:
            del self.websocket_clients[client_id]
        if session_id in self.session_clients:
            clients = self.session_clients[session_id]
            if client_id in clients:
                clients.remove(client_id)

    async def _send_session_info(self, websocket: websockets.WebSocketServerProtocol, session_id: str) -> None:
        """
        Send initial session info to client.

        Args:
            websocket: WebSocket connection.
            session_id: Session ID.
        """
        session_info = self.vnc_manager.get_session_info(session_id)
        if session_info:
            await websocket.send(json.dumps({"type": "session_info", "data": session_info}))

    async def _handle_client_message(self, client_id: str, session_id: str, message: str) -> None:
        """
        Handle messages from WebSocket clients.

        Args:
            client_id: Sending client.
            session_id: Client's session.
            message: JSON message.
        """
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "control_request":
                await self._handle_control_request(session_id, data.get("data", {}))
            elif msg_type == "get_screenshot":
                await self._send_screenshot(client_id, session_id)
            elif msg_type == "session_status":
                await self._send_session_status(client_id, session_id)

        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON from client %s: %s", client_id, e)
        except Exception as e:
            logger.error("Error handling client message: %s", e)

    async def _send_screenshot(self, client_id: str, session_id: str) -> None:
        """
        Send screenshot to client.

        Args:
            client_id: Requesting client.
            session_id: Session to screenshot.
        """
        screenshot_data = await self._get_session_screenshot(session_id)
        if screenshot_data and client_id in self.websocket_clients:
            await self.websocket_clients[client_id].send(json.dumps({"type": "screenshot", "data": screenshot_data}))

    async def _send_session_status(self, client_id: str, session_id: str) -> None:
        """
        Send session status to client.

        Args:
            client_id: Requesting client.
            session_id: Session to query.
        """
        if client_id in self.websocket_clients:
            status = self.vnc_manager.get_session_info(session_id)
            await self.websocket_clients[client_id].send(json.dumps({"type": "session_status", "data": status}))

    async def _handle_control_request(self, session_id: str, control_data: SessionDict) -> None:
        """
        Handle desktop control requests.

        Issue #315: Refactored to reduce nesting.

        Args:
            session_id: Target session.
            control_data: Control command data.
        """
        session_info = self.vnc_manager.get_session_info(session_id)
        if not session_info:
            return

        display = session_info["display_num"]
        control_type = control_data.get("type")

        if control_type == "mouse_click":
            await self._handle_mouse_click(display, control_data)
        elif control_type == "key_press":
            await self._handle_key_press(display, control_data)
        elif control_type == "type_text":
            await self._handle_type_text(display, control_data)

    async def _handle_mouse_click(self, display: int, control_data: SessionDict) -> None:
        """Handle mouse click control."""
        x, y = control_data.get("x", 0), control_data.get("y", 0)
        button = control_data.get("button", 1)
        await _run_xdotool_command(display, "mousemove", "--sync", str(x), str(y), "click", str(button))

    async def _handle_key_press(self, display: int, control_data: SessionDict) -> None:
        """Handle key press control."""
        key = control_data.get("key", "")
        if key:
            await _run_xdotool_command(display, "key", key)

    async def _handle_type_text(self, display: int, control_data: SessionDict) -> None:
        """Handle type text control."""
        text = control_data.get("text", "")
        if text:
            await _run_xdotool_command(display, "type", text)

    async def _get_session_screenshot(self, session_id: str) -> str | None:
        """
        Get screenshot from desktop session.

        Args:
            session_id: Session to screenshot.

        Returns:
            Base64-encoded PNG, or None on failure.
        """
        session_info = self.vnc_manager.get_session_info(session_id)
        if not session_info:
            return None

        try:
            display = session_info["display_num"]

            # Use imagemagick to capture screenshot
            proc = await asyncio.create_subprocess_exec(
                "import",
                "-window",
                "root",
                "-display",
                f":{display}",
                "png:-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if proc.returncode == 0:
                return base64.b64encode(stdout).decode("utf-8")

        except OSError as e:
            logger.error("Screenshot capture failed: %s", e)

        return None

    async def _broadcast_to_local_clients(self, session_id: str, message: str) -> None:
        """Send a message to all local WebSocket clients for a session.

        Args:
            session_id: Target session.
            message: JSON string to send.
        """
        for client_id in list(self.session_clients.get(session_id, [])):
            if client_id not in self.websocket_clients:
                continue
            try:
                await self.websocket_clients[client_id].send(message)
            except Exception as e:
                logger.warning("Error sending to client %s: %s", client_id, e)

    async def list_all_sessions(self) -> list[dict]:
        """List sessions from all workers via Redis metadata.

        Returns per-worker local sessions when Redis is unavailable.
        """
        meta_map = await self._meta_all()
        if meta_map:
            return list(meta_map.values())
        # Fallback: local sessions only
        return [{"session_id": sid} for sid in self.session_clients]

    async def terminate_streaming_session(self, session_id: str) -> bool:
        """
        Terminate a desktop streaming session.

        Issue #315: Refactored.
        Issue #11639: Also removes Redis metadata and publishes termination event.

        H3: If this worker does NOT own the session locally (not in
        session_clients or vnc_manager.active_sessions) we publish a
        'session_terminate_requested' event so the owner worker handles the
        local teardown (process kills + client notification) and returns True
        (accepted).  The owner's relay loop calls _local_terminate which then
        publishes 'session_terminated' and deletes the metadata.

        Args:
            session_id: Session to terminate.

        Returns:
            True if termination succeeded or was accepted, False otherwise.
        """
        locally_owned = session_id in self.session_clients or session_id in self.vnc_manager.active_sessions

        if not locally_owned:
            # H3: delegate to the owner worker via pub/sub
            meta = await self._meta_get(session_id)
            if meta is None:
                return False
            logger.info(
                "terminate_streaming_session: session %s not local — " "publishing terminate_requested (worker=%s)",
                session_id,
                _WORKER_ID,
            )
            await self._publish_event("session_terminate_requested", {"session_id": session_id})
            return True  # accepted; owner will complete teardown asynchronously

        # Owner path: local teardown
        if session_id in self.session_clients:
            await self._notify_session_clients_terminated(session_id)
            del self.session_clients[session_id]

        # Remove Redis metadata (#11639)
        await self._meta_delete(session_id)

        # Publish termination for other workers' relay loops
        await self._publish_event("session_terminated", {"session_id": session_id})

        # Terminate VNC session
        return await self.vnc_manager.terminate_session(session_id)

    async def _notify_session_clients_terminated(self, session_id: str) -> None:
        """
        Notify clients that session is terminated.

        Issue #315: Extracted method.

        Args:
            session_id: Terminated session.
        """
        termination_msg = json.dumps({"type": "session_terminated", "data": {"session_id": session_id}})
        for client_id in list(self.session_clients.get(session_id, [])):
            await self._notify_client_and_close(client_id, termination_msg)

    async def _notify_client_and_close(self, client_id: str, message: str) -> None:
        """
        Notify a client and close connection.

        Issue #315: Extracted method.

        Args:
            client_id: Client to notify.
            message: Message to send.
        """
        if client_id not in self.websocket_clients:
            return
        try:
            await self.websocket_clients[client_id].send(message)
            await self.websocket_clients[client_id].close()
        except Exception as e:
            logger.warning("Error notifying client %s: %s", client_id, e)

    def get_system_capabilities(self) -> SessionDict:
        """
        Get desktop streaming system capabilities.

        Returns:
            Dictionary of system capabilities.
        """
        return {
            "vnc_available": self.vnc_manager.vnc_available,
            "novnc_available": self.vnc_manager.novnc_available,
            "active_sessions": len(self.vnc_manager.active_sessions),
            "connected_clients": len(self.websocket_clients),
            "max_concurrent_sessions": 10,
            "supported_features": [
                "screen_sharing",
                "remote_control",
                "screenshot_capture",
                "websocket_streaming",
            ],
        }


get_desktop_streaming = lazy_singleton(DesktopStreamingManager)

# Set by DesktopStreamingManager.start(); lets shutdown stop the relay
# WITHOUT constructing a manager when none was ever used (#11639).
_relay_manager: DesktopStreamingManager | None = None


async def stop_desktop_relay() -> None:
    """Stop the cross-worker pub/sub relay if one was started (#11639)."""
    global _relay_manager
    if _relay_manager is not None:
        await _relay_manager.stop()
        _relay_manager = None
