# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Distributed Service Discovery - Eliminates DNS Resolution Timeouts

This module provides instant service resolution for the distributed VM architecture
by maintaining a local cache of service endpoints and implementing health-based routing.

ROOT CAUSE FIX: Replaces DNS resolution delays with cached service endpoints
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import aiohttp

from constants.network_constants import NetworkConstants
from constants.threshold_constants import ServiceDiscoveryConfig, TimingConstants
from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)


@dataclass
class ServiceEndpoint:
    """Service endpoint with health status"""

    host: str
    port: int
    protocol: str = "http"
    last_check: float = 0
    is_healthy: bool = False
    response_time: float = 0.0

    @property
    def url(self) -> str:
        """Return full URL for this service endpoint."""
        return f"{self.protocol}://{self.host}:{self.port}"

    def is_stale(self, max_age: float = 30.0) -> bool:
        """Check if health status is stale"""
        return time.time() - self.last_check > max_age


class DistributedServiceDiscovery:
    """
    Service discovery for distributed VM architecture

    ELIMINATES DNS TIMEOUTS BY:
    - Maintaining cached service endpoints
    - Async health checking without blocking
    - Instant service resolution
    - Automatic failover to backup endpoints
    """

    def __init__(self):
        """Initialize distributed service discovery with registry."""
        self.services: Dict[str, ServiceEndpoint] = {}
        self.backup_endpoints: Dict[str, list] = {}
        self._health_check_task = None
        self._initialize_service_registry()

    def _initialize_service_registry(self):
        """
        Initialize service registry from unified configuration.

        Issue #281: Refactored from 141 lines to use extracted helper methods.
        """
        from config import unified_config_manager

        # Load configurations
        self._services_config = unified_config_manager.get_distributed_services_config()
        self._backend_config = unified_config_manager.get_backend_config()
        self._redis_config = unified_config_manager.get_redis_config()
        self._system_defaults = (
            unified_config_manager.get_config_section("service_discovery_defaults")
            or {}
        )

        # Build service registries
        primary_services = self._build_primary_services()
        backup_endpoints = self._build_backup_endpoints()

        self.services.update(primary_services)
        self.backup_endpoints.update(backup_endpoints)

        logger.info(
            "🌐 Service registry initialized with %s services", len(self.services)
        )

    def _get_config_value(self, service_name: str, key: str, default_key: str):
        """Get configuration value with fallback to system defaults. Issue #281: Extracted helper."""
        if service_name == "backend":
            value = self._backend_config.get(key)
        elif service_name == "redis":
            value = self._redis_config.get(key)
        else:
            service_config = self._services_config.get(service_name, {})
            value = service_config.get(key)

        if not value:
            value = self._system_defaults.get(
                default_key,
                (
                    NetworkConstants.LOCALHOST_NAME
                    if key == "host"
                    else NetworkConstants.BACKEND_PORT
                ),
            )
        return value

    def _build_primary_services(self) -> Dict[str, ServiceEndpoint]:
        """Build primary service endpoints from configuration. Issue #281: Extracted helper."""
        return {
            "redis": ServiceEndpoint(
                self._get_config_value("redis", "host", "redis_host"),
                self._get_config_value("redis", "port", "redis_port"),
                "redis",
            ),
            "backend": ServiceEndpoint(
                self._get_config_value("backend", "host", "backend_host"),
                self._get_config_value("backend", "port", "backend_port"),
                "http",
            ),
            "frontend": ServiceEndpoint(
                self._get_config_value("frontend", "host", "frontend_host"),
                self._get_config_value("frontend", "port", "frontend_port"),
                "http",
            ),
            "npu_worker": ServiceEndpoint(
                self._get_config_value("npu_worker", "host", "npu_worker_host"),
                self._get_config_value("npu_worker", "port", "npu_worker_port"),
                "http",
            ),
            "ai_stack": ServiceEndpoint(
                self._get_config_value("ai_stack", "host", "ai_stack_host"),
                self._get_config_value("ai_stack", "port", "ai_stack_port"),
                "http",
            ),
            "browser": ServiceEndpoint(
                self._get_config_value(
                    "browser_service", "host", "browser_service_host"
                ),
                self._get_config_value(
                    "browser_service", "port", "browser_service_port"
                ),
                "http",
            ),
            "ollama": ServiceEndpoint(
                self._get_config_value("ollama", "host", "ollama_host"),
                self._get_config_value("ollama", "port", "ollama_port"),
                "http",
            ),
        }

    def _build_backup_endpoints(self) -> Dict[str, list]:
        """Build backup endpoints for failover. Issue #281: Extracted helper."""
        backup_configs = self._system_defaults.get("backup_endpoints", {})
        return {
            "redis": self._build_redis_backups(backup_configs),
            "backend": self._build_backend_backups(backup_configs),
            "ollama": self._build_ollama_backups(backup_configs),
        }

    def _build_redis_backups(self, backup_configs: Dict) -> list:
        """Build Redis backup endpoints. Issue #281: Extracted helper."""
        return [
            ServiceEndpoint(
                backup_configs.get("redis_backup_1_host", "localhost"),
                backup_configs.get(
                    "redis_backup_1_port",
                    self._get_config_value("redis", "port", "redis_port"),
                ),
                "redis",
            ),
            ServiceEndpoint(
                backup_configs.get(
                    "redis_backup_2_host",
                    self._get_config_value("backend", "host", "backend_host"),
                ),
                backup_configs.get(
                    "redis_backup_2_port",
                    self._get_config_value("redis", "port", "redis_port"),
                ),
                "redis",
            ),
        ]

    def _build_backend_backups(self, backup_configs: Dict) -> list:
        """Build backend backup endpoints. Issue #281: Extracted helper."""
        return [
            ServiceEndpoint(
                backup_configs.get("backend_backup_1_host", "localhost"),
                backup_configs.get(
                    "backend_backup_1_port",
                    self._get_config_value("backend", "port", "backend_port"),
                ),
                "http",
            ),
        ]

    def _build_ollama_backups(self, backup_configs: Dict) -> list:
        """Build Ollama backup endpoints. Issue #281: Extracted helper."""
        return [
            ServiceEndpoint(
                backup_configs.get(
                    "ollama_backup_1_host",
                    self._get_config_value("ai_stack", "host", "ai_stack_host"),
                ),
                backup_configs.get(
                    "ollama_backup_1_port",
                    self._get_config_value("ollama", "port", "ollama_port"),
                ),
                "http",
            ),
            ServiceEndpoint(
                backup_configs.get(
                    "ollama_backup_2_host",
                    self._get_config_value("npu_worker", "host", "npu_worker_host"),
                ),
                backup_configs.get(
                    "ollama_backup_2_port",
                    self._get_config_value("ollama", "port", "ollama_port"),
                ),
                "http",
            ),
        ]

    async def get_service_endpoint(
        self, service_name: str
    ) -> Optional[ServiceEndpoint]:
        """
        Get healthy service endpoint instantly (no DNS resolution delays)

        ELIMINATES TIMEOUTS BY:
        - Returning cached healthy endpoints immediately
        - No DNS resolution required
        - Automatic failover to backup endpoints
        """

        # Check primary endpoint
        if service_name in self.services:
            endpoint = self.services[service_name]

            # Return immediately if recently checked and healthy
            if not endpoint.is_stale() and endpoint.is_healthy:
                return endpoint

            # Quick async health check (non-blocking)
            if await self._quick_health_check(endpoint):
                return endpoint

        # Try backup endpoints if primary failed
        if service_name in self.backup_endpoints:
            for backup in self.backup_endpoints[service_name]:
                if await self._quick_health_check(backup):
                    logger.warning(
                        f"🔄 Using backup endpoint for {service_name}: {backup.url}"
                    )
                    return backup

        # Return primary even if unhealthy (let caller handle)
        return self.services.get(service_name)

    async def _quick_health_check(self, endpoint: ServiceEndpoint) -> bool:
        """
        Non-blocking health check with immediate return

        ELIMINATES BLOCKING BY:
        - Using asyncio.timeout with very short duration
        - Returns immediately on success/failure
        - No waiting or retry logic
        """
        try:
            if endpoint.protocol == "redis":
                return await self._check_redis_health(endpoint)
            else:
                return await self._check_http_health(endpoint)
        except Exception as e:
            logger.debug("Health check failed for %s: %s", endpoint.url, e)
            endpoint.is_healthy = False
            endpoint.last_check = time.time()
            return False

    async def _check_redis_health(self, endpoint: ServiceEndpoint) -> bool:
        """Quick Redis connection test

        NOTE: This method uses direct redis.Redis() instantiation intentionally
        for health check diagnostics. This is a monitoring/diagnostic function,
        NOT for production client creation. For production clients, use
        get_redis_client() from autobot_shared.redis_client.

        Direct instantiation is appropriate here because:
        - Tests arbitrary endpoints with strict 100ms timeouts
        - Creates fresh connections (no pooling) to test raw connectivity
        - Measures actual response times for health monitoring
        - No retries wanted (immediate failure detection)
        """
        try:
            import redis.asyncio as redis

            # Direct instantiation for health check (intentional exception to canonical pattern)
            # Immediate connection test (no retries)
            client = redis.Redis(
                host=endpoint.host,
                port=endpoint.port,
                socket_connect_timeout=0.1,  # 100ms max
                socket_timeout=0.1,
                retry_on_timeout=False,
                health_check_interval=0,
            )

            start_time = time.time()
            await client.ping()
            response_time = time.time() - start_time
            await client.aclose()

            endpoint.is_healthy = True
            endpoint.response_time = response_time
            endpoint.last_check = time.time()

            return True

        except Exception:
            endpoint.is_healthy = False
            endpoint.last_check = time.time()
            return False

    async def _try_health_url(
        self,
        url: str,
        http_client,
        timeout,
        start_time: float,
        endpoint: ServiceEndpoint,
    ) -> bool:
        """Try a single health URL check. (Issue #315 - extracted)"""
        try:
            async with await http_client.get(url, timeout=timeout) as response:
                if response.status < 500:  # Accept 2xx, 3xx, 4xx
                    endpoint.is_healthy = True
                    endpoint.response_time = time.time() - start_time
                    endpoint.last_check = time.time()
                    return True
        except Exception:
            pass  # nosec B110 - intentional fallback for health check failures
        return False

    async def _check_http_health(self, endpoint: ServiceEndpoint) -> bool:
        """Quick HTTP health check (Issue #315 - uses helper)"""
        try:
            timeout = aiohttp.ClientTimeout(total=0.2, connect=0.1)  # 200ms max
            http_client = get_http_client()
            start_time = time.time()

            # Try health endpoint first, then root
            health_urls = [f"{endpoint.url}/health", f"{endpoint.url}/", endpoint.url]
            for url in health_urls:
                if await self._try_health_url(
                    url, http_client, timeout, start_time, endpoint
                ):
                    return True

            endpoint.is_healthy = False
            endpoint.last_check = time.time()
            return False
        except Exception:
            endpoint.is_healthy = False
            endpoint.last_check = time.time()
            return False

    async def get_redis_connection_params(self) -> Dict:
        """
        Get Redis connection parameters with instant resolution

        ELIMINATES DNS TIMEOUT BY:
        - Using cached IP addresses
        - Immediate parameter return
        - Built-in failover logic
        """
        endpoint = await self.get_service_endpoint("redis")
        if not endpoint:
            raise ConnectionError("No Redis endpoint available")

        return {
            "host": endpoint.host,
            "port": endpoint.port,
            "decode_responses": True,
            "socket_connect_timeout": 0.1,  # Very short, non-blocking
            "socket_timeout": 0.5,
            "retry_on_timeout": False,
            "health_check_interval": 0,
            "max_connections": 5,
        }

    def start_background_health_monitoring(self):
        """Start background health monitoring (optional)"""
        if not self._health_check_task:
            self._health_check_task = asyncio.create_task(
                self._background_health_monitor()
            )

    async def _background_health_monitor(self):
        """Background task to keep service health updated"""
        while True:
            try:
                # Check all services in parallel
                tasks = []
                for service_name, endpoint in self.services.items():
                    if endpoint.is_stale(
                        TimingConstants.STANDARD_TIMEOUT
                    ):  # Check stale services
                        task = asyncio.create_task(self._quick_health_check(endpoint))
                        tasks.append((service_name, task))

                if tasks:
                    await asyncio.gather(
                        *[task for _, task in tasks], return_exceptions=True
                    )

                await asyncio.sleep(
                    ServiceDiscoveryConfig.HEALTH_CHECK_INTERVAL_S
                )  # Check every 30 seconds

            except Exception as e:
                logger.error("Background health monitoring error: %s", e)
                await asyncio.sleep(
                    TimingConstants.STANDARD_TIMEOUT
                )  # Back off on errors


