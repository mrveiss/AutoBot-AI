# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VM Service Registry with Circuit Breaker Integration

Issue #432: Provides graceful handling when VM services are offline by:
1. Tracking service availability state with circuit breakers
2. Suppressing repetitive error logs for known offline services
3. Providing clear status reporting for VM infrastructure

This module integrates with the existing CircuitBreaker implementation
in src/circuit_breaker.py for consistent failure handling.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

import aiohttp

from src.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    circuit_breaker_manager,
)
from src.constants.network_constants import NetworkConstants
from src.constants.threshold_constants import ServiceDiscoveryConfig

logger = logging.getLogger(__name__)


class VMServiceType(Enum):
    """Types of VM services in the AutoBot infrastructure."""

    FRONTEND = "frontend"
    NPU_WORKER = "npu_worker"
    REDIS = "redis"
    AI_STACK = "ai_stack"
    BROWSER = "browser"
    OLLAMA = "ollama"  # May run on main or AI stack


class ServiceStatus(Enum):
    """Current status of a VM service."""

    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    INTENTIONALLY_OFFLINE = "intentionally_offline"


@dataclass
class VMServiceConfig:
    """Configuration for a VM service."""

    service_type: VMServiceType
    name: str
    host: str
    port: int
    health_endpoint: str = "/health"
    timeout: float = 10.0
    is_critical: bool = False  # Critical services should log more verbosely
    is_optional: bool = False  # Optional services can be gracefully degraded
    description: str = ""

    @property
    def base_url(self) -> str:
        """Get the base URL for this service."""
        return f"http://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        """Get the health check URL for this service."""
        return f"{self.base_url}{self.health_endpoint}"


@dataclass
class VMServiceState:
    """Runtime state for a VM service."""

    config: VMServiceConfig
    status: ServiceStatus = ServiceStatus.UNKNOWN
    last_check: Optional[float] = None
    last_success: Optional[float] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    log_suppressed_until: float = 0.0  # Timestamp until which logs are suppressed
    error_count_since_last_log: int = 0  # Errors since last logged error

    # Log suppression settings (Issue #432)
    log_suppression_threshold: int = 3  # Suppress after N consecutive failures
    log_suppression_duration: float = 300.0  # Suppress for 5 minutes
    log_interval_during_suppression: float = 60.0  # Log every 60s during suppression
    last_logged_time: float = 0.0  # Track when we last logged for periodic logging
    was_offline: bool = False  # Track previous offline status for recovery logging


# Default VM service configurations
_DEFAULT_VM_SERVICES = [
    VMServiceConfig(
        service_type=VMServiceType.FRONTEND,
        name="Frontend Server",
        host=NetworkConstants.FRONTEND_VM_IP,
        port=NetworkConstants.FRONTEND_PORT,
        health_endpoint="/",
        timeout=ServiceDiscoveryConfig.FRONTEND_TIMEOUT,
        is_critical=False,
        is_optional=True,
        description="Vue.js frontend web interface (VM1)",
    ),
    VMServiceConfig(
        service_type=VMServiceType.NPU_WORKER,
        name="NPU Worker",
        host=NetworkConstants.NPU_WORKER_VM_IP,
        port=NetworkConstants.NPU_WORKER_PORT,
        health_endpoint="/health",
        timeout=ServiceDiscoveryConfig.NPU_WORKER_TIMEOUT,
        is_critical=False,
        is_optional=True,
        description="Hardware AI acceleration worker (VM2)",
    ),
    VMServiceConfig(
        service_type=VMServiceType.REDIS,
        name="Redis Server",
        host=NetworkConstants.REDIS_VM_IP,
        port=NetworkConstants.REDIS_PORT,
        health_endpoint="",  # Redis uses PING command, not HTTP
        timeout=ServiceDiscoveryConfig.REDIS_TIMEOUT,
        is_critical=True,
        is_optional=False,
        description="Redis data layer and caching (VM3)",
    ),
    VMServiceConfig(
        service_type=VMServiceType.AI_STACK,
        name="AI Stack",
        host=NetworkConstants.AI_STACK_VM_IP,
        port=NetworkConstants.AI_STACK_PORT,
        health_endpoint="/api/health",
        timeout=ServiceDiscoveryConfig.AI_STACK_TIMEOUT,
        is_critical=False,
        is_optional=True,
        description="AI processing and Ollama hosting (VM4)",
    ),
    VMServiceConfig(
        service_type=VMServiceType.BROWSER,
        name="Browser Automation",
        host=NetworkConstants.BROWSER_VM_IP,
        port=NetworkConstants.BROWSER_SERVICE_PORT,
        health_endpoint="/health",
        timeout=ServiceDiscoveryConfig.BROWSER_SERVICE_TIMEOUT,
        is_critical=False,
        is_optional=True,
        description="Playwright browser automation (VM5)",
    ),
    VMServiceConfig(
        service_type=VMServiceType.OLLAMA,
        name="Ollama LLM (AI Stack)",
        host=NetworkConstants.AI_STACK_VM_IP,
        port=NetworkConstants.OLLAMA_PORT,
        health_endpoint="/api/tags",
        timeout=ServiceDiscoveryConfig.OLLAMA_TIMEOUT,
        is_critical=False,
        is_optional=True,
        description="Local LLM inference via Ollama on AI Stack VM",
    ),
]


class VMServiceRegistry:
    """
    Registry for VM services with circuit breaker integration.

    Provides:
    - Service discovery and health monitoring
    - Circuit breaker protection for each service
    - Log suppression for known offline services
    - Graceful degradation when services are unavailable

    Issue #432: Addresses VM services offline handling.
    """

    def __init__(self):
        """Initialize VM service registry with default services."""
        self._services: Dict[VMServiceType, VMServiceState] = {}
        self._circuit_breakers: Dict[VMServiceType, CircuitBreaker] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        # Use threading.Lock for state access (works in both sync and async contexts)
        self._state_lock = threading.Lock()

        # Configuration
        self._health_check_interval = ServiceDiscoveryConfig.HEALTH_CHECK_INTERVAL_S

        # Initialize default services
        for config in _DEFAULT_VM_SERVICES:
            self._register_service(config)

    def _register_service(self, config: VMServiceConfig) -> None:
        """Register a VM service with its circuit breaker."""
        self._services[config.service_type] = VMServiceState(config=config)

        # Create circuit breaker for the service
        cb_config = CircuitBreakerConfig(
            failure_threshold=ServiceDiscoveryConfig.CIRCUIT_BREAKER_THRESHOLD,
            recovery_timeout=config.timeout * 3,  # Recovery = 3x timeout
            timeout=config.timeout,
            success_threshold=2,  # 2 successes to close circuit
        )
        self._circuit_breakers[config.service_type] = circuit_breaker_manager.get_circuit_breaker(
            f"vm_{config.service_type.value}", cb_config
        )

    def get_service_state(self, service_type: VMServiceType) -> Optional[VMServiceState]:
        """Get current state for a service."""
        return self._services.get(service_type)

    def get_all_service_states(self) -> Dict[VMServiceType, VMServiceState]:
        """Get states for all registered services."""
        return dict(self._services)

    def is_service_available(self, service_type: VMServiceType) -> bool:
        """Check if a service is currently available."""
        state = self._services.get(service_type)
        if not state:
            return False

        cb = self._circuit_breakers.get(service_type)
        if cb and cb.state == CircuitState.OPEN:
            return False

        return state.status == ServiceStatus.ONLINE

    def _should_log_error(self, state: VMServiceState) -> bool:
        """
        Determine if an error should be logged based on suppression rules.

        Issue #432: Reduces repetitive error logging for known offline services.
        """
        current_time = time.time()

        # Always log if below suppression threshold
        if state.consecutive_failures < state.log_suppression_threshold:
            state.last_logged_time = current_time
            return True

        # Check if suppression period has ended
        if current_time >= state.log_suppressed_until:
            # Start new suppression period, but log this occurrence
            state.log_suppressed_until = current_time + state.log_suppression_duration
            state.error_count_since_last_log = 0
            state.last_logged_time = current_time
            return True

        # During suppression, log periodically based on last_logged_time
        time_since_last_log = current_time - state.last_logged_time
        if time_since_last_log >= state.log_interval_during_suppression:
            # Log periodic summary during suppression
            state.last_logged_time = current_time
            return True

        # Suppressed - increment counter but don't log
        state.error_count_since_last_log += 1
        return False

    def _log_service_error(
        self,
        state: VMServiceState,
        error_msg: str,
        is_connection_error: bool = True,
    ) -> None:
        """
        Log a service error with suppression logic.

        Issue #432: Implements intelligent log suppression.
        """
        if not self._should_log_error(state):
            return

        suppressed_count = state.error_count_since_last_log
        suppression_note = ""
        if suppressed_count > 0:
            suppression_note = f" ({suppressed_count} similar errors suppressed)"

        if is_connection_error and state.config.is_optional:
            # Use WARNING for optional services that are simply offline
            logger.warning(
                "VM service %s (%s) is offline: %s%s",
                state.config.name,
                state.config.service_type.value,
                error_msg,
                suppression_note,
            )
        else:
            # Use ERROR for critical services or unexpected errors
            logger.error(
                "VM service %s (%s) health check failed: %s%s",
                state.config.name,
                state.config.service_type.value,
                error_msg,
                suppression_note,
            )

        state.error_count_since_last_log = 0

    async def _check_http_service_health(self, state: VMServiceState) -> bool:
        """Check health of an HTTP-based service."""
        config = state.config

        try:
            timeout = aiohttp.ClientTimeout(total=config.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(config.health_url) as response:
                    return response.status < 500
        except aiohttp.ClientConnectorError:
            self._log_service_error(
                state,
                f"Cannot connect to {config.host}:{config.port}",
                is_connection_error=True,
            )
            return False
        except asyncio.TimeoutError:
            self._log_service_error(
                state,
                f"Connection timeout after {config.timeout}s",
                is_connection_error=True,
            )
            return False
        except Exception as e:
            self._log_service_error(
                state, str(e), is_connection_error=False
            )
            return False

    async def _check_redis_health(self, state: VMServiceState) -> bool:
        """Check health of Redis service using PING."""
        config = state.config

        try:
            # Import here to avoid circular dependency
            from src.utils.redis_client import get_redis_client

            redis = await get_redis_client(async_client=True, database="main")
            response = await asyncio.wait_for(
                redis.ping(), timeout=config.timeout
            )
            return response is True
        except Exception as e:
            self._log_service_error(state, str(e), is_connection_error=True)
            return False

    async def check_service_health(
        self, service_type: VMServiceType
    ) -> ServiceStatus:
        """
        Check health of a specific VM service.

        Returns:
            ServiceStatus indicating current service state
        """
        state = self._services.get(service_type)
        if not state:
            return ServiceStatus.UNKNOWN

        # Update state with lock for thread safety
        with self._state_lock:
            state.last_check = time.time()
            previous_was_offline = state.was_offline

        try:
            # Use circuit breaker to wrap the health check
            cb = self._circuit_breakers.get(service_type)

            if cb and cb.state == CircuitState.OPEN:
                # Circuit is open - service is known to be failing
                with self._state_lock:
                    state.status = ServiceStatus.OFFLINE
                    state.was_offline = True
                return ServiceStatus.OFFLINE

            # Perform appropriate health check
            if service_type == VMServiceType.REDIS:
                is_healthy = await self._check_redis_health(state)
            else:
                is_healthy = await self._check_http_service_health(state)

            if is_healthy:
                with self._state_lock:
                    # Log recovery if service was previously offline
                    if previous_was_offline:
                        logger.info(
                            "VM service %s (%s) is now ONLINE",
                            state.config.name,
                            service_type.value,
                        )

                    state.status = ServiceStatus.ONLINE
                    state.last_success = time.time()
                    state.consecutive_failures = 0
                    state.last_error = None
                    state.was_offline = False
            else:
                with self._state_lock:
                    state.consecutive_failures += 1
                    state.status = ServiceStatus.OFFLINE
                    state.was_offline = True

        except CircuitBreakerOpenError:
            with self._state_lock:
                state.status = ServiceStatus.OFFLINE
                state.was_offline = True
        except Exception as e:
            with self._state_lock:
                state.status = ServiceStatus.OFFLINE
                state.consecutive_failures += 1
                state.last_error = str(e)
                state.was_offline = True

        return state.status

    async def check_all_services(self) -> Dict[VMServiceType, ServiceStatus]:
        """Check health of all registered VM services concurrently."""
        service_types = list(self._services.keys())

        # Run all health checks concurrently using asyncio.gather()
        tasks = [self.check_service_health(stype) for stype in service_types]
        statuses = await asyncio.gather(*tasks, return_exceptions=True)

        # Build results dict, handling any exceptions
        results = {}
        for stype, status in zip(service_types, statuses):
            if isinstance(status, Exception):
                logger.error(
                    "Health check failed for %s: %s", stype.value, status
                )
                results[stype] = ServiceStatus.UNKNOWN
            else:
                results[stype] = status

        return results

    async def start_monitoring(self) -> None:
        """Start background health monitoring task."""
        if self._running:
            logger.warning("VM service monitoring already running")
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._monitoring_loop())
        logger.info(
            "Started VM service monitoring (interval: %ds)",
            self._health_check_interval,
        )

    async def stop_monitoring(self) -> None:
        """Stop background health monitoring task."""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped VM service monitoring")

    async def _monitoring_loop(self) -> None:
        """Background loop that periodically checks service health."""
        while self._running:
            try:
                await self.check_all_services()
                await asyncio.sleep(self._health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in VM service monitoring loop: %s", e)
                await asyncio.sleep(ServiceDiscoveryConfig.ERROR_RECOVERY_DELAY_S)

    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get a comprehensive status summary of all VM services.

        Returns:
            Dictionary with service statuses and metadata
        """
        services = {}
        for stype, state in self._services.items():
            cb = self._circuit_breakers.get(stype)
            cb_state = cb.state.value if cb else "unknown"

            services[stype.value] = {
                "name": state.config.name,
                "status": state.status.value,
                "host": state.config.host,
                "port": state.config.port,
                "is_critical": state.config.is_critical,
                "is_optional": state.config.is_optional,
                "description": state.config.description,
                "circuit_breaker_state": cb_state,
                "consecutive_failures": state.consecutive_failures,
                "last_check": (
                    datetime.fromtimestamp(state.last_check).isoformat()
                    if state.last_check
                    else None
                ),
                "last_success": (
                    datetime.fromtimestamp(state.last_success).isoformat()
                    if state.last_success
                    else None
                ),
                "last_error": state.last_error,
            }

        # Calculate summary statistics
        total = len(services)
        online = sum(1 for s in services.values() if s["status"] == "online")
        offline = sum(1 for s in services.values() if s["status"] == "offline")
        critical_offline = sum(
            1
            for s in services.values()
            if s["status"] == "offline" and s["is_critical"]
        )

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "summary": {
                "total": total,
                "online": online,
                "offline": offline,
                "critical_offline": critical_offline,
                "health_status": (
                    "healthy"
                    if critical_offline == 0
                    else "degraded"
                    if online > 0
                    else "unhealthy"
                ),
            },
            "services": services,
        }

    def mark_service_intentionally_offline(
        self, service_type: VMServiceType, reason: str = "User disabled"
    ) -> None:
        """
        Mark a service as intentionally offline.

        This prevents error logging for services that are known to be stopped.
        """
        state = self._services.get(service_type)
        if state:
            state.status = ServiceStatus.INTENTIONALLY_OFFLINE
            state.last_error = f"Intentionally offline: {reason}"
            logger.info(
                "VM service %s marked as intentionally offline: %s",
                service_type.value,
                reason,
            )


# Global registry instance
_vm_service_registry: Optional[VMServiceRegistry] = None
_registry_lock = threading.Lock()


async def get_vm_service_registry() -> VMServiceRegistry:
    """Get or create the global VM service registry."""
    global _vm_service_registry

    if _vm_service_registry is None:
        with _registry_lock:
            # Double-check pattern for thread safety
            if _vm_service_registry is None:
                _vm_service_registry = VMServiceRegistry()

    return _vm_service_registry


async def initialize_vm_service_monitoring() -> VMServiceRegistry:
    """Initialize and start VM service monitoring."""
    registry = await get_vm_service_registry()
    await registry.start_monitoring()
    return registry


async def shutdown_vm_service_monitoring() -> None:
    """Shutdown VM service monitoring."""
    global _vm_service_registry

    if _vm_service_registry is not None:
        await _vm_service_registry.stop_monitoring()
        _vm_service_registry = None  # Clear reference after shutdown
