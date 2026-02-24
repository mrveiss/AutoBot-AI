#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Discovery System for AutoBot Distributed Architecture
Provides dynamic service resolution and health monitoring across 6 VMs
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import aiohttp
from constants.network_constants import NetworkConstants
from constants.path_constants import PATH
from constants.threshold_constants import RetryConfig, ServiceDiscoveryConfig

from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for service health checks (Issue #326)
DEGRADED_STATUS_FIELDS = {"degraded", "warning"}
SERVICE_UNAVAILABLE_HTTP_CODES = {503, 502, 504}


def _parse_health_response(
    data: dict, service: "ServiceEndpoint"
) -> Optional["ServiceStatus"]:
    """Parse health response JSON for service status (Issue #315: extracted).

    Args:
        data: Parsed JSON response from health endpoint
        service: Service endpoint to update with metadata

    Returns:
        ServiceStatus.DEGRADED if degraded, None if healthy
    """
    # Extract service metadata if available
    service.version = data.get("version")
    service.capabilities = data.get("capabilities", [])

    # Check if response indicates degraded state
    status_field = data.get("status", "healthy").lower()
    if status_field in DEGRADED_STATUS_FIELDS:
        return ServiceStatus.DEGRADED

    return None  # Healthy


class ServiceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    STARTING = "starting"


@dataclass
class ServiceEndpoint:
    """Represents a service endpoint with discovery and health information"""

    name: str
    host: str
    port: int
    protocol: str = "http"
    health_endpoint: str = "/health"
    required: bool = True
    timeout: float = ServiceDiscoveryConfig.BACKEND_TIMEOUT
    retry_count: int = RetryConfig.DEFAULT_RETRIES

    # Health status tracking
    status: ServiceStatus = ServiceStatus.UNKNOWN
    last_check: Optional[datetime] = None
    last_healthy: Optional[datetime] = None
    consecutive_failures: int = 0
    response_time: Optional[float] = None
    error_message: Optional[str] = None

    # Service metadata
    version: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        """Get the complete service URL"""
        return f"{self.protocol}://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        """Get the complete health check URL"""
        return f"{self.url}{self.health_endpoint}"

    @property
    def is_available(self) -> bool:
        """Check if service is currently available"""
        return self.status in [ServiceStatus.HEALTHY, ServiceStatus.DEGRADED]


class ServiceDiscovery:
    """
    Centralized service discovery and health monitoring system
    Eliminates hardcoded IP addresses and provides dynamic service resolution
    """

    def __init__(self, config_file: Optional[str] = None):
        """Initialize service discovery with config file and health checks."""
        self.services: Dict[str, ServiceEndpoint] = {}
        # Use centralized PathConstants (Issue #380)
        default_config = PATH.CONFIG_DIR / "services.json"
        self.config_file = config_file or str(default_config)
        self.health_check_interval = ServiceDiscoveryConfig.HEALTH_CHECK_INTERVAL_S
        self.circuit_breaker_threshold = (
            ServiceDiscoveryConfig.CIRCUIT_BREAKER_THRESHOLD
        )
        self._health_check_task: Optional[asyncio.Task] = None
        self._http_client = get_http_client()  # Use singleton HTTP client

        # Lock for thread-safe access to services dictionary
        self._lock = asyncio.Lock()

        # Service definitions for AutoBot's 6-VM architecture
        self._init_default_services()

    def _get_service_config_with_fallback(
        self, service_name: str, config_dict: Optional[dict], system_defaults: dict
    ) -> tuple:
        """Get host and port from config with system defaults fallback."""
        if config_dict is None:
            config_dict = {}
        host = config_dict.get("host")
        port = config_dict.get("port")
        if not host or not port:
            logger.error(
                "Service %s missing required 'host' or 'port' in configuration",
                service_name,
            )
            host = host or system_defaults.get(f"{service_name}_host", "localhost")
            port = port or system_defaults.get(f"{service_name}_port", 8000)
        return host, port

    def _register_frontend_service(
        self, services_config: dict, system_defaults: dict
    ) -> None:
        """Register VM1: Frontend (Web Interface) service."""
        host, port = self._get_service_config_with_fallback(
            "frontend", services_config.get("frontend", {}), system_defaults
        )
        self.services["frontend"] = ServiceEndpoint(
            name="frontend",
            host=host,
            port=port,
            protocol="http",
            health_endpoint="/",
            timeout=ServiceDiscoveryConfig.FRONTEND_TIMEOUT,
            required=True,
        )

    def _register_npu_worker_service(
        self, services_config: dict, system_defaults: dict
    ) -> None:
        """Register VM2: NPU Worker (AI Hardware Acceleration) service."""
        host, port = self._get_service_config_with_fallback(
            "npu_worker", services_config.get("npu_worker", {}), system_defaults
        )
        self.services["npu_worker"] = ServiceEndpoint(
            name="npu_worker",
            host=host,
            port=port,
            protocol="http",
            health_endpoint="/health",
            timeout=ServiceDiscoveryConfig.NPU_WORKER_TIMEOUT,
            required=False,
        )

    def _register_redis_service(
        self, redis_config: dict, system_defaults: dict
    ) -> None:
        """Register VM3: Redis (Data Layer) service."""
        redis_host = redis_config.get("host")
        redis_port = redis_config.get("port")
        if not redis_host or not redis_port:
            logger.error("Redis configuration missing required 'host' or 'port'")
            redis_host = redis_host or system_defaults.get(
                "redis_host", NetworkConstants.REDIS_VM_IP
            )
            redis_port = redis_port or system_defaults.get(
                "redis_port", NetworkConstants.REDIS_PORT
            )
        self.services["redis"] = ServiceEndpoint(
            name="redis",
            host=redis_host,
            port=int(redis_port),
            protocol="tcp",
            health_endpoint="",
            timeout=ServiceDiscoveryConfig.REDIS_TIMEOUT,
            required=True,
        )

    def _register_ai_stack_service(
        self, services_config: dict, system_defaults: dict
    ) -> None:
        """Register VM4: AI Stack (AI Processing) service."""
        host, port = self._get_service_config_with_fallback(
            "ai_stack", services_config.get("ai_stack", {}), system_defaults
        )
        self.services["ai_stack"] = ServiceEndpoint(
            name="ai_stack",
            host=host,
            port=port,
            protocol="http",
            health_endpoint="/health",
            timeout=ServiceDiscoveryConfig.AI_STACK_TIMEOUT,
            required=False,
        )

    def _register_browser_service(
        self, services_config: dict, system_defaults: dict
    ) -> None:
        """Register VM5: Browser Service (Playwright Automation)."""
        host, port = self._get_service_config_with_fallback(
            "browser_service",
            services_config.get("browser_service", {}),
            system_defaults,
        )
        self.services["browser_service"] = ServiceEndpoint(
            name="browser_service",
            host=host,
            port=port,
            protocol="http",
            health_endpoint="/health",
            timeout=ServiceDiscoveryConfig.BROWSER_SERVICE_TIMEOUT,
            required=False,
        )

    def _register_backend_service(
        self, backend_config: dict, system_defaults: dict
    ) -> None:
        """Register Main Machine (WSL): Backend API service."""
        backend_host = backend_config.get("host")
        backend_port = backend_config.get("port")
        if not backend_host or not backend_port:
            logger.error("Backend configuration missing required 'host' or 'port'")
            backend_host = backend_host or system_defaults.get(
                "backend_host", NetworkConstants.LOCALHOST_NAME
            )
            backend_port = backend_port or system_defaults.get(
                "backend_port", NetworkConstants.BACKEND_PORT
            )
        self.services["backend"] = ServiceEndpoint(
            name="backend",
            host=backend_host,
            port=int(backend_port),
            protocol="http",
            health_endpoint="/api/health",
            timeout=ServiceDiscoveryConfig.BACKEND_TIMEOUT,
            required=True,
        )

    def _register_ollama_service(
        self, services_config: dict, system_defaults: dict
    ) -> None:
        """Register Main Machine (WSL): Ollama LLM service."""
        ollama_config = services_config.get("ollama", {})
        ollama_host = ollama_config.get("host")
        ollama_port = ollama_config.get("port")
        if not ollama_host or not ollama_port:
            logger.error("Ollama configuration missing required 'host' or 'port'")
            ollama_host = ollama_host or system_defaults.get(
                "ollama_host", NetworkConstants.LOCALHOST_NAME
            )
            ollama_port = ollama_port or system_defaults.get(
                "ollama_port", NetworkConstants.OLLAMA_PORT
            )
        self.services["ollama"] = ServiceEndpoint(
            name="ollama",
            host=ollama_host,
            port=int(ollama_port),
            protocol="http",
            health_endpoint="/api/tags",
            timeout=ServiceDiscoveryConfig.OLLAMA_TIMEOUT,
            required=True,
        )

    def _init_default_services(self):
        """Initialize default service definitions from unified configuration."""
        from config import unified_config_manager

        services_config = unified_config_manager.get_distributed_services_config()
        backend_config = unified_config_manager.get_backend_config()
        redis_config = unified_config_manager.get_redis_config()
        system_defaults = (
            unified_config_manager.get_config_section("service_discovery_defaults")
            or {}
        )

        # Register all services
        self._register_frontend_service(services_config, system_defaults)
        self._register_npu_worker_service(services_config, system_defaults)
        self._register_redis_service(redis_config, system_defaults)
        self._register_ai_stack_service(services_config, system_defaults)
        self._register_browser_service(services_config, system_defaults)
        self._register_backend_service(backend_config, system_defaults)
        self._register_ollama_service(services_config, system_defaults)

    async def start_health_monitoring(self):
        """Start continuous health monitoring of all services"""
        if self._health_check_task and not self._health_check_task.done():
            return  # Already running

        # HTTP client singleton handles session management
        self._health_check_task = asyncio.create_task(self._health_monitor_loop())
        logger.info("Started continuous health monitoring for all services")

    async def stop_health_monitoring(self):
        """Stop health monitoring and clean up resources"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                logger.debug("Health check task cancelled during shutdown")

        # Session cleanup is handled by singleton HTTPClientManager
        logger.info("Stopped health monitoring")

    async def _health_monitor_loop(self):
        """Continuous health monitoring loop"""
        while True:
            try:
                await self.check_all_services()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in health monitor loop: %s", e)
                await asyncio.sleep(ServiceDiscoveryConfig.ERROR_RECOVERY_DELAY_S)

    async def check_all_services(self) -> Dict[str, ServiceStatus]:
        """Check health of all registered services concurrently (thread-safe)"""
        tasks = []

        # Get service names under lock
        async with self._lock:
            service_names = list(self.services.keys())

        for service_name in service_names:
            task = asyncio.create_task(
                self.check_service_health(service_name),
                name=f"health_check_{service_name}",
            )
            tasks.append((service_name, task))

        results = {}
        completed_tasks = await asyncio.gather(
            *[task for _, task in tasks], return_exceptions=True
        )

        for i, (service_name, _) in enumerate(tasks):
            result = completed_tasks[i]
            if isinstance(result, Exception):
                logger.error("Health check failed for %s: %s", service_name, result)
                # Update service status under lock
                async with self._lock:
                    if service_name in self.services:
                        self.services[service_name].status = ServiceStatus.UNHEALTHY
                        self.services[service_name].error_message = str(result)
                results[service_name] = ServiceStatus.UNHEALTHY
            else:
                results[service_name] = result

        return results

    def _should_skip_circuit_breaker_check(
        self,
        consecutive_failures: int,
        last_check: Optional[datetime],
        current_status: ServiceStatus,
    ) -> Optional[ServiceStatus]:
        """Check if health check should be skipped due to circuit breaker. Returns status to skip with, or None."""
        if consecutive_failures < self.circuit_breaker_threshold:
            return None
        if not last_check:
            return None
        time_since_check = (datetime.now() - last_check).seconds
        check_threshold = (
            self.health_check_interval
            * ServiceDiscoveryConfig.CIRCUIT_BREAKER_CHECK_MULTIPLIER
        )
        return current_status if time_since_check < check_threshold else None

    async def _update_service_health_status(
        self, service: ServiceEndpoint, status: ServiceStatus, response_time: float
    ) -> None:
        """Update service status after health check (under lock)."""
        async with self._lock:
            service.status = status
            service.last_check = datetime.now()
            service.response_time = response_time
            if status == ServiceStatus.HEALTHY:
                service.consecutive_failures = 0
                service.last_healthy = datetime.now()
                service.error_message = None
            else:
                service.consecutive_failures += 1

    async def _update_service_error_status(
        self, service: ServiceEndpoint, error: str, response_time: float
    ) -> None:
        """Update service status after health check error (under lock)."""
        async with self._lock:
            service.status = ServiceStatus.UNHEALTHY
            service.last_check = datetime.now()
            service.consecutive_failures += 1
            service.error_message = error
            service.response_time = response_time

    async def check_service_health(self, service_name: str) -> ServiceStatus:
        """Check health of a specific service with circuit breaker logic (thread-safe)."""
        async with self._lock:
            if service_name not in self.services:
                logger.warning("Unknown service: %s", service_name)
                return ServiceStatus.UNKNOWN
            service = self.services[service_name]
            consecutive_failures = service.consecutive_failures
            last_check = service.last_check
            current_status = service.status
            protocol = service.protocol

        if skip_status := self._should_skip_circuit_breaker_check(
            consecutive_failures, last_check, current_status
        ):
            return skip_status

        start_time = time.time()
        try:
            if protocol == "tcp":
                status = await self._check_tcp_service(service)
            else:
                status = await self._check_http_service(service)
            await self._update_service_health_status(
                service, status, time.time() - start_time
            )
            return status
        except Exception as e:
            await self._update_service_error_status(
                service, str(e), time.time() - start_time
            )
            logger.error("Health check error for %s: %s", service_name, e)
            return ServiceStatus.UNHEALTHY

    async def _check_http_service(self, service: ServiceEndpoint) -> ServiceStatus:
        """Check HTTP-based service health (Issue #315: refactored for reduced nesting)."""
        try:
            async with await self._http_client.get(
                service.health_url, timeout=aiohttp.ClientTimeout(total=service.timeout)
            ) as response:
                return await self._evaluate_http_response(response, service)

        except asyncio.TimeoutError:
            return ServiceStatus.UNHEALTHY
        except aiohttp.ClientError:
            return ServiceStatus.UNHEALTHY

    async def _evaluate_http_response(
        self, response: aiohttp.ClientResponse, service: ServiceEndpoint
    ) -> ServiceStatus:
        """Evaluate HTTP response and determine service status (Issue #315: extracted).

        Args:
            response: HTTP response from health endpoint
            service: Service endpoint to update with metadata

        Returns:
            ServiceStatus based on response
        """
        if response.status != 200:
            if response.status in SERVICE_UNAVAILABLE_HTTP_CODES:
                return ServiceStatus.DEGRADED  # Temporary issues
            return ServiceStatus.UNHEALTHY

        # Try to parse response for additional health info
        try:
            data = await response.json()
            if isinstance(data, dict):
                degraded = _parse_health_response(data, service)
                if degraded:
                    return degraded
        except Exception:
            logger.debug("Suppressed exception in try block", exc_info=True)

        return ServiceStatus.HEALTHY

    async def _check_tcp_service(self, service: ServiceEndpoint) -> ServiceStatus:
        """Check TCP-based service health (e.g., Redis)

        NOTE: This method uses direct Redis instantiation intentionally
        for health check diagnostics. This is a monitoring/diagnostic function,
        NOT for production client creation. For production clients, use
        get_redis_client() from autobot_shared.redis_client.

        Direct instantiation is appropriate here because:
        - Tests arbitrary endpoints (not just canonical Redis VM)
        - Uses custom strict timeouts for fast failure detection
        - Creates fresh connections (no pooling) to test raw connectivity
        - Measures actual response times for health monitoring
        """
        try:
            # For Redis specifically
            if service.name == "redis":
                import redis.asyncio as redis

                # Direct instantiation for health check (intentional exception to canonical pattern)
                client = redis.Redis(  # noqa: redis
                    host=service.host,
                    port=service.port,
                    socket_timeout=service.timeout,
                    socket_connect_timeout=service.timeout,
                )

                # Send PING command
                pong = await client.ping()
                await client.close()

                return ServiceStatus.HEALTHY if pong else ServiceStatus.UNHEALTHY

            else:
                # Generic TCP connection test
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(service.host, service.port),
                    timeout=service.timeout,
                )
                writer.close()
                await writer.wait_closed()
                return ServiceStatus.HEALTHY

        except Exception:
            return ServiceStatus.UNHEALTHY

    async def get_service_url(self, service_name: str) -> Optional[str]:
        """Get service URL with automatic failover (thread-safe)"""
        async with self._lock:
            if service_name not in self.services:
                return None

            service = self.services[service_name]

            # Check if service is available
            if not service.is_available and service.required:
                logger.warning("Required service %s is not available", service_name)

            return service.url

    async def get_healthy_services(self) -> List[str]:
        """Get list of currently healthy services (thread-safe)"""
        async with self._lock:
            return [
                name
                for name, service in self.services.items()
                if service.status == ServiceStatus.HEALTHY
            ]

    def _format_service_data(self, service_data: dict) -> dict:
        """Format service data for summary output."""
        return {
            "status": service_data["status"].value,
            "url": service_data["url"],
            "required": service_data["required"],
            "last_check": (
                service_data["last_check"].isoformat()
                if service_data["last_check"]
                else None
            ),
            "response_time": service_data["response_time"],
            "consecutive_failures": service_data["consecutive_failures"],
            "error": service_data["error"],
        }

    def _update_status_counters(self, status: ServiceStatus, summary: dict) -> None:
        """Update summary status counters based on service status."""
        counter_map = {
            ServiceStatus.HEALTHY: "healthy",
            ServiceStatus.DEGRADED: "degraded",
            ServiceStatus.UNHEALTHY: "unhealthy",
        }
        key = counter_map.get(status, "unknown")
        summary[key] += 1

    async def get_service_status_summary(self) -> Dict:
        """Get comprehensive status summary of all services (thread-safe)."""
        async with self._lock:
            services_snapshot = {
                name: {
                    "status": s.status,
                    "url": s.url,
                    "required": s.required,
                    "last_check": s.last_check,
                    "response_time": s.response_time,
                    "consecutive_failures": s.consecutive_failures,
                    "error": s.error_message,
                }
                for name, s in self.services.items()
            }

        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_services": len(services_snapshot),
            "healthy": 0,
            "degraded": 0,
            "unhealthy": 0,
            "unknown": 0,
            "services": {},
        }

        for name, service_data in services_snapshot.items():
            summary["services"][name] = self._format_service_data(service_data)
            self._update_status_counters(service_data["status"], summary)

        return summary

    async def wait_for_service(
        self,
        service_name: str,
        timeout: float = ServiceDiscoveryConfig.DEFAULT_SERVICE_WAIT_TIMEOUT,
    ) -> bool:
        """Wait for a service to become healthy with timeout (thread-safe)"""
        async with self._lock:
            if service_name not in self.services:
                return False

        start_time = time.time()

        while time.time() - start_time < timeout:
            status = await self.check_service_health(service_name)
            if status == ServiceStatus.HEALTHY:
                return True

            await asyncio.sleep(ServiceDiscoveryConfig.SERVICE_WAIT_INTERVAL_S)

        return False

    async def wait_for_core_services(
        self, timeout: float = ServiceDiscoveryConfig.CORE_SERVICES_WAIT_TIMEOUT
    ) -> Tuple[bool, List[str]]:
        """Wait for all required services to become healthy (thread-safe)"""
        # Get required services under lock
        async with self._lock:
            required_services = [
                name for name, service in self.services.items() if service.required
            ]

        start_time = time.time()
        ready_services = []

        while time.time() - start_time < timeout:
            await self.check_all_services()

            # Check service statuses under lock
            async with self._lock:
                ready_services = [
                    name
                    for name in required_services
                    if name in self.services
                    and self.services[name].status == ServiceStatus.HEALTHY
                ]

            if len(ready_services) == len(required_services):
                return True, ready_services

            missing = set(required_services) - set(ready_services)
            logger.info("Waiting for services: %s", list(missing))

            await asyncio.sleep(ServiceDiscoveryConfig.CORE_SERVICES_WAIT_INTERVAL_S)

        return False, ready_services


# Global service discovery instance
service_discovery = ServiceDiscovery()


# Convenience functions for backward compatibility
async def get_service_url(service_name: str) -> Optional[str]:
    """Get service URL - backward compatible function"""
    return await service_discovery.get_service_url(service_name)


async def check_service_health(service_name: str) -> ServiceStatus:
    """Check specific service health - backward compatible function"""
    return await service_discovery.check_service_health(service_name)


async def get_all_service_health() -> Dict[str, ServiceStatus]:
    """Get health status of all services - backward compatible function"""
    return await service_discovery.check_all_services()


# Auto-start health monitoring when module is imported
async def _auto_start_monitoring():
    """Auto-start health monitoring in background"""
    try:
        await service_discovery.start_health_monitoring()
    except Exception as e:
        logger.error("Failed to auto-start service discovery: %s", e)


# Schedule auto-start (will run when event loop is available)
def _schedule_auto_start():
    """Schedule auto-start of service discovery when event loop is available."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_auto_start_monitoring())
    except RuntimeError:
        # No running loop, will start manually later
        pass


_schedule_auto_start()
