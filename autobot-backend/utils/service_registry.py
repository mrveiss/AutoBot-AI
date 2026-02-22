# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Service Registry
=======================

Provides service discovery and configuration management for distributed deployments.
Supports multiple deployment patterns: single-machine, Docker Compose, and distributed.

Key Features:
- Environment-based service discovery
- Health checking with circuit breakers
- Fallback strategies for service failures
- Support for external service registries (Consul, etcd)
- Automatic service URL construction
- Configuration-driven service mapping

Usage:
    registry = ServiceRegistry()
    redis_url = registry.get_service_url("redis")
    ai_endpoint = registry.get_service_url("ai-stack", "/api/process")
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp
import yaml

# Import unified configuration system - NO HARDCODED VALUES
from config import ConfigManager

# Create singleton config instance
config = ConfigManager()
from autobot_shared.http_client import get_http_client


class ServiceStatus(Enum):
    """Service health status"""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    CIRCUIT_OPEN = "circuit_open"


class DeploymentMode(Enum):
    """Deployment mode detection"""

    LOCAL = "local"  # Single machine, no containers
    DOCKER_LOCAL = "docker_local"  # Docker Compose on single machine
    DISTRIBUTED = "distributed"  # Services across multiple machines
    KUBERNETES = "kubernetes"  # Kubernetes deployment
    CLOUD = "cloud"  # Cloud-managed services


@dataclass
class ServiceConfig:
    """Service configuration with health checking"""

    name: str
    host: str
    port: int
    scheme: str = "http"
    path: str = ""
    health_endpoint: str = "/health"
    timeout: int = None  # Will use config
    retries: int = None  # Will use config
    circuit_breaker_threshold: int = None  # Will use config
    circuit_breaker_timeout: int = None  # Will use config


@dataclass
class ServiceHealth:
    """Service health state"""

    status: ServiceStatus
    last_check: float
    failure_count: int = 0
    circuit_open_until: float = 0
    response_time: float = 0