# Global instance for easy access (thread-safe)
import asyncio as _asyncio_lock

_service_discovery = None
_service_discovery_lock = _asyncio_lock.Lock()


async def get_service_discovery() -> DistributedServiceDiscovery:
    """Get global service discovery instance (thread-safe)"""
    global _service_discovery
    if not _service_discovery:
        async with _service_discovery_lock:
            # Double-check after acquiring lock
            if not _service_discovery:
                _service_discovery = DistributedServiceDiscovery()
                _service_discovery.start_background_health_monitoring()
    return _service_discovery


async def get_service_url(service_name: str) -> str:
    """Quick service URL resolution without DNS delays"""
    from config import unified_config_manager

    discovery = await get_service_discovery()
    endpoint = await discovery.get_service_endpoint(service_name)

    if endpoint:
        return endpoint.url
    else:
        # Configuration-driven fallback
        system_defaults = (
            unified_config_manager.get_config_section("service_discovery_defaults")
            or {}
        )
        fallback_host = system_defaults.get(
            "fallback_host", NetworkConstants.LOCALHOST_NAME
        )
        fallback_port = system_defaults.get(
            "fallback_port", NetworkConstants.BACKEND_PORT
        )
        return f"http://{fallback_host}:{fallback_port}"


# Synchronous helpers for backward compatibility with sync Redis clients
def get_redis_connection_params_sync() -> Dict:
    """
    Get Redis connection parameters synchronously for sync contexts

    ELIMINATES DNS TIMEOUT BY:
    - Using pre-configured values from unified configuration
    - Immediate parameter return without async overhead
    - Configuration-driven fallback addresses

    Returns same dict structure as config-based approach for backward compatibility
    """
    from config import unified_config_manager

    # Get Redis configuration from unified config manager
    redis_config = unified_config_manager.get_redis_config()
    system_defaults = (
        unified_config_manager.get_config_section("service_discovery_defaults") or {}
    )

    # Get host and port from configuration
    host = redis_config.get("host") or system_defaults.get(
        "redis_host", NetworkConstants.LOCALHOST_NAME
    )
    port = redis_config.get("port") or system_defaults.get(
        "redis_port", NetworkConstants.REDIS_PORT
    )

    # Return cached endpoint parameters immediately
    return {
        "host": host,
        "port": int(port),
        "decode_responses": True,
        "socket_connect_timeout": 0.5,  # Fast timeout for distributed setup
        "socket_timeout": 1.0,
        "retry_on_timeout": False,
        "health_check_interval": 0,
        "max_connections": 10,
    }


