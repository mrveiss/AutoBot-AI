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
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from backend.type_defs.common import Metadata

# TODO (#729): SSH proxied through SLM API
# from backend.services.ssh_manager import RemoteCommandResult, SSHManager
from src.constants.network_constants import NetworkConstants
from src.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)

# TODO (#729): Temporary placeholders until refactored to use SLM proxy
# These are used for type hints only
SSHManager = object  # type: ignore
RemoteCommandResult = object  # type: ignore


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
        ssh_manager: Optional[SSHManager] = None,
        redis_host: str = "redis",
        service_name: str = "redis-stack-server",
        enable_audit_logging: bool = True,
    ):
        """
        Initialize Redis Service Manager

        Args:
            ssh_manager: SSH manager instance (creates new if None)
            redis_host: SSH host name for Redis VM (default: 'redis')
            service_name: Systemd service name (default: 'redis-stack-server')
            enable_audit_logging: Enable audit logging (default: True)
        """
        # TODO (#729): SSH proxied through SLM API - This service needs refactoring
        raise NotImplementedError("Redis Service Manager temporarily disabled - SSH proxied through SLM API (#729)")
        # OLD CODE:
        # self.ssh_manager = ssh_manager or SSHManager(enable_audit_logging=True)
        self.redis_host = redis_host
        self.service_name = service_name
        self.enable_audit_logging = enable_audit_logging

        # Status cache
        self._status_cache: Optional[ServiceStatus] = None
        self._status_cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 10  # Cache TTL

        # Error tracking for health metrics
        self._error_count: int = 0
        self._error_count_hour_start: datetime = datetime.now()
        self._error_lock = asyncio.Lock()  # Lock for thread-safe error tracking

        logger.info(
            f"Redis Service Manager initialized for host={redis_host}, "
            f"service={service_name}"
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

    async def start(self):
        """Start Redis Service Manager"""
        await self.ssh_manager.start()
        logger.info("Redis Service Manager started")

    async def stop(self):
        """Stop Redis Service Manager"""
        await self.ssh_manager.stop()
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

    async def _execute_systemctl_command(
        self, command: str, timeout: int = 30
    ) -> RemoteCommandResult:
        """
        Execute systemctl command on Redis VM

        Args:
            command: Systemctl command (e.g., 'start', 'stop', 'status')
            timeout: Command timeout in seconds

        Returns:
            RemoteCommandResult

        Raises:
            RedisConnectionError: If SSH connection fails
        """
        full_command = f"sudo systemctl {command} {self.service_name}"

        try:
            result = await self.ssh_manager.execute_command(
                host=self.redis_host,
                command=full_command,
                timeout=timeout,
                validate=False,  # Skip validation - commands are hardcoded and RBAC-protected
            )
            return result

        except Exception as e:
            logger.error("Failed to execute systemctl %s: %s", command, e)
            await self._record_error()
            raise RedisConnectionError(
                f"Cannot execute command on Redis VM: {str(e)}"
            ) from e

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

            # Execute start command and verify
            result = await self._execute_systemctl_command(
                "start", timeout=TimingConstants.SHORT_TIMEOUT
            )
            await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)
            new_status = await self.get_service_status()

            duration = (datetime.now() - start_time).total_seconds()
            success = new_status.status == "running"

            # Build result (Issue #665: uses helper)
            operation_result = self._operation_result(
                "start", success, new_status.status, duration, result.stderr
            )

            self._audit_log(
                "redis_service_start_completed",
                {"success": success, "duration": duration, "new_status": new_status.status},
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

            # Execute stop command and verify
            result = await self._execute_systemctl_command(
                "stop", timeout=TimingConstants.SHORT_TIMEOUT
            )
            await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)
            new_status = await self.get_service_status()

            duration = (datetime.now() - start_time).total_seconds()
            success = new_status.status == "stopped"

            # Build result (Issue #665: uses helper)
            operation_result = self._operation_result(
                "stop", success, new_status.status, duration, result.stderr
            )

            self._audit_log(
                "redis_service_stop_completed",
                {"success": success, "duration": duration, "new_status": new_status.status},
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
        Restart Redis Stack service

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
            # Execute restart command
            result = await self._execute_systemctl_command("restart", timeout=TimingConstants.SHORT_TIMEOUT)

            # Verify service restarted - wait for initialization
            await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)
            new_status = await self.get_service_status()

            duration = (datetime.now() - start_time).total_seconds()
            success = new_status.status == "running"

            operation_result = ServiceOperationResult(
                success=success,
                operation="restart",
                message=(
                    "Redis Stack service restarted successfully"
                    if success
                    else "Failed to restart Redis Stack service"
                ),
                duration_seconds=duration,
                timestamp=datetime.now(),
                new_status=new_status.status,
                error=None if success else result.stderr,
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

            return ServiceOperationResult(
                success=False,
                operation="restart",
                message=f"Failed to restart Redis Stack service: {str(e)}",
                duration_seconds=duration,
                timestamp=datetime.now(),
                new_status="unknown",
                error=str(e),
            )

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
            # Execute status command
            result = await self._execute_systemctl_command("status", timeout=10)

            # Parse systemctl status output
            status_text = result.stdout.lower()

            if "active (running)" in status_text:
                status = "running"
            elif (
                "inactive (dead)" in status_text or "could not be found" in status_text
            ):
                status = "stopped"
            elif "failed" in status_text:
                status = "failed"
            else:
                status = "unknown"

            # Try to extract PID (basic parsing)
            pid = None
            try:
                for line in result.stdout.split("\n"):
                    if "Main PID:" in line:
                        pid_str = line.split("Main PID:")[1].strip().split()[0]
                        pid = int(pid_str) if pid_str.isdigit() else None
                        break
            except Exception as e:
                logger.debug("Failed to parse PID from status output: %s", e)

            service_status = ServiceStatus(
                status=status, pid=pid, last_check=datetime.now()
            )

            # Update cache
            self._status_cache = service_status
            self._status_cache_time = datetime.now()

            return service_status

        except Exception as e:
            logger.error("Failed to get service status: %s", e)
            await self._record_error()
            return ServiceStatus(status="unknown", last_check=datetime.now())

    async def _check_redis_connectivity(self) -> tuple:
        """
        Test Redis connectivity via redis-cli PING.

        (Issue #398: extracted helper)

        Returns:
            Tuple of (connectivity: bool, response_time_ms: float)
        """
        try:
            ping_start = datetime.now()
            ping_result = await self.ssh_manager.execute_command(
                host=self.redis_host,
                command=(
                    f"redis-cli -h {NetworkConstants.LOCALHOST_IP} -p {NetworkConstants.REDIS_PORT}"
                    f"PING"
                ),
                timeout=5,
                validate=False,
            )
            response_time_ms = (datetime.now() - ping_start).total_seconds() * 1000
            connectivity = ping_result.success and "PONG" in ping_result.stdout
            return connectivity, response_time_ms
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
            overall_status = self._determine_health_status(service_running, connectivity)
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
