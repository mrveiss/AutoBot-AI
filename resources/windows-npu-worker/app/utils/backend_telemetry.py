# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backend Telemetry Client for Windows NPU Worker

Sends heartbeat and telemetry data to the main AutoBot backend.
Enables active registration and status reporting.

Issue #68: NPU worker telemetry implementation
"""

import asyncio
import logging
import socket
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class BackendTelemetryClient:
    """
    Client for sending telemetry to AutoBot backend.

    Features:
    - Periodic heartbeat sending
    - Auto-registration with backend
    - Prometheus/OpenTelemetry integration support
    - Graceful reconnection on failures
    """

    def __init__(
        self,
        backend_host: str,
        backend_port: int,
        worker_id: str,
        worker_url: str,
        platform: str = "windows",
        heartbeat_interval: int = 30,
    ):
        """
        Initialize telemetry client.

        Args:
            backend_host: Backend server IP/hostname
            backend_port: Backend server port
            worker_id: Unique worker identifier
            worker_url: This worker's accessible URL
            platform: Platform type (windows, linux, macos)
            heartbeat_interval: Seconds between heartbeats
        """
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.worker_id = worker_id
        self.worker_url = worker_url
        self.platform = platform
        self.heartbeat_interval = heartbeat_interval

        self.backend_url = f"http://{backend_host}:{backend_port}"
        self._session: Optional[aiohttp.ClientSession] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        self._start_time = time.time()

        # Metrics storage for telemetry
        self._current_load = 0
        self._total_tasks_completed = 0
        self._total_tasks_failed = 0
        self._npu_available = False
        self._loaded_models: List[str] = []
        self._metrics: Dict[str, Any] = {}

        # Retry configuration
        self._retry_delay = 5
        self._max_retry_delay = 60
        self._consecutive_failures = 0

    async def start(self) -> None:
        """Start the telemetry client and heartbeat loop."""
        if self._running:
            return

        self._running = True
        self._start_time = time.time()

        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        self._session = aiohttp.ClientSession(timeout=timeout)

        # Start heartbeat loop
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(
            "Backend telemetry started - sending to %s every %ds",
            self.backend_url,
            self.heartbeat_interval,
        )

    async def stop(self) -> None:
        """Stop the telemetry client."""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._session:
            await self._session.close()

        logger.info("Backend telemetry stopped")

    def update_metrics(
        self,
        current_load: Optional[int] = None,
        tasks_completed: Optional[int] = None,
        tasks_failed: Optional[int] = None,
        npu_available: Optional[bool] = None,
        loaded_models: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update metrics to be sent with next heartbeat.

        Args:
            current_load: Current number of active tasks
            tasks_completed: Total completed task count
            tasks_failed: Total failed task count
            npu_available: Whether NPU hardware is available
            loaded_models: List of loaded model names
            metrics: Additional performance metrics
        """
        if current_load is not None:
            self._current_load = current_load
        if tasks_completed is not None:
            self._total_tasks_completed = tasks_completed
        if tasks_failed is not None:
            self._total_tasks_failed = tasks_failed
        if npu_available is not None:
            self._npu_available = npu_available
        if loaded_models is not None:
            self._loaded_models = loaded_models
        if metrics is not None:
            self._metrics = metrics

    async def _heartbeat_loop(self) -> None:
        """Background loop that sends periodic heartbeats."""
        # Initial delay to let worker initialize
        await asyncio.sleep(2)

        while self._running:
            try:
                success = await self._send_heartbeat()

                if success:
                    self._consecutive_failures = 0
                    self._retry_delay = 5
                else:
                    self._consecutive_failures += 1
                    # Exponential backoff up to max
                    self._retry_delay = min(
                        self._retry_delay * 2, self._max_retry_delay
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Heartbeat loop error: %s", e)
                self._consecutive_failures += 1

            # Wait for next heartbeat
            await asyncio.sleep(self.heartbeat_interval)

    async def _send_heartbeat(self) -> bool:
        """
        Send heartbeat to backend.

        Returns:
            True if heartbeat was acknowledged, False otherwise
        """
        if not self._session:
            return False

        uptime = time.time() - self._start_time

        heartbeat_data = {
            "worker_id": self.worker_id,
            "status": "online",
            "platform": self.platform,
            "url": self.worker_url,
            "current_load": self._current_load,
            "total_tasks_completed": self._total_tasks_completed,
            "total_tasks_failed": self._total_tasks_failed,
            "uptime_seconds": uptime,
            "npu_available": self._npu_available,
            "loaded_models": self._loaded_models,
            "metrics": self._metrics,
        }

        try:
            url = f"{self.backend_url}/api/npu/workers/heartbeat"
            async with self._session.post(url, json=heartbeat_data) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.debug(
                        "Heartbeat acknowledged: server_timestamp=%s",
                        data.get("server_timestamp"),
                    )
                    return True
                else:
                    text = await response.text()
                    logger.warning(
                        "Heartbeat failed: status=%d, response=%s",
                        response.status,
                        text[:200],
                    )
                    return False

        except aiohttp.ClientConnectorError:
            logger.warning(
                "Cannot connect to backend at %s (attempt %d)",
                self.backend_url,
                self._consecutive_failures + 1,
            )
            return False
        except asyncio.TimeoutError:
            logger.warning("Heartbeat timeout to %s", self.backend_url)
            return False
        except Exception as e:
            logger.error("Heartbeat error: %s", e)
            return False

    async def send_registration(self) -> bool:
        """
        Attempt to register this worker with the backend.

        This is called on startup and if heartbeat detects worker isn't registered.

        Returns:
            True if registration succeeded, False otherwise
        """
        if not self._session:
            return False

        registration_data = {
            "id": self.worker_id,
            "name": f"Windows NPU Worker ({self.worker_id})",
            "url": self.worker_url,
            "platform": self.platform,
            "enabled": True,
            "priority": 5,
            "weight": 1,
            "max_concurrent_tasks": 4,
        }

        try:
            url = f"{self.backend_url}/api/npu/workers"
            async with self._session.post(url, json=registration_data) as response:
                if response.status in (200, 201):
                    logger.info("Successfully registered with backend")
                    return True
                elif response.status == 400:
                    # Likely already registered
                    logger.info("Worker already registered with backend")
                    return True
                else:
                    text = await response.text()
                    logger.warning(
                        "Registration failed: status=%d, response=%s",
                        response.status,
                        text[:200],
                    )
                    return False

        except Exception as e:
            logger.error("Registration error: %s", e)
            return False


# =============================================================================
# Constants (Issue #68 - Code smells fix: Extract magic numbers)
# Note: No hardcoded IPs - backend host comes from config/environment
# =============================================================================
DEFAULT_WORKER_PORT = 8082
DEFAULT_HEARTBEAT_INTERVAL = 30
LOCAL_IP_FALLBACK = "127.0.0.1"

# =============================================================================
# Thread-safe global state (Issue #68 - Race condition fix)
# =============================================================================
_telemetry_lock = asyncio.Lock()
_telemetry_client: Optional[BackendTelemetryClient] = None
_local_ip_cache: Optional[str] = None  # Cache to avoid repeated socket calls


def _get_local_ip(backend_host: str) -> str:
    """
    Get the local IP address that can reach the backend.

    Uses caching to avoid repeated socket operations.

    Args:
        backend_host: Backend server hostname/IP

    Returns:
        Local IP address string
    """
    global _local_ip_cache

    # Return cached value if available
    if _local_ip_cache is not None:
        return _local_ip_cache

    sock = None
    try:
        # Get local IP by connecting to backend (doesn't actually send data)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((backend_host, 80))
        local_ip = sock.getsockname()[0]
        _local_ip_cache = local_ip
        return local_ip
    except Exception:
        return LOCAL_IP_FALLBACK
    finally:
        # Proper socket cleanup (Issue #68 - unclosed socket fix)
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


async def get_telemetry_client(config: dict) -> Optional[BackendTelemetryClient]:
    """
    Get or create the global telemetry client.

    Thread-safe with lock to prevent race conditions on initialization.

    Args:
        config: Configuration dictionary with backend settings

    Returns:
        BackendTelemetryClient instance or None if disabled
    """
    global _telemetry_client

    # Fast path: check without lock first (double-check locking pattern)
    if _telemetry_client is not None:
        return _telemetry_client

    # Acquire lock for thread-safe initialization (Issue #68 - race condition fix)
    async with _telemetry_lock:
        # Double-check after acquiring lock
        if _telemetry_client is not None:
            return _telemetry_client

        backend_config = config.get("backend", {})
        if not backend_config.get("register_with_backend", True):
            logger.info("Backend telemetry disabled in config")
            return None

        # Backend host/port must be in config - no hardcoded defaults
        backend_host = backend_config.get("host")
        backend_port = backend_config.get("port")
        if not backend_host or not backend_port:
            logger.warning("Backend host/port not configured - telemetry disabled")
            return None

        service_config = config.get("service", {})
        worker_id_prefix = service_config.get("worker_id_prefix", "windows_npu_worker")
        port = service_config.get("port", DEFAULT_WORKER_PORT)

        # Generate worker ID
        import uuid
        worker_id = f"{worker_id_prefix}_{uuid.uuid4().hex[:8]}"

        # Determine this worker's accessible URL using cached local IP
        local_ip = _get_local_ip(backend_host)
        worker_url = f"http://{local_ip}:{port}"

        _telemetry_client = BackendTelemetryClient(
            backend_host=backend_host,
            backend_port=backend_port,
            worker_id=worker_id,
            worker_url=worker_url,
            platform="windows",
            heartbeat_interval=backend_config.get("health_check_interval", DEFAULT_HEARTBEAT_INTERVAL),
        )

        return _telemetry_client


async def stop_telemetry_client() -> None:
    """Stop and cleanup the global telemetry client."""
    global _telemetry_client

    async with _telemetry_lock:
        if _telemetry_client:
            await _telemetry_client.stop()
            _telemetry_client = None