def _get_sync_config_value(
    svc_name: str,
    key: str,
    default_key: str,
    default_val,
    services_config: Dict,
    backend_config: Dict,
    redis_config: Dict,
    system_defaults: Dict,
):
    """Get service config value with fallback to defaults.

    Issue #620.
    """
    if svc_name == "backend":
        val = backend_config.get(key)
    elif svc_name == "redis":
        val = redis_config.get(key)
    else:
        svc_cfg = services_config.get(svc_name, {})
        val = svc_cfg.get(key)
    return val or system_defaults.get(default_key, default_val)


def _create_service_endpoint_dict(
    host: str,
    port: int,
    protocol: str,
) -> Dict[str, Any]:
    """Create a service endpoint dictionary with host, port, and protocol.

    Issue #620.
    """
    return {"host": host, "port": port, "protocol": protocol}


def _build_core_service_endpoints(
    get_val_fn,
) -> Dict[str, Dict]:
    """Build core service endpoints (redis, backend, frontend).

    Issue #620.
    """
    return {
        "redis": _create_service_endpoint_dict(
            get_val_fn("redis", "host", "redis_host", NetworkConstants.LOCALHOST_NAME),
            int(get_val_fn("redis", "port", "redis_port", NetworkConstants.REDIS_PORT)),
            "redis",
        ),
        "backend": _create_service_endpoint_dict(
            get_val_fn(
                "backend", "host", "backend_host", NetworkConstants.LOCALHOST_NAME
            ),
            int(
                get_val_fn(
                    "backend", "port", "backend_port", NetworkConstants.BACKEND_PORT
                )
            ),
            "http",
        ),
        "frontend": _create_service_endpoint_dict(
            get_val_fn(
                "frontend", "host", "frontend_host", NetworkConstants.LOCALHOST_NAME
            ),
            int(
                get_val_fn(
                    "frontend", "port", "frontend_port", NetworkConstants.FRONTEND_PORT
                )
            ),
            "http",
        ),
    }


