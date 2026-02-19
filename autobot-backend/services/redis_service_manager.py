# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Service Manager
Manages Redis Stack service lifecycle and health on the Redis VM (see NetworkConstants.REDIS_VM_IP)

Related Issue: #729 - SSH operations now proxied through SLM API

TODO (#729): This service needs refactoring to proxy SSH through SLM API

Features:
- Service control operations (start/stop/restart)
- Health monitoring and status checks
- Integration with SSHManager for remote operations (will proxy through SLM)
- Audit logging for all service operations
- RBAC enforcement for admin/operator roles
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

import aiohttp

from backend.constants.threshold_constants import TimingConstants
from backend.type_defs.common import Metadata

logger = logging.getLogger(__name__)

_DEFAULT_SLM_URL = os.environ.get("SLM_URL", "")
_DEFAULT_REDIS_NODE_ID = os.environ.get("REDIS_NODE_ID", "04-Databases")


# Custom exceptions for Redis Stack service operations
class RedisServiceException(Exception):
    """Base exception for Redis Stack service operations"""


class RedisConnectionError(RedisServiceException):
    """Raised when cannot connect to Redis VM"""


class RedisPermissionError(RedisServiceException):
    """Raised when user lacks permissions for operation"""


@dataclass
class ServiceOperationResult:
    """Result of a service operation"""

    success: bool
    operation: str  # "start", "stop", "restart", "status"
    message: str
    duration_seconds: float
    timestamp: datetime
    new_status: str  # "running", "stopped", "failed", "unknown"
    error: Optional[str] = None


@dataclass
class ServiceStatus:
    """Current service status"""

    status: str  # "running", "stopped", "failed", "unknown"
    pid: Optional[int] = None
    uptime_seconds: Optional[float] = None
    memory_mb: Optional[float] = None
    last_check: datetime = None


@dataclass
class HealthStatus:
    """Detailed health status"""

    overall_status: str  # "healthy", "degraded", "critical"
    service_running: bool
    connectivity: bool
    response_time_ms: float
    last_successful_command: Optional[datetime] = None
    error_count_last_hour: int = 0
    recommendations: list = None


class RedisServiceManager:
    """
    Manages Redis Stack service lifecycle and health on Redis VM

    Responsibilities:
    - Execute service control operations (start/stop/restart)
    - Monitor Redis Stack service status and health
    - Audit logging for all operations
    - RBAC enforcement for admin/operator roles
    """

    def __init__(
        self,
        slm_url: Optional[str] = None,
        slm_node_id: Optional[str] = None,
        service_name: str = "redis-stack-server",
        enable_audit_logging: bool = True,
    ):
        """
        Initialize Redis Service Manager.

        Routes all service operations through the SLM API (Issue #933).

        Args:
            slm_url: Base URL of SLM server (default: SLM_URL env var)
            slm_node_id: SLM node_id of the Redis VM (default: REDIS_NODE_ID env var)
            service_name: Systemd service name (default: 'redis-stack-server')
            enable_audit_logging: Enable audit logging (default: True)
        """
        self.slm_url = (slm_url or _DEFAULT_SLM_URL).rstrip("/")
        self.slm_node_id = slm_node_id or _DEFAULT_REDIS_NODE_ID
        self.service_name = service_name
        self.enable_audit_logging = enable_audit_logging

        # Status cache
        self._status_cache: Optional[ServiceStatus] = None
        self._status_cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 10

        # Error tracking for health metrics
        self._error_count: int = 0
        self._error_count_hour_start: datetime = datetime.now()
        self._error_lock = asyncio.Lock()

        logger.info(
            "Redis Service Manager initialized for node=%s, service=%s",
            self.slm_node_id,
            service_name,
        )

    async def _record_error(self) -> None:
        """Record an error for health metrics tracking (thread-safe)."""
        async with self._error_lock:
            now = datetime.now()
            # Reset counter if hour has passed
            if (now - self._error_count_hour_start).total_seconds() >= 3600:
                self._error_count = 0
                self._error_count_hour_start = now
            self._error_count += 1

    async def _get_error_count_last_hour(self) -> int:
        """Get error count for the last hour, resetting if needed (thread-safe)."""
        async with self._error_lock:
            now = datetime.now()
            if (now - self._error_count_hour_start).total_seconds() >= 3600:
                self._error_count = 0
                self._error_count_hour_start = now
            return self._error_count

    async def start(self) -> None:
        """Start Redis Service Manager (no-op — SLM API is stateless)."""
        logger.info("Redis Service Manager ready (SLM URL: %s)", self.slm_url)

    async def stop(self) -> None:
        """Stop Redis Service Manager (no-op — SLM API is stateless)."""
        logger.info("Redis Service Manager stopped")

    def _audit_log(
        self, event_type: str, data: Metadata, user_id: Optional[str] = None
    ):
        """Log audit event"""
        if not self.enable_audit_logging:
            return

        try:
            audit_entry = {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                "user_id": user_id,
                "data": data,
            }
            logger.info("AUDIT: %s", json.dumps(audit_entry))
        except Exception as e:
            logger.error("Audit logging failed: %s", e)

    async def _slm_service_action(self, action: str) -> Tuple[bool, str]:
        """
        Call SLM API to start/stop/restart the Redis service.

        Issue #933: Replaces direct SSH systemctl calls.

        Args:
            action: "start", "stop", or "restart"

        Returns:
            Tuple of (success, message)

        Raises:
            RedisConnectionError: If SLM API is unreachable
        """
        if not self.slm_url:
            raise RedisConnectionError("SLM_URL not configured")
        url = (
            f"{self.slm_url}/api/nodes/{self.slm_node_id}"
            f"/services/{self.service_name}/{action}"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, ssl=False) as resp:
                    data = await resp.json()
                    success = data.get("success", resp.status < 300)
                    message = data.get("message", "")
                    return success, message
        except Exception as exc:
            logger.error("SLM service action '%s' failed: %s", action, exc)
            await self._record_error()
            raise RedisConnectionError(
                f"Cannot reach SLM API for service action '{action}': {exc}"
            ) from exc

    async def _slm_get_service_status(self) -> str:
        """
        Query SLM API for Redis service status.

        Issue #933: Replaces direct SSH systemctl status call.

        Returns:
            One of: "running", "stopped", "failed", "unknown"
        """
        if not self.slm_url:
            return "unknown"
        url = f"{self.slm_url}/api/nodes/{self.slm_node_id}/services"
        try:
            async with aiohttp.ClientSession() as session:
                params = {"search": self.service_name, "per_page": "1"}
                async with session.get(url, params=params, ssl=False) as resp:
                    if resp.status != 200:
                        return "unknown"
                    data = await resp.json()
                    services = data.get("services", [])
                    if services:
                        return services[0].get("status", "unknown")
                    return "unknown"
        except Exception as exc:
            logger.warning("SLM service status query failed: %s", exc)
            return "unknown"

    def _already_in_state_result(
        self, operation: str, target_status: str, duration: float
    ) -> ServiceOperationResult:
        """
        Create result for service already in target state.

        Issue #665: Extracted from start_service and stop_service.
        """
        return ServiceOperationResult(
            success=True,
            operation=operation,
            message=f"Redis Stack service already {target_status}",
            duration_seconds=duration,
            timestamp=datetime.now(),
            new_status=target_status,
        )

    def _operation_result(
        self,
        operation: str,
        success: bool,
        actual_status: str,
        duration: float,
        stderr: Optional[str] = None,
    ) -> ServiceOperationResult:
        """
        Create result for service operation completion.

        Issue #665: Extracted from start_service and stop_service.
        """
        action = "started" if operation == "start" else "stopped"
        return ServiceOperationResult(
            success=success,
            operation=operation,
            message=(
                f"Redis Stack service {action} successfully"
                if success
                else f"Failed to {operation} Redis Stack service"
            ),
            duration_seconds=duration,
            timestamp=datetime.now(),
            new_status=actual_status,
            error=None if success else stderr,
        )

    def _operation_failure_result(
        self, operation: str, error: str, duration: float
    ) -> ServiceOperationResult:
        """
        Create result for operation failure.

        Issue #665: Extracted from start_service and stop_service.
        """
        return ServiceOperationResult(
            success=False,
            operation=operation,
            message=f"Failed to {operation} Redis Stack service: {error}",
            duration_seconds=duration,
            timestamp=datetime.now(),
            new_status="unknown",
            error=error,
        )

    async def start_service(self, user_id: str = "system") -> ServiceOperationResult:
        """
        Start Redis Stack service.

        Issue #665: Refactored from 87 lines to use extracted helper methods.

        Args:
            user_id: User ID for audit logging

        Returns:
            ServiceOperationResult with operation details

        Raises:
            RedisConnectionError: If cannot connect to Redis VM
        """
        start_time = datetime.now()
        self._audit_log(
            "redis_service_start_attempt", {"user_id": user_id}, user_id=user_id
        )

        try:
            # Check if already running (Issue #665: uses helper)
            current_status = await self.get_service_status()
            if current_status.status == "running":
                duration = (datetime.now() - start_time).total_seconds()
                return self._already_in_state_result("start", "running", duration)

            # Call SLM API to start service and verify
            _ok, err_msg = await self._slm_service_action("start")
            await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)
            new_status = await self.get_service_status()

            duration = (datetime.now() - start_time).total_seconds()
            success = new_status.status == "running"

            # Build result (Issue #665: uses helper)
            operation_result = self._operation_result(
                "start",
                success,
                new_status.status,
                duration,
                None if success else err_msg,
            )

            self._audit_log(
                "redis_service_start_completed",
                {
                    "success": success,
                    "duration": duration,
                    "new_status": new_status.status,
                },
                user_id=user_id,
            )
            return operation_result

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error("Start service failed: %s", e)
            await self._record_error()
            self._audit_log(
                "redis_service_start_failed", {"error": str(e)}, user_id=user_id
            )
            return self._operation_failure_result("start", str(e), duration)

    async def stop_service(self, user_id: str = "system") -> ServiceOperationResult:
        """
        Stop Redis Stack service.

        Issue #665: Refactored from 87 lines to use extracted helper methods.

        Args:
            user_id: User ID for audit logging

        Returns:
            ServiceOperationResult with operation details

        Raises:
            RedisConnectionError: If cannot connect to Redis VM
        """
        start_time = datetime.now()
        self._audit_log(
            "redis_service_stop_attempt", {"user_id": user_id}, user_id=user_id
        )

        try:
            # Check if already stopped (Issue #665: uses helper)
            current_status = await self.get_service_status()
            if current_status.status == "stopped":
                duration = (datetime.now() - start_time).total_seconds()
                return self._already_in_state_result("stop", "stopped", duration)

            # Call SLM API to stop service and verify
            _ok, err_msg = await self._slm_service_action("stop")
            await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)
            new_status = await self.get_service_status()

            duration = (datetime.now() - start_time).total_seconds()
            success = new_status.status == "stopped"

            # Build result (Issue #665: uses helper)
            operation_result = self._operation_result(
                "stop",
                success,
                new_status.status,
                duration,
                None if success else err_msg,
            )

            self._audit_log(
                "redis_service_stop_completed",
                {
                    "success": success,
                    "duration": duration,
                    "new_status": new_status.status,
                },
                user_id=user_id,
            )
            return operation_result

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error("Stop service failed: %s", e)
            await self._record_error()
            self._audit_log(
                "redis_service_stop_failed", {"error": str(e)}, user_id=user_id
            )
            return self._operation_failure_result("stop", str(e), duration)

    async def restart_service(self, user_id: str = "system") -> ServiceOperationResult:
        """
        Restart Redis Stack service.

        Issue #933: Uses SLM API instead of SSH.

        Args:
            user_id: User ID for audit logging

        Returns:
            ServiceOperationResult with operation details

        Raises:
            RedisConnectionError: If cannot connect to Redis VM
        """
        start_time = datetime.now()
        self._audit_log(
            "redis_service_restart_attempt", {"user_id": user_id}, user_id=user_id
        )

        try:
            # Call SLM API to restart service and verify
            _ok, err_msg = await self._slm_service_action("restart")
            await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)
            new_status = await self.get_service_status()

            duration = (datetime.now() - start_time).total_seconds()
            success = new_status.status == "running"
            operation_result = self._operation_result(
                "restart",
                success,
                new_status.status,
                duration,
                None if success else err_msg,
            )
            self._audit_log(
                "redis_service_restart_completed",
                {
                    "success": success,
                    "duration": duration,
                    "new_status": new_status.status,
                },
                user_id=user_id,
            )
            return operation_result

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error("Restart service failed: %s", e)
            await self._record_error()
            self._audit_log(
                "redis_service_restart_failed", {"error": str(e)}, user_id=user_id
            )
            return self._operation_failure_result("restart", str(e), duration)

    async def get_service_status(self, use_cache: bool = True) -> ServiceStatus:
        """
        Get current service status

        Args:
            use_cache: Use cached status if available and fresh

        Returns:
            ServiceStatus with current status information
        """
        # Check cache
        if (
            use_cache
            and self._status_cache
            and self._status_cache_time
            and (datetime.now() - self._status_cache_time).total_seconds()
            < self._cache_ttl_seconds
        ):
            return self._status_cache

        try:
            status_str = await self._slm_get_service_status()
            service_status = ServiceStatus(status=status_str, last_check=datetime.now())

            # Update cache
            self._status_cache = service_status
            self._status_cache_time = datetime.now()

            return service_status

        except Exception as e:
            logger.error("Failed to get service status: %s", e)
            await self._record_error()
            return ServiceStatus(status="unknown", last_check=datetime.now())

    async def _check_redis_connectivity(self) -> Tuple[bool, float]:
        """
        Test Redis connectivity via direct Python redis ping.

        Issue #933: Replaces SSH-based redis-cli PING.

        Returns:
            Tuple of (connectivity: bool, response_time_ms: float)
        """
        try:
            from autobot_shared.redis_client import get_redis_client

            ping_start = datetime.now()
            client = get_redis_client(async_client=True, database="main")
            await client.ping()
            response_time_ms = (datetime.now() - ping_start).total_seconds() * 1000
            return True, response_time_ms
        except Exception as e:
            logger.warning("Redis connectivity check failed: %s", e)
            return False, 0.0

    def _determine_health_status(
        self, service_running: bool, connectivity: bool
    ) -> str:
        """
        Determine overall health status based on service and connectivity.

        (Issue #398: extracted helper)
        """
        if service_running and connectivity:
            return "healthy"
        elif service_running and not connectivity:
            return "degraded"
        return "critical"

    def _generate_health_recommendations(
        self, service_running: bool, connectivity: bool, response_time_ms: float
    ) -> List[str]:
        """
        Generate health recommendations based on current state.

        (Issue #398: extracted helper)
        """
        recommendations = []
        if not service_running:
            recommendations.append(
                "Redis Stack service is not running - consider starting it"
            )
        if not connectivity and service_running:
            recommendations.append(
                "Redis Stack service running but not responding - check logs"
            )
        if response_time_ms > 1000:
            recommendations.append(
                f"High response time ({response_time_ms:.1f}ms) - check system load"
            )
        return recommendations

    async def get_health(self) -> HealthStatus:
        """
        Get detailed health status.

        (Issue #398: refactored to use extracted helpers)

        Returns:
            HealthStatus with comprehensive health information
        """
        try:
            status = await self.get_service_status(use_cache=False)
            service_running = status.status == "running"

            connectivity, response_time_ms = await self._check_redis_connectivity()
            overall_status = self._determine_health_status(
                service_running, connectivity
            )
            recommendations = self._generate_health_recommendations(
                service_running, connectivity, response_time_ms
            )

            return HealthStatus(
                overall_status=overall_status,
                service_running=service_running,
                connectivity=connectivity,
                response_time_ms=response_time_ms,
                last_successful_command=datetime.now() if connectivity else None,
                error_count_last_hour=await self._get_error_count_last_hour(),
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error("Health check failed: %s", e)
            await self._record_error()
            return HealthStatus(
                overall_status="critical",
                service_running=False,
                connectivity=False,
                response_time_ms=0.0,
                error_count_last_hour=await self._get_error_count_last_hour(),
                recommendations=["Health check failed - cannot determine status"],
            )