class ServiceRegistry:
    """
    Centralized service discovery and configuration management.

    Handles multiple deployment scenarios:
    1. Local development (localhost)
    2. Docker Compose (container names)
    3. Distributed deployment (external hosts)
    4. Cloud deployment (managed services)
    """

    # Issue #380: Cache service configs to avoid repeated dict creation/config lookups
    _cached_default_services: Optional[Dict] = None
    _cached_host_patterns: Optional[Dict] = None

    # Service configurations from unified config - NO HARDCODED VALUES
    @classmethod
    def get_default_services(cls):
        """Get service configurations from unified config (cached)"""
        if cls._cached_default_services is not None:
            return cls._cached_default_services
        cls._cached_default_services = {
            "redis": {
                "port": config.get_port("redis"),
                "health_endpoint": "/",
                "schemes": {
                    "local": "redis",
                    "docker": "redis",
                    "distributed": "redis",
                },
            },
            "ai-stack": {
                "port": config.get_port("ai_stack"),
                "health_endpoint": "/health",
                "schemes": {"local": "http", "docker": "http", "distributed": "http"},
            },
            "npu-worker": {
                "port": config.get_port("npu_worker"),
                "health_endpoint": "/health",
                "schemes": {"local": "http", "docker": "http", "distributed": "http"},
            },
            "backend": {
                "port": config.get_port("backend"),
                "health_endpoint": "/api/health",  # Fixed endpoint
                "schemes": {"local": "http", "docker": "http", "distributed": "http"},
            },
            "frontend": {
                "port": config.get_port("frontend"),
                "health_endpoint": "/",
                "schemes": {"local": "http", "docker": "http", "distributed": "http"},
            },
            "playwright-vnc": {
                "port": config.get_port("browser_service"),
                "health_endpoint": "/health",
                "schemes": {"local": "http", "docker": "http", "distributed": "http"},
            },
            "ollama": {
                "port": config.get_port("ollama"),
                "health_endpoint": "/api/tags",
                "schemes": {"local": "http", "docker": "http", "distributed": "http"},
            },
        }
        return cls._cached_default_services

    # Host resolution patterns from unified config - NO HARDCODED VALUES
    @classmethod
    def get_host_patterns(cls):
        """Get host patterns from unified config (cached)"""
        if cls._cached_host_patterns is not None:
            return cls._cached_host_patterns
        cls._cached_host_patterns = {
            DeploymentMode.LOCAL: {
                # DEFAULT HYBRID: Backend/frontend on localhost, Docker services on localhost ports
                "default": config.get("infrastructure.defaults.localhost"),
                "redis": config.get_host("redis"),
                "backend": config.get_host("backend"),
                "frontend": config.get_host("frontend"),
                "ai-stack": config.get_host("ai_stack"),
                "npu-worker": config.get_host("npu_worker"),
                "playwright-vnc": config.get_host("browser_service"),
                "ollama": config.get_host("ollama"),  # Use configured host for Ollama
                "lmstudio": config.get_host(
                    "lmstudio"
                ),  # Use configured host for LM Studio
            },
            DeploymentMode.DOCKER_LOCAL: {
                "default": "autobot-{service}",
                "redis": "autobot-redis",
                "ai-stack": "autobot-ai-stack",
                "npu-worker": "autobot-npu-worker",
            },
            DeploymentMode.DISTRIBUTED: {
                "default": "{service}.{domain}",
                "redis": "redis.autobot.local",
                "ai-stack": "ai-stack.autobot.local",
                "npu-worker": "npu-worker.autobot.local",
            },
        }
        return cls._cached_host_patterns

    def __init__(self, config_file: Optional[str] = None):
        """Initialize service registry with optional configuration file"""
        self.logger = logging.getLogger(__name__)
        self.services: Dict[str, ServiceConfig] = {}
        self.health_status: Dict[str, ServiceHealth] = {}
        self.deployment_mode = self._detect_deployment_mode()
        self.domain = config.get("deployment.domain", "autobot.local")

        # Load configuration from unified config
        self._load_default_services()
        if config_file:
            self._load_config_file(config_file)
        self._load_environment_config()

        self.logger.info(
            f"Service registry initialized in {self.deployment_mode.value} mode"
        )

    def _detect_deployment_mode(self) -> DeploymentMode:
        """Detect current deployment mode"""
        # Check for explicit mode setting
        mode = config.get("deployment.mode", "").lower()
        if mode:
            try:
                return DeploymentMode(mode)
            except ValueError:
                self.logger.warning("Invalid deployment mode: %s", mode)

        # Auto-detect based on environment
        # DEFAULT BEHAVIOR: Local + Docker hybrid (backend on host, services in containers)
        if os.path.exists("/.dockerenv"):
            # Running inside container
            if config.get("deployment.kubernetes.service_host", False):
                return DeploymentMode.KUBERNETES
            elif config.get("deployment.distributed", False):
                return DeploymentMode.DISTRIBUTED
            else:
                return DeploymentMode.DOCKER_LOCAL
        else:
            # Running on host - DEFAULT: Local with Docker services
            if config.get("deployment.mode") == "distributed":
                return DeploymentMode.DISTRIBUTED
            else:
                # Default hybrid mode: backend/frontend on localhost, services in Docker
                return DeploymentMode.LOCAL

    def _load_default_services(self):
        """Load default service configurations from unified config"""
        for service_name, svc_def in self.get_default_services().items():
            host = self._resolve_host(service_name)

            service_config = ServiceConfig(
                name=service_name,
                host=host,
                port=svc_def["port"],
                health_endpoint=svc_def["health_endpoint"],
                scheme=svc_def["schemes"].get(
                    self.deployment_mode.value.split("_")[0], "http"
                ),
                timeout=config.get_timeout("service_registry", "default"),
                retries=config.get("service_registry.retries", 3),
                circuit_breaker_threshold=config.get(
                    "circuit_breaker.service_registry.failure_threshold", 5
                ),
                circuit_breaker_timeout=config.get_timeout(
                    "circuit_breaker", "recovery"
                ),
            )

            self.services[service_name] = service_config
            self.health_status[service_name] = ServiceHealth(
                status=ServiceStatus.UNKNOWN, last_check=0
            )

    def _resolve_host(self, service_name: str) -> str:
        """Resolve hostname based on deployment mode and service"""
        # PRIORITY 1: Check deployment mode patterns first (for LOCAL mode overrides)
        patterns = self.get_host_patterns().get(self.deployment_mode, {})

        # For LOCAL mode, always use the localhost patterns for Ollama and LMStudio
        if self.deployment_mode == DeploymentMode.LOCAL and service_name in patterns:
            pattern = patterns[service_name]
            return pattern.format(service=service_name, domain=self.domain)

        # PRIORITY 2: Check for explicit host configuration
        service_key = service_name.replace("-", "_")
        explicit_host = config.get(f"services.{service_key}.host")
        if explicit_host:
            return explicit_host

        # PRIORITY 3: Use deployment mode patterns from unified config
        if service_name in patterns:
            pattern = patterns[service_name]
        else:
            pattern = patterns.get(
                "default", config.get("infrastructure.defaults.localhost")
            )

        # Replace placeholders
        return pattern.format(service=service_name, domain=self.domain)

    def _load_config_file(self, config_file: str):
        """Load services from configuration file"""
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)

            services_config = config.get("services", {})
            for service_name, service_data in services_config.items():
                if service_name in self.services:
                    # Update existing service
                    service = self.services[service_name]
                    service.host = service_data.get("host", service.host)
                    service.port = service_data.get("port", service.port)
                    service.scheme = service_data.get("scheme", service.scheme)
                    service.health_endpoint = service_data.get(
                        "health_endpoint", service.health_endpoint
                    )
                else:
                    # Add new service
                    self.services[service_name] = ServiceConfig(
                        name=service_name,
                        host=service_data.get(
                            "host", config.get("infrastructure.defaults.localhost")
                        ),
                        port=service_data.get(
                            "port", config.get("infrastructure.ports.default", 80)
                        ),
                        scheme=service_data.get(
                            "scheme", config.get("deployment.default_scheme", "http")
                        ),
                        health_endpoint=service_data.get(
                            "health_endpoint",
                            config.get("deployment.default_health_endpoint", "/health"),
                        ),
                    )

        except Exception as e:
            self.logger.error("Failed to load config file %s: %s", config_file, e)

    def _load_environment_config(self):
        """Load service configurations from environment variables"""
        for service_name in self.services:
            service = self.services[service_name]

            # Update from environment variables
            # Load service-specific overrides from config
            service_key = service_name.replace("-", "_")

            # CRITICAL: Respect LOCAL mode patterns for localhost services
            # Don't override Ollama/LMStudio hosts in LOCAL mode
            if self.deployment_mode == DeploymentMode.LOCAL and service_name in (
                "ollama",
                "lmstudio",
            ):
                # Keep the LOCAL mode host pattern, don't override with explicit config
                pass
            else:
                service.host = config.get(f"services.{service_key}.host", service.host)
            service.port = config.get(f"services.{service_key}.port", service.port)
            service.scheme = config.get(
                f"services.{service_key}.scheme", service.scheme
            )
            service.path = config.get(f"services.{service_key}.path", service.path)
            service.health_endpoint = config.get(
                f"services.{service_key}.health_endpoint", service.health_endpoint
            )

    def get_service_url(self, service_name: str, path: str = "") -> str:
        """
        Get full URL for a service

        Args:
            service_name: Name of the service
            path: Optional path to append

        Returns:
            Full service URL

        Example:
            registry.get_service_url("redis")
            registry.get_service_url("ai-stack", "/api/process")
        """
        if service_name not in self.services:
            self.logger.error("Unknown service: %s", service_name)
            raise ValueError(f"Service '{service_name}' not found in registry")

        service = self.services[service_name]

        # Construct URL
        base_url = f"{service.scheme}://{service.host}:{service.port}"

        # Add service path and requested path
        full_path = f"{service.path.rstrip('/')}{path}" if path else service.path
        if full_path and not full_path.startswith("/"):
            full_path = f"/{full_path}"

        return f"{base_url}{full_path}"

    def get_service_config(self, service_name: str) -> Optional[ServiceConfig]:
        """Get service configuration"""
        return self.services.get(service_name)

    def list_services(self) -> List[str]:
        """List all registered services"""
        return list(self.services.keys())

    def register_service(self, service_config: ServiceConfig):
        """Register a new service"""
        self.services[service_config.name] = service_config
        self.health_status[service_config.name] = ServiceHealth(
            status=ServiceStatus.UNKNOWN, last_check=0
        )
        self.logger.info("Registered service: %s", service_config.name)

    async def check_service_health(self, service_name: str) -> ServiceHealth:
        """Check health of a specific service"""
        if service_name not in self.services:
            raise ValueError(f"Service '{service_name}' not found")

        service = self.services[service_name]
        health = self.health_status[service_name]

        # Check if circuit breaker is open
        current_time = time.time()
        if health.circuit_open_until > current_time:
            health.status = ServiceStatus.CIRCUIT_OPEN
            return health

        try:
            health_url = self.get_service_url(service_name, service.health_endpoint)

            start_time = time.time()
            timeout = aiohttp.ClientTimeout(total=service.timeout)

            # Use singleton HTTP client for connection pooling
            http_client = get_http_client()
            async with await http_client.get(health_url, timeout=timeout) as response:
                health.response_time = time.time() - start_time

                if response.status == 200:
                    health.status = ServiceStatus.HEALTHY
                    health.failure_count = 0
                else:
                    health.status = ServiceStatus.UNHEALTHY
                    health.failure_count += 1

        except Exception as e:
            self.logger.warning("Health check failed for %s: %s", service_name, e)
            health.status = ServiceStatus.UNHEALTHY
            health.failure_count += 1

        # Update circuit breaker
        if health.failure_count >= service.circuit_breaker_threshold:
            health.circuit_open_until = current_time + service.circuit_breaker_timeout
            health.status = ServiceStatus.CIRCUIT_OPEN
            self.logger.error("Circuit breaker opened for %s", service_name)

        health.last_check = current_time
        return health

    async def check_all_services_health(self) -> Dict[str, ServiceHealth]:
        """Check health of all registered services"""
        tasks = []
        for service_name in self.services:
            task = self.check_service_health(service_name)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        health_report = {}
        for i, service_name in enumerate(self.services):
            if isinstance(results[i], Exception):
                self.logger.error(
                    f"Health check error for {service_name}: {results[i]}"
                )
                health_report[service_name] = ServiceHealth(
                    status=ServiceStatus.UNHEALTHY, last_check=time.time()
                )
            else:
                health_report[service_name] = results[i]

        return health_report

    def get_service_health(self, service_name: str) -> ServiceHealth:
        """Get cached health status for a service"""
        return self.health_status.get(
            service_name, ServiceHealth(status=ServiceStatus.UNKNOWN, last_check=0)
        )

    def is_service_healthy(self, service_name: str, max_age: int = 60) -> bool:
        """Check if service is healthy (with cache age limit)"""
        health = self.get_service_health(service_name)

        # Check if health data is too old
        if time.time() - health.last_check > max_age:
            return False

        return health.status == ServiceStatus.HEALTHY

    def get_deployment_info(self) -> Dict[str, Any]:
        """Get deployment information"""
        return {
            "deployment_mode": self.deployment_mode.value,
            "domain": self.domain,
            "services_count": len(self.services),
            "services": {
                name: {
                    "url": self.get_service_url(name),
                    "health": self.get_service_health(name).status.value,
                }
                for name in self.services
            },
        }


# Global service registry instance (thread-safe)
import threading

_registry: Optional[ServiceRegistry] = None
_registry_lock = threading.Lock()


def get_service_registry(config_file: Optional[str] = None) -> ServiceRegistry:
    """Get global service registry instance (singleton, thread-safe)"""
    global _registry
    if _registry is None:
        with _registry_lock:
            # Double-check after acquiring lock
            if _registry is None:
                _registry = ServiceRegistry(config_file)
    return _registry


def get_service_url(service_name: str, path: str = "") -> str:
    """Convenience function to get service URL"""
    registry = get_service_registry()
    return registry.get_service_url(service_name, path)


# Legacy compatibility functions
def get_redis_url() -> str:
    """Get Redis connection URL"""
    return get_service_url("redis")


def get_ai_stack_url(path: str = "") -> str:
    """Get AI stack URL"""
    return get_service_url("ai-stack", path)


def get_npu_worker_url(path: str = "") -> str:
    """Get NPU worker URL"""
    return get_service_url("npu-worker", path)