def _build_worker_service_endpoints(
    get_val_fn,
) -> Dict[str, Dict]:
    """Build worker service endpoints (npu_worker, ai_stack).

    Issue #620.
    """
    return {
        "npu_worker": _create_service_endpoint_dict(
            get_val_fn(
                "npu_worker", "host", "npu_worker_host", NetworkConstants.LOCALHOST_NAME
            ),
            int(
                get_val_fn(
                    "npu_worker",
                    "port",
                    "npu_worker_port",
                    NetworkConstants.NPU_WORKER_PORT,
                )
            ),
            "http",
        ),
        "ai_stack": _create_service_endpoint_dict(
            get_val_fn(
                "ai_stack", "host", "ai_stack_host", NetworkConstants.LOCALHOST_NAME
            ),
            int(
                get_val_fn(
                    "ai_stack", "port", "ai_stack_port", NetworkConstants.AI_STACK_PORT
                )
            ),
            "http",
        ),
    }


def _build_auxiliary_service_endpoints(
    get_val_fn,
) -> Dict[str, Dict]:
    """Build auxiliary service endpoints (browser, ollama).

    Issue #620.
    """
    return {
        "browser": _create_service_endpoint_dict(
            get_val_fn(
                "browser_service",
                "host",
                "browser_service_host",
                NetworkConstants.LOCALHOST_NAME,
            ),
            int(
                get_val_fn(
                    "browser_service",
                    "port",
                    "browser_service_port",
                    NetworkConstants.BROWSER_SERVICE_PORT,
                )
            ),
            "http",
        ),
        "ollama": _create_service_endpoint_dict(
            get_val_fn(
                "ollama", "host", "ollama_host", NetworkConstants.LOCALHOST_NAME
            ),
            int(
                get_val_fn(
                    "ollama", "port", "ollama_port", NetworkConstants.OLLAMA_PORT
                )
            ),
            "http",
        ),
    }


