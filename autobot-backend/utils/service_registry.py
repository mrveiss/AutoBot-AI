# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import aiohttp
import yaml

from autobot_shared.config_file_loading import load_config_file
from autobot_shared.http_client import get_http_client
from autobot_shared.service_registry_core import (
    SERVICE_DEFINITIONS,
    DeploymentMode,
    ServiceHealth,
    build_base_url,
    detect_deployment_mode,
    join_service_path,
    parse_deployment_mode,
)

# Import unified configuration system - NO HARDCODED VALUES
from config.manager import get_config_manager

config = get_config_manager()
from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import HealthStatus
from constants.api_constants import PATH_HEALTH

# Alias of the canonical enum (#12771): same members, same identity.
RegistryServiceStatus = HealthStatus


@dataclass
class ServiceConfig:
    """Service configuration with health checking"""

    name: str
    host: str
    port: int
    scheme: str = "http"
    path: str = ""
    health_endpoint: str = PATH_HEALTH
    timeout: int = None  # Will use config
    retries: int = None  # Will use config
    circuit_breaker_threshold: int = None  # Will use config
    circuit_breaker_timeout: int = None  # Will use config


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
    _cached_default_services: Dict | None = None
    _cached_host_patterns: Dict | None = None

    # Service configurations from unified config - NO HARDCODED VALUES
    @classmethod
    def get_default_services(cls):
        """Get service configurations from unified config (cached)"""
        if cls._cached_default_services is not None:
            return cls._cached_default_services
        cls._cached_default_services = {
            name: {
                "port": d.port,
                "health_endpoint": d.health_path,
                "schemes": {"local": d.scheme, "docker": d.scheme, "distributed": d.scheme},
            }
            for name, d in SERVICE_DEFINITIONS.items()
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
                **{name: d.host for name, d in SERVICE_DEFINITIONS.items()},
                "lmstudio": "localhost",
            },
            DeploymentMode.DOCKER_LOCAL: {
                "default": "autobot-{service}",
                "redis": "autobot-redis",
                "ai-stack": "autobot-ai-stack",
                "npu-worker": "autobot-npu-worker",
            },
            DeploymentMode.DISTRIBUTED: {
                "default": "{service}.{domain}",
                "redis": "redis.{domain}",
                "ai-stack": "ai-stack.{domain}",
                "npu-worker": "npu-worker.{domain}",
            },
        }
        return cls._cached_host_patterns

    def __init__(self, config_file: str | None = None):
        """Initialize service registry with optional configuration file"""
        self.logger = get_logger(__name__)
        self.services: Dict[str, ServiceConfig] = {}
        self.health_status: Dict[str, ServiceHealth] = {}
        self.deployment_mode = self._detect_deployment_mode()
        self.domain = config.get("deployment.domain", "autobot.local")

        # Load configuration from unified config
        self._load_default_services()
        if config_file:
            self._load_config_file(config_file)
        self._load_environment_config()
        self._pin_redis_to_endpoint()

        self.logger.info(f"Service registry initialized in {self.deployment_mode.value} mode")

    def _detect_deployment_mode(self) -> DeploymentMode:
        """Detect current deployment mode"""
        explicit = parse_deployment_mode(config.get("deployment.mode", "").lower(), self.logger, "deployment.mode")
        return detect_deployment_mode(
            explicit,
            in_container=os.path.exists("/.dockerenv"),
            kubernetes=bool(config.get("deployment.kubernetes.service_host", False)),
            distributed=bool(config.get("deployment.distributed", False)),
        )

    def _load_default_services(self):
        """Load default service configurations from unified config"""
        for service_name, svc_def in self.get_default_services().items():
            host = self._resolve_host(service_name)

            service_config = ServiceConfig(
                name=service_name,
                host=host,
                port=svc_def["port"],
                health_endpoint=svc_def["health_endpoint"],
                scheme=svc_def["schemes"].get(self.deployment_mode.value.split("_")[0], "http"),
                timeout=config.get_timeout("service_registry", "default"),
                retries=config.get("service_registry.retries", 3),
                circuit_breaker_threshold=config.get("circuit_breaker.service_registry.failure_threshold", 5),
                circuit_breaker_timeout=config.get_timeout("circuit_breaker", "recovery"),
            )

            self.services[service_name] = service_config
            self.health_status[service_name] = ServiceHealth(status=RegistryServiceStatus.UNKNOWN, last_check=0)

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
            pattern = patterns.get("default", config.get("infrastructure.defaults.localhost"))

        # Replace placeholders
        return pattern.format(service=service_name, domain=self.domain)

    def _load_config_file(self, config_file: str):
        """Load services from configuration file"""
        try:
            parser = yaml.safe_load if config_file.endswith((".yaml", ".yml")) else json.load
            config = load_config_file(config_file, dict, "Service registry", parser=parser).values

            services_config = config.get("services", {})
            for service_name, service_data in services_config.items():
                if service_name in self.services:
                    # Update existing service
                    service = self.services[service_name]
                    service.host = service_data.get("host", service.host)
                    service.port = service_data.get("port", service.port)
                    service.scheme = service_data.get("scheme", service.scheme)
                    service.health_endpoint = service_data.get("health_endpoint", service.health_endpoint)
                else:
                    # Add new service
                    self.services[service_name] = ServiceConfig(
                        name=service_name,
                        host=service_data.get("host", config.get("infrastructure.defaults.localhost")),
                        port=service_data.get("port", config.get("infrastructure.ports.default", 80)),
                        scheme=service_data.get("scheme", config.get("deployment.default_scheme", "http")),
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
            service.scheme = config.get(f"services.{service_key}.scheme", service.scheme)
            service.path = config.get(f"services.{service_key}.path", service.path)
            service.health_endpoint = config.get(f"services.{service_key}.health_endpoint", service.health_endpoint)

    def _pin_redis_to_endpoint(self) -> None:
        """Report Redis where the canonical client dials it (#19232).

        Redis has ONE resolution path, ``endpoint.resolve_redis_endpoint``; the
        deployment-mode patterns and config overrides above would be a second.
        """
        from autobot_shared.redis_management.endpoint import resolve_redis_endpoint

        redis_service = self.services.get("redis")
        if redis_service is None:
            return
        resolved = resolve_redis_endpoint()
        redis_service.host, redis_service.port = resolved.host, resolved.port
        redis_service.scheme = "rediss" if resolved.tls else "redis"

    def get_service_url(self, service_name: str, path: str = "") -> str:
        """
        Get full URL for a service

        Args:
            service_name: Name of the service
            path: Optional path to append

        Returns:
            Full service URL

        Raises:
            ValueError: the service is not registered. A miss never falls back
                to a default host (#18639); the SSOT lookup
                ``autobot_shared.ssot_config`` ``get_service_url`` returns None
                instead. Neither guesses an endpoint.

        Example:
            registry.get_service_url("redis")
            registry.get_service_url("ai-stack", "/api/process")
        """
        if service_name not in self.services:
            self.logger.error("Unknown service: %s", service_name)
            raise ValueError(f"Service '{service_name}' not found in registry")

        service = self.services[service_name]

        base_url = build_base_url(service.scheme, service.host, service.port)
        return join_service_path(base_url, service.path, path)

    def get_service_config(self, service_name: str) -> ServiceConfig | None:
        """Get service configuration"""
        return self.services.get(service_name)

    def list_services(self) -> List[str]:
        """List all registered services"""
        return list(self.services.keys())

    def register_service(self, service_config: ServiceConfig):
        """Register a new service"""
        self.services[service_config.name] = service_config
        self.health_status[service_config.name] = ServiceHealth(status=RegistryServiceStatus.UNKNOWN, last_check=0)
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
            health.status = RegistryServiceStatus.CIRCUIT_OPEN
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
                    health.status = RegistryServiceStatus.HEALTHY
                    health.failure_count = 0
                else:
                    health.status = RegistryServiceStatus.UNHEALTHY
                    health.failure_count += 1

        except Exception as e:
            self.logger.warning("Health check failed for %s: %s", service_name, e)
            health.status = RegistryServiceStatus.UNHEALTHY
            health.failure_count += 1

        # Update circuit breaker
        if health.failure_count >= service.circuit_breaker_threshold:
            health.circuit_open_until = current_time + service.circuit_breaker_timeout
            health.status = RegistryServiceStatus.CIRCUIT_OPEN
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
                self.logger.error(f"Health check error for {service_name}: {results[i]}")
                health_report[service_name] = ServiceHealth(
                    status=RegistryServiceStatus.UNHEALTHY, last_check=time.time()
                )
            else:
                health_report[service_name] = results[i]

        return health_report

    def get_service_health(self, service_name: str) -> ServiceHealth:
        """Get cached health status for a service"""
        return self.health_status.get(service_name, ServiceHealth(status=RegistryServiceStatus.UNKNOWN, last_check=0))

    def is_service_healthy(self, service_name: str, max_age: int = 60) -> bool:
        """Check if service is healthy (with cache age limit)"""
        health = self.get_service_health(service_name)

        # Check if health data is too old
        if time.time() - health.last_check > max_age:
            return False

        return health.status == RegistryServiceStatus.HEALTHY

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

_registry: ServiceRegistry | None = None
_registry_lock = threading.Lock()


def get_service_registry(config_file: str | None = None) -> ServiceRegistry:
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
def get_ai_stack_url(path: str = "") -> str:
    """Get AI stack URL"""
    return get_service_url("ai-stack", path)


def get_npu_worker_url(path: str = "") -> str:
    """Get NPU worker URL"""
    return get_service_url("npu-worker", path)
