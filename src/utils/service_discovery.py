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
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

from src.constants.network_constants import NetworkConstants
from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)


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
    timeout: float = 5.0
    retry_count: int = 3

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
        self.services: Dict[str, ServiceEndpoint] = {}
        # Use project-relative path for config file (this file is in src/utils/)
        default_config = (
            Path(__file__).parent.parent.parent / "config" / "services.json"
        )
        self.config_file = config_file or str(default_config)
        self.health_check_interval = 30  # seconds
        self.circuit_breaker_threshold = 5  # consecutive failures
        self._health_check_task: Optional[asyncio.Task] = None
        self._http_client = get_http_client()  # Use singleton HTTP client

        # Service definitions for AutoBot's 6-VM architecture
        self._init_default_services()

    def _init_default_services(self):
        """Initialize default service definitions from unified configuration"""

        # Get configuration from unified config manager
        from src.unified_config_manager import unified_config_manager

        # Get service configurations
        services_config = unified_config_manager.get_distributed_services_config()
        backend_config = unified_config_manager.get_backend_config()
        redis_config = unified_config_manager.get_redis_config()

        # Get system defaults section for ultimate fallbacks
        system_defaults = (
            unified_config_manager.get_config_section("service_discovery_defaults")
            or {}
        )

        # Helper to get service config from unified configuration
        def get_service_config(service_name, config_dict=None):
            """Get host and port from unified configuration"""
            if config_dict is None:
                config_dict = services_config.get(service_name, {})

            # Get from config, with no hardcoded fallbacks
            # Config must provide these values
            host = config_dict.get("host")
            port = config_dict.get("port")

            if not host or not port:
                logger.error(
                    f"Service {service_name} missing required 'host' or 'port' in configuration"
                )
                # Use system defaults as absolute last resort
                host = host or system_defaults.get(f"{service_name}_host", "localhost")
                port = port or system_defaults.get(f"{service_name}_port", 8000)

            return host, port

        # VM1: Frontend (Web Interface)
        frontend_host, frontend_port = get_service_config("frontend")
        self.services["frontend"] = ServiceEndpoint(
            name="frontend",
            host=frontend_host,
            port=frontend_port,
            protocol="http",
            health_endpoint="/",  # Vue.js app health check
            timeout=10.0,
            required=True,
        )

        # VM2: NPU Worker (AI Hardware Acceleration)
        npu_host, npu_port = get_service_config("npu_worker")
        self.services["npu_worker"] = ServiceEndpoint(
            name="npu_worker",
            host=npu_host,
            port=npu_port,
            protocol="http",
            health_endpoint="/health",
            timeout=15.0,
            required=False,  # Optional AI acceleration
        )

        # VM3: Redis (Data Layer)
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
            protocol="tcp",  # Redis uses TCP, not HTTP
            health_endpoint="",  # Redis PING command
            timeout=5.0,
            required=True,
        )

        # VM4: AI Stack (AI Processing)
        ai_stack_host, ai_stack_port = get_service_config("ai_stack")
        self.services["ai_stack"] = ServiceEndpoint(
            name="ai_stack",
            host=ai_stack_host,
            port=ai_stack_port,
            protocol="http",
            health_endpoint="/health",
            timeout=20.0,
            required=False,  # Optional AI processing
        )

        # VM5: Browser Service (Playwright Automation)
        browser_host, browser_port = get_service_config("browser_service")
        self.services["browser_service"] = ServiceEndpoint(
            name="browser_service",
            host=browser_host,
            port=browser_port,
            protocol="http",
            health_endpoint="/health",
            timeout=10.0,
            required=False,  # Optional browser automation
        )

        # Main Machine (WSL): Backend API
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
            timeout=5.0,
            required=True,
        )

        # Main Machine (WSL): Ollama LLM
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
            health_endpoint="/api/tags",  # Ollama health check
            timeout=10.0,
            required=True,
        )

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
                pass

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
                logger.error(f"Error in health monitor loop: {e}")
                await asyncio.sleep(5)  # Brief pause on error

    async def check_all_services(self) -> Dict[str, ServiceStatus]:
        """Check health of all registered services concurrently"""
        tasks = []

        for service_name in self.services:
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
                logger.error(f"Health check failed for {service_name}: {result}")
                self.services[service_name].status = ServiceStatus.UNHEALTHY
                self.services[service_name].error_message = str(result)
                results[service_name] = ServiceStatus.UNHEALTHY
            else:
                results[service_name] = result

        return results

    async def check_service_health(self, service_name: str) -> ServiceStatus:
        """Check health of a specific service with circuit breaker logic"""
        if service_name not in self.services:
            logger.warning(f"Unknown service: {service_name}")
            return ServiceStatus.UNKNOWN

        service = self.services[service_name]
        start_time = time.time()

        try:
            # Circuit breaker logic
            if service.consecutive_failures >= self.circuit_breaker_threshold:
                # Service is in circuit breaker mode - reduce check frequency
                if service.last_check:
                    time_since_check = (datetime.now() - service.last_check).seconds
                    if time_since_check < (self.health_check_interval * 2):
                        return service.status  # Skip check, too recent

            # Perform health check based on service type
            if service.protocol == "tcp":
                status = await self._check_tcp_service(service)
            else:
                status = await self._check_http_service(service)

            # Update service status
            service.status = status
            service.last_check = datetime.now()
            service.response_time = time.time() - start_time

            if status == ServiceStatus.HEALTHY:
                service.consecutive_failures = 0
                service.last_healthy = datetime.now()
                service.error_message = None
            else:
                service.consecutive_failures += 1

            return status

        except Exception as e:
            service.status = ServiceStatus.UNHEALTHY
            service.last_check = datetime.now()
            service.consecutive_failures += 1
            service.error_message = str(e)
            service.response_time = time.time() - start_time

            logger.error(f"Health check error for {service_name}: {e}")
            return ServiceStatus.UNHEALTHY

    async def _check_http_service(self, service: ServiceEndpoint) -> ServiceStatus:
        """Check HTTP-based service health"""
        try:
            async with await self._http_client.get(
                service.health_url, timeout=aiohttp.ClientTimeout(total=service.timeout)
            ) as response:

                # Check response status
                if response.status == 200:
                    # Try to parse response for additional health info
                    try:
                        data = await response.json()
                        if isinstance(data, dict):
                            # Extract service metadata if available
                            service.version = data.get("version")
                            service.capabilities = data.get("capabilities", [])

                            # Check if response indicates degraded state
                            status_field = data.get("status", "healthy").lower()
                            if status_field in ["degraded", "warning"]:
                                return ServiceStatus.DEGRADED
                    except Exception:
                        pass  # Ignore JSON parsing errors for simple endpoints

                    return ServiceStatus.HEALTHY

                elif response.status in [503, 502, 504]:
                    return ServiceStatus.DEGRADED  # Temporary issues
                else:
                    return ServiceStatus.UNHEALTHY

        except asyncio.TimeoutError:
            return ServiceStatus.UNHEALTHY
        except aiohttp.ClientError:
            return ServiceStatus.UNHEALTHY

    async def _check_tcp_service(self, service: ServiceEndpoint) -> ServiceStatus:
        """Check TCP-based service health (e.g., Redis)

        NOTE: This method uses direct redis.Redis() instantiation intentionally
        for health check diagnostics. This is a monitoring/diagnostic function,
        NOT for production client creation. For production clients, use
        get_redis_client() from src.utils.redis_client.

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
                client = redis.Redis(
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

    def get_service_url(self, service_name: str) -> Optional[str]:
        """Get service URL with automatic failover"""
        if service_name not in self.services:
            return None

        service = self.services[service_name]

        # Check if service is available
        if not service.is_available and service.required:
            logger.warning(f"Required service {service_name} is not available")

        return service.url

    def get_healthy_services(self) -> List[str]:
        """Get list of currently healthy services"""
        return [
            name
            for name, service in self.services.items()
            if service.status == ServiceStatus.HEALTHY
        ]

    def get_service_status_summary(self) -> Dict:
        """Get comprehensive status summary of all services"""
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_services": len(self.services),
            "healthy": 0,
            "degraded": 0,
            "unhealthy": 0,
            "unknown": 0,
            "services": {},
        }

        for name, service in self.services.items():
            status_str = service.status.value
            summary["services"][name] = {
                "status": status_str,
                "url": service.url,
                "required": service.required,
                "last_check": (
                    service.last_check.isoformat() if service.last_check else None
                ),
                "response_time": service.response_time,
                "consecutive_failures": service.consecutive_failures,
                "error": service.error_message,
            }

            # Update counters
            if service.status == ServiceStatus.HEALTHY:
                summary["healthy"] += 1
            elif service.status == ServiceStatus.DEGRADED:
                summary["degraded"] += 1
            elif service.status == ServiceStatus.UNHEALTHY:
                summary["unhealthy"] += 1
            else:
                summary["unknown"] += 1

        return summary

    async def wait_for_service(self, service_name: str, timeout: float = 60.0) -> bool:
        """Wait for a service to become healthy with timeout"""
        if service_name not in self.services:
            return False

        start_time = time.time()

        while time.time() - start_time < timeout:
            status = await self.check_service_health(service_name)
            if status == ServiceStatus.HEALTHY:
                return True

            await asyncio.sleep(2)  # Check every 2 seconds

        return False

    async def wait_for_core_services(
        self, timeout: float = 120.0
    ) -> Tuple[bool, List[str]]:
        """Wait for all required services to become healthy"""
        required_services = [
            name for name, service in self.services.items() if service.required
        ]

        start_time = time.time()
        ready_services = []

        while time.time() - start_time < timeout:
            await self.check_all_services()

            ready_services = [
                name
                for name in required_services
                if self.services[name].status == ServiceStatus.HEALTHY
            ]

            if len(ready_services) == len(required_services):
                return True, ready_services

            missing = set(required_services) - set(ready_services)
            logger.info(f"Waiting for services: {list(missing)}")

            await asyncio.sleep(5)  # Check every 5 seconds

        return False, ready_services


# Global service discovery instance
service_discovery = ServiceDiscovery()


# Convenience functions for backward compatibility
async def get_service_url(service_name: str) -> Optional[str]:
    """Get service URL - backward compatible function"""
    return service_discovery.get_service_url(service_name)


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
        logger.error(f"Failed to auto-start service discovery: {e}")


# Schedule auto-start (will run when event loop is available)
def _schedule_auto_start():
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_auto_start_monitoring())
    except RuntimeError:
        # No running loop, will start manually later
        pass


_schedule_auto_start()
