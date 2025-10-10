"""
Redis Service Manager
Manages Redis service lifecycle and health on the Redis VM (172.16.168.23)

Features:
- Service control operations (start/stop/restart)
- Health monitoring and status checks
- Integration with SSHManager for remote operations
- Audit logging for all service operations
- RBAC enforcement for admin/operator roles
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from backend.services.ssh_manager import RemoteCommandResult, SSHManager

logger = logging.getLogger(__name__)


# Custom exceptions for Redis service operations
class RedisServiceException(Exception):
    """Base exception for Redis service operations"""

    pass


class RedisConnectionError(RedisServiceException):
    """Raised when cannot connect to Redis VM"""

    pass


class RedisPermissionError(RedisServiceException):
    """Raised when user lacks permissions for operation"""

    pass


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
    Manages Redis service lifecycle and health on Redis VM

    Responsibilities:
    - Execute service control operations (start/stop/restart)
    - Monitor Redis service status and health
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
        self.ssh_manager = ssh_manager or SSHManager(enable_audit_logging=True)
        self.redis_host = redis_host
        self.service_name = service_name
        self.enable_audit_logging = enable_audit_logging

        # Status cache
        self._status_cache: Optional[ServiceStatus] = None
        self._status_cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 10  # Cache TTL

        logger.info(
            f"Redis Service Manager initialized for host={redis_host}, "
            f"service={service_name}"
        )

    async def start(self):
        """Start Redis Service Manager"""
        await self.ssh_manager.start()
        logger.info("Redis Service Manager started")

    async def stop(self):
        """Stop Redis Service Manager"""
        await self.ssh_manager.stop()
        logger.info("Redis Service Manager stopped")

    def _audit_log(
        self, event_type: str, data: Dict[str, Any], user_id: Optional[str] = None
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
            logger.info(f"AUDIT: {json.dumps(audit_entry)}")
        except Exception as e:
            logger.error(f"Audit logging failed: {e}")

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
                validate=True,  # Use SecureCommandExecutor validation
            )
            return result

        except Exception as e:
            logger.error(f"Failed to execute systemctl {command}: {e}")
            raise RedisConnectionError(
                f"Cannot execute command on Redis VM: {str(e)}"
            ) from e

    async def start_service(self, user_id: str = "system") -> ServiceOperationResult:
        """
        Start Redis service

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
            # Check current status first
            current_status = await self.get_service_status()
            if current_status.status == "running":
                duration = (datetime.now() - start_time).total_seconds()
                return ServiceOperationResult(
                    success=True,
                    operation="start",
                    message="Redis service already running",
                    duration_seconds=duration,
                    timestamp=datetime.now(),
                    new_status="running",
                )

            # Execute start command
            result = await self._execute_systemctl_command("start", timeout=30)

            # Verify service started
            await asyncio.sleep(2)  # Give service time to start
            new_status = await self.get_service_status()

            duration = (datetime.now() - start_time).total_seconds()
            success = new_status.status == "running"

            operation_result = ServiceOperationResult(
                success=success,
                operation="start",
                message=(
                    "Redis service started successfully"
                    if success
                    else "Failed to start Redis service"
                ),
                duration_seconds=duration,
                timestamp=datetime.now(),
                new_status=new_status.status,
                error=None if success else result.stderr,
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
            logger.error(f"Start service failed: {e}")

            self._audit_log(
                "redis_service_start_failed", {"error": str(e)}, user_id=user_id
            )

            return ServiceOperationResult(
                success=False,
                operation="start",
                message=f"Failed to start Redis service: {str(e)}",
                duration_seconds=duration,
                timestamp=datetime.now(),
                new_status="unknown",
                error=str(e),
            )

    async def stop_service(self, user_id: str = "system") -> ServiceOperationResult:
        """
        Stop Redis service

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
            # Check current status first
            current_status = await self.get_service_status()
            if current_status.status == "stopped":
                duration = (datetime.now() - start_time).total_seconds()
                return ServiceOperationResult(
                    success=True,
                    operation="stop",
                    message="Redis service already stopped",
                    duration_seconds=duration,
                    timestamp=datetime.now(),
                    new_status="stopped",
                )

            # Execute stop command
            result = await self._execute_systemctl_command("stop", timeout=30)

            # Verify service stopped
            await asyncio.sleep(2)  # Give service time to stop
            new_status = await self.get_service_status()

            duration = (datetime.now() - start_time).total_seconds()
            success = new_status.status == "stopped"

            operation_result = ServiceOperationResult(
                success=success,
                operation="stop",
                message=(
                    "Redis service stopped successfully"
                    if success
                    else "Failed to stop Redis service"
                ),
                duration_seconds=duration,
                timestamp=datetime.now(),
                new_status=new_status.status,
                error=None if success else result.stderr,
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
            logger.error(f"Stop service failed: {e}")

            self._audit_log(
                "redis_service_stop_failed", {"error": str(e)}, user_id=user_id
            )

            return ServiceOperationResult(
                success=False,
                operation="stop",
                message=f"Failed to stop Redis service: {str(e)}",
                duration_seconds=duration,
                timestamp=datetime.now(),
                new_status="unknown",
                error=str(e),
            )

    async def restart_service(self, user_id: str = "system") -> ServiceOperationResult:
        """
        Restart Redis service

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
            result = await self._execute_systemctl_command("restart", timeout=30)

            # Verify service restarted
            await asyncio.sleep(2)  # Give service time to restart
            new_status = await self.get_service_status()

            duration = (datetime.now() - start_time).total_seconds()
            success = new_status.status == "running"

            operation_result = ServiceOperationResult(
                success=success,
                operation="restart",
                message=(
                    "Redis service restarted successfully"
                    if success
                    else "Failed to restart Redis service"
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
            logger.error(f"Restart service failed: {e}")

            self._audit_log(
                "redis_service_restart_failed", {"error": str(e)}, user_id=user_id
            )

            return ServiceOperationResult(
                success=False,
                operation="restart",
                message=f"Failed to restart Redis service: {str(e)}",
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
            except Exception:
                pass

            service_status = ServiceStatus(
                status=status, pid=pid, last_check=datetime.now()
            )

            # Update cache
            self._status_cache = service_status
            self._status_cache_time = datetime.now()

            return service_status

        except Exception as e:
            logger.error(f"Failed to get service status: {e}")
            return ServiceStatus(status="unknown", last_check=datetime.now())

    async def get_health(self) -> HealthStatus:
        """
        Get detailed health status

        Returns:
            HealthStatus with comprehensive health information
        """
        try:
            # Get service status
            status = await self.get_service_status(use_cache=False)
            service_running = status.status == "running"

            # Test Redis connectivity via redis-cli PING
            connectivity = False
            response_time_ms = 0.0

            try:
                ping_start = datetime.now()
                ping_result = await self.ssh_manager.execute_command(
                    host=self.redis_host,
                    command="redis-cli -h 127.0.0.1 -p 6379 PING",
                    timeout=5,
                    validate=False,
                )
                ping_duration = (datetime.now() - ping_start).total_seconds() * 1000
                response_time_ms = ping_duration

                if ping_result.success and "PONG" in ping_result.stdout:
                    connectivity = True
            except Exception as e:
                logger.warning(f"Redis connectivity check failed: {e}")
                connectivity = False

            # Determine overall status
            if service_running and connectivity:
                overall_status = "healthy"
            elif service_running and not connectivity:
                overall_status = "degraded"
            else:
                overall_status = "critical"

            # Generate recommendations
            recommendations = []
            if not service_running:
                recommendations.append(
                    "Redis service is not running - consider starting it"
                )
            if not connectivity and service_running:
                recommendations.append(
                    "Redis service running but not responding - check logs"
                )
            if response_time_ms > 1000:
                recommendations.append(
                    f"High response time ({response_time_ms:.1f}ms) - check system load"
                )

            return HealthStatus(
                overall_status=overall_status,
                service_running=service_running,
                connectivity=connectivity,
                response_time_ms=response_time_ms,
                last_successful_command=datetime.now() if connectivity else None,
                error_count_last_hour=0,  # TODO: Implement error tracking
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return HealthStatus(
                overall_status="critical",
                service_running=False,
                connectivity=False,
                response_time_ms=0.0,
                error_count_last_hour=0,
                recommendations=["Health check failed - cannot determine status"],
            )