def _build_service_endpoints_map(
    services_config: Dict,
    backend_config: Dict,
    redis_config: Dict,
    system_defaults: Dict,
) -> Dict[str, Dict]:
    """Build the service endpoints mapping from configuration.

    Issue #620.
    """

    def get_val(svc_name, key, default_key, default_val):
        return _get_sync_config_value(
            svc_name,
            key,
            default_key,
            default_val,
            services_config,
            backend_config,
            redis_config,
            system_defaults,
        )

    endpoints: Dict[str, Dict] = {}
    endpoints.update(_build_core_service_endpoints(get_val))
    endpoints.update(_build_worker_service_endpoints(get_val))
    endpoints.update(_build_auxiliary_service_endpoints(get_val))
    return endpoints


def get_service_endpoint_sync(service_name: str) -> Optional[Dict]:
    """Get service endpoint synchronously for sync contexts.

    Returns endpoint information as a dict with host, port, protocol.
    Gets values from unified configuration.
    """
    from config import unified_config_manager

    # Get configurations
    services_config = unified_config_manager.get_distributed_services_config()
    backend_config = unified_config_manager.get_backend_config()
    redis_config = unified_config_manager.get_redis_config()
    system_defaults = (
        unified_config_manager.get_config_section("service_discovery_defaults") or {}
    )

    # Build service endpoints using helper (Issue #620)
    service_endpoints = _build_service_endpoints_map(
        services_config, backend_config, redis_config, system_defaults
    )

    return service_endpoints.get(service_name)
