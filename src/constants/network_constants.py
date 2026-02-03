#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Network Constants for AutoBot
=============================

Centralized network configuration constants.

MIGRATION (Issue #763):
    All values now use registry_defaults with environment variable override.
    Fallback chain: Environment → Registry Defaults → Hardcoded Default

Usage:
    from src.constants.network_constants import NetworkConstants, ServiceURLs

    # Use VM IP addresses
    redis_url = f"redis://{NetworkConstants.REDIS_VM_IP}:6379"

    # Use service URLs
    backend_url = ServiceURLs.BACKEND_API

    # Preferred: Use ConfigRegistry directly (after module load)
    from src.config.registry import ConfigRegistry
    redis_ip = _get_config("vm.redis", "172.16.168.23")
"""

import os
import warnings
from functools import cached_property
from typing import Optional

# Inline registry defaults to avoid importing from src.config package (circular import)
# These values match src/config/registry_defaults.py
_REGISTRY_DEFAULTS = {
    "vm.main": "172.16.168.20",
    "vm.frontend": "172.16.168.21",
    "vm.npu": "172.16.168.22",
    "vm.redis": "172.16.168.23",
    "vm.aistack": "172.16.168.24",
    "vm.browser": "172.16.168.25",
    "vm.ollama": "127.0.0.1",
    "port.backend": "8001",
    "port.frontend": "5173",
    "port.redis": "6379",
    "port.ollama": "11434",
    "port.vnc": "6080",
    "port.browser": "3000",
    "port.aistack": "8080",
    "port.npu": "8081",
    "port.prometheus": "9090",
    "port.grafana": "3000",
    "deployment.mode": "distributed",
    "deployment.environment": "production",
}


def _get_config(key: str, default: str) -> str:
    """
    Get config value with fallback chain.

    Priority: Environment Variable → Registry Default → Hardcoded Default

    This avoids importing ConfigRegistry at module load time to prevent
    circular imports with src.config package.
    """
    # Try environment variable first (AUTOBOT_VM_REDIS format)
    env_key = f"AUTOBOT_{key.upper().replace('.', '_')}"
    env_value = os.getenv(env_key)
    if env_value is not None:
        return env_value

    # Try inline registry defaults
    registry_value = _REGISTRY_DEFAULTS.get(key)
    if registry_value is not None:
        return registry_value

    # Return hardcoded default
    return default


# Deprecation flag - set to True to enable deprecation warnings
_SHOW_DEPRECATION_WARNINGS = (
    os.getenv("AUTOBOT_SHOW_DEPRECATION_WARNINGS", "").lower() == "true"
)


def _emit_deprecation_warning(old_pattern: str, new_pattern: str) -> None:
    """
    Emit a deprecation warning if enabled.

    Issue #763: Helps identify code that should migrate to ConfigRegistry.
    Enable with: AUTOBOT_SHOW_DEPRECATION_WARNINGS=true
    """
    if _SHOW_DEPRECATION_WARNINGS:
        warnings.warn(
            f"ConfigRegistry Migration: '{old_pattern}' is deprecated. "
            f"Use '{new_pattern}' instead. (Issue #763)",
            DeprecationWarning,
            stacklevel=3,
        )


class NetworkConstants:
    """
    Core network constants for AutoBot distributed infrastructure.

    SSOT Migration (Issue #763):
        All values now use ConfigRegistry with five-tier fallback.

    Usage remains unchanged for backward compatibility:
        from src.constants.network_constants import NetworkConstants
        host = NetworkConstants.MAIN_MACHINE_IP
    """

    # === VM Infrastructure IPs (from ConfigRegistry) ===

    # Main machine (WSL)
    MAIN_MACHINE_IP: str = _get_config("vm.main", "172.16.168.20")

    # VM Infrastructure IPs
    FRONTEND_VM_IP: str = _get_config("vm.frontend", "172.16.168.21")
    NPU_WORKER_VM_IP: str = _get_config("vm.npu", "172.16.168.22")
    REDIS_VM_IP: str = _get_config("vm.redis", "172.16.168.23")
    AI_STACK_VM_IP: str = _get_config("vm.aistack", "172.16.168.24")
    BROWSER_VM_IP: str = _get_config("vm.browser", "172.16.168.25")

    # Backward compatibility aliases
    AI_STACK_HOST: str = _get_config("vm.aistack", "172.16.168.24")

    # === Local/Localhost addresses (static - not from SSOT) ===
    LOCALHOST_IP: str = "127.0.0.1"
    LOCALHOST_IPV6: str = "::1"  # IPv6 loopback address
    LOCALHOST_NAME: str = "localhost"
    BIND_ALL_INTERFACES: str = "0.0.0.0"  # nosec B104 - intentional for servers

    # === Loopback/Local IP sets for O(1) membership checks (#625) ===
    # Use these frozensets instead of inline lists for `in` checks
    # nosec B104 - These contain intentional bind-all-interfaces for loopback checking
    LOOPBACK_IPS: frozenset = frozenset(
        {"127.0.0.1", "localhost", "0.0.0.0", "::1"}  # nosec B104
    )
    LOOPBACK_IPS_V4: frozenset = frozenset(
        {"127.0.0.1", "localhost", "0.0.0.0"}  # nosec B104
    )

    # === Network prefixes for IP validation (static) ===
    VM_IP_PREFIX: str = "172.16.168."  # AutoBot VM network prefix
    DEFAULT_SCAN_NETWORK: str = (
        "192.168.1.0/24"  # Default network range for scanning tools
    )
    PUBLIC_DNS_IP: str = "8.8.8.8"  # Google Public DNS for connectivity testing

    # === Special purpose IPs (static) ===
    DUMMY_ROUTE_IP: str = (
        "10.255.255.255"  # Dummy IP for local IP detection via socket routing
    )
    TEST_HOST_IP: str = "172.16.168.99"  # Test host IP for unit tests (not a real VM)

    # === Standard ports (from ConfigRegistry) ===
    BACKEND_PORT: int = int(_get_config("port.backend", "8001"))
    FRONTEND_PORT: int = int(_get_config("port.frontend", "5173"))
    REDIS_PORT: int = int(_get_config("port.redis", "6379"))
    OLLAMA_PORT: int = int(_get_config("port.ollama", "11434"))
    VNC_PORT: int = int(_get_config("port.vnc", "6080"))
    BROWSER_SERVICE_PORT: int = int(_get_config("port.browser", "3000"))
    AI_STACK_PORT: int = int(_get_config("port.aistack", "8080"))
    NPU_WORKER_PORT: int = int(_get_config("port.npu", "8081"))
    NPU_WORKER_WINDOWS_PORT: int = 8082  # Windows NPU worker (static)
    CHROME_DEBUGGER_PORT: int = 9222  # Chrome DevTools Protocol port (static)

    # Issue #474: Monitoring stack ports (from ConfigRegistry)
    PROMETHEUS_PORT: int = int(_get_config("port.prometheus", "9090"))
    ALERTMANAGER_PORT: int = 9093  # Not in ConfigRegistry currently
    GRAFANA_PORT: int = int(_get_config("port.grafana", "3000"))

    # Development ports (aliases)
    DEV_FRONTEND_PORT: int = int(_get_config("port.frontend", "5173"))
    DEV_BACKEND_PORT: int = int(_get_config("port.backend", "8001"))

    # === External service URLs (static) ===
    GOOGLE_SEARCH_BASE_URL: str = "https://www.google.com/search"

    # === Docker user/group IDs (static) ===
    DEFAULT_UID: str = "1000"
    DEFAULT_GID: str = "1000"
    DEFAULT_USER_GROUP: str = "1000:1000"

    # === Issue #372: Feature Envy Reduction Methods ===

    @classmethod
    def get_host_configs(cls) -> list:
        """Get list of host configurations for frontend (Issue #372 - reduces feature envy)."""
        return [
            {
                "id": "main",
                "name": "Main (WSL Backend)",
                "ip": cls.MAIN_MACHINE_IP,
                "port": cls.BACKEND_PORT,
                "description": "Main backend server on WSL",
            },
            {
                "id": "frontend",
                "name": "VM1 (Frontend)",
                "ip": cls.FRONTEND_VM_IP,
                "port": cls.FRONTEND_PORT,
                "description": "Frontend web interface server",
            },
            {
                "id": "npu-worker",
                "name": "VM2 (NPU Worker)",
                "ip": cls.NPU_WORKER_VM_IP,
                "port": cls.NPU_WORKER_PORT,
                "description": "Hardware AI acceleration worker",
            },
            {
                "id": "redis",
                "name": "VM3 (Redis)",
                "ip": cls.REDIS_VM_IP,
                "port": cls.REDIS_PORT,
                "description": "Redis data layer server",
            },
            {
                "id": "ai-stack",
                "name": "VM4 (AI Stack)",
                "ip": cls.AI_STACK_VM_IP,
                "port": cls.AI_STACK_PORT,
                "description": "AI processing stack server",
            },
            {
                "id": "browser",
                "name": "VM5 (Browser)",
                "ip": cls.BROWSER_VM_IP,
                "port": cls.BROWSER_SERVICE_PORT,
                "description": "Browser automation server",
            },
        ]

    @classmethod
    def get_api_config(cls) -> dict:
        """Get API connection config for frontend (Issue #372 - reduces feature envy)."""
        return {
            "base_url": cls.MAIN_MACHINE_IP,
            "port": cls.BACKEND_PORT,
        }

    @classmethod
    def get_websocket_url(cls) -> str:
        """Get WebSocket URL for frontend (Issue #372 - reduces feature envy)."""
        return f"ws://{cls.MAIN_MACHINE_IP}:{cls.BACKEND_PORT}/ws"


class ServiceURLs:
    """
    Pre-built service URLs for common AutoBot services.

    SSOT Migration (Issue #763):
        URLs are now computed from ConfigRegistry values.
        For direct access, use:
            from src.config.registry import ConfigRegistry
            backend = f"http://{_get_config('vm.main', '...')}:..."
    """

    # Backend API URLs (computed from ConfigRegistry)
    BACKEND_API: str = (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
    )
    BACKEND_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.BACKEND_PORT}"
    )

    # Frontend URLs (computed from ConfigRegistry)
    FRONTEND_VM: str = (
        f"http://{NetworkConstants.FRONTEND_VM_IP}:{NetworkConstants.FRONTEND_PORT}"
    )
    FRONTEND_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.FRONTEND_PORT}"
    )

    # Redis URLs (computed from ConfigRegistry)
    REDIS_VM: str = (
        f"redis://{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.REDIS_PORT}"
    )
    REDIS_LOCAL: str = (
        f"redis://{NetworkConstants.LOCALHOST_IP}:{NetworkConstants.REDIS_PORT}"
    )

    # Ollama LLM URLs (computed from ConfigRegistry)
    OLLAMA_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.OLLAMA_PORT}"
    )
    OLLAMA_MAIN: str = (
        f"http://{NetworkConstants.AI_STACK_VM_IP}:{NetworkConstants.OLLAMA_PORT}"
    )

    # VNC Desktop URLs (computed from ConfigRegistry)
    # fmt: off
    VNC_DESKTOP: str = (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.VNC_PORT}/vnc.html"
    )
    # fmt: on

    # Chrome DevTools Protocol URLs (static)
    # fmt: off
    CHROME_DEBUGGER_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.CHROME_DEBUGGER_PORT}"
    )
    # fmt: on
    VNC_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.VNC_PORT}/vnc.html"
    )

    # Browser automation service (computed from ConfigRegistry)
    # fmt: off
    BROWSER_SERVICE: str = (
        f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}"
    )
    # fmt: on

    # AI Stack service (computed from ConfigRegistry)
    AI_STACK_SERVICE: str = (
        f"http://{NetworkConstants.AI_STACK_VM_IP}:{NetworkConstants.AI_STACK_PORT}"
    )

    # NPU Worker services (computed from ConfigRegistry)
    NPU_WORKER_SERVICE: str = (
        f"http://{NetworkConstants.NPU_WORKER_VM_IP}:{NetworkConstants.NPU_WORKER_PORT}"
    )
    # fmt: off
    NPU_WORKER_WINDOWS_SERVICE: str = (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.NPU_WORKER_WINDOWS_PORT}"
    )
    # fmt: on

    # Issue #474: Monitoring stack services (hosted on Redis VM)
    PROMETHEUS_API: str = (
        f"http://{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.PROMETHEUS_PORT}"
    )
    ALERTMANAGER_API: str = (
        f"http://{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.ALERTMANAGER_PORT}"
    )
    GRAFANA_URL: str = (
        f"http://{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.GRAFANA_PORT}"
    )


class NetworkConfig:
    """
    Dynamic network configuration based on environment.
    Provides context-aware URL generation.

    SSOT Migration (Issue #763):
        This class now uses ConfigRegistry for deployment mode.
        For direct access, prefer using ConfigRegistry:
            from src.config.registry import ConfigRegistry
            mode = _get_config("deployment.mode", "distributed")
    """

    def __init__(self):
        """Initialize network config using ConfigRegistry values."""
        self._deployment_mode = _get_config(
            "deployment.mode", os.getenv("AUTOBOT_DEPLOYMENT_MODE", "distributed")
        )
        self._is_development = (
            _get_config(
                "deployment.environment",
                os.getenv("AUTOBOT_ENV", "production"),
            )
            == "development"
        )

    @property
    def backend_url(self) -> str:
        """Get backend URL based on deployment context"""
        if self._deployment_mode == "local":
            return ServiceURLs.BACKEND_LOCAL
        return ServiceURLs.BACKEND_API

    @property
    def frontend_url(self) -> str:
        """Get frontend URL based on deployment context"""
        if self._deployment_mode == "local":
            return ServiceURLs.FRONTEND_LOCAL
        return ServiceURLs.FRONTEND_VM

    @property
    def redis_url(self) -> str:
        """Get Redis URL based on deployment context"""
        if self._deployment_mode == "local":
            return ServiceURLs.REDIS_LOCAL
        return ServiceURLs.REDIS_VM

    @property
    def ollama_url(self) -> str:
        """Get Ollama URL based on deployment context"""
        return ServiceURLs.OLLAMA_MAIN

    @cached_property
    def _service_map(self) -> dict:
        """Issue #380: Cache service map to avoid repeated dict creation."""
        return {
            "backend": self.backend_url,
            "frontend": self.frontend_url,
            "redis": self.redis_url,
            "ollama": self.ollama_url,
            "browser": ServiceURLs.BROWSER_SERVICE,
            "ai_stack": ServiceURLs.AI_STACK_SERVICE,
            "npu_worker": ServiceURLs.NPU_WORKER_SERVICE,
            "vnc": ServiceURLs.VNC_DESKTOP,
        }

    def get_service_url(self, service_name: str) -> Optional[str]:
        """
        Get service URL by name.

        Issue #763: Prefer using ConfigRegistry directly:
            from src.config.registry import ConfigRegistry
            host = _get_config("vm.redis", "172.16.168.23")

        Args:
            service_name: Name of the service (backend, frontend, redis, etc.)

        Returns:
            Service URL or None if not found
        """
        return self._service_map.get(service_name)

    @cached_property
    def _vm_map(self) -> dict:
        """Issue #380: Cache VM map to avoid repeated dict creation."""
        return {
            "main": NetworkConstants.MAIN_MACHINE_IP,
            "frontend": NetworkConstants.FRONTEND_VM_IP,
            "npu_worker": NetworkConstants.NPU_WORKER_VM_IP,
            "redis": NetworkConstants.REDIS_VM_IP,
            "ai_stack": NetworkConstants.AI_STACK_VM_IP,
            "browser": NetworkConstants.BROWSER_VM_IP,
        }

    def get_vm_ip(self, vm_name: str) -> Optional[str]:
        """
        Get VM IP address by name.

        Issue #763: Prefer using ConfigRegistry directly:
            from src.config.registry import ConfigRegistry
            ip = _get_config("vm.redis", "172.16.168.23")

        Args:
            vm_name: Name of the VM (frontend, redis, ai_stack, etc.)

        Returns:
            IP address or None if not found
        """
        return self._vm_map.get(vm_name)


# Global network configuration instance
_network_config = NetworkConfig()


def get_network_config() -> NetworkConfig:
    """Get the global network configuration instance"""
    return _network_config


class DatabaseConstants:
    """Redis database assignments to eliminate hardcoded database numbers"""

    # Core databases
    MAIN_DB = 0
    KNOWLEDGE_DB = 1
    CACHE_DB = 2
    VECTORS_DB = 8

    # Specialized databases
    SESSIONS_DB = 3
    METRICS_DB = 4
    LOGS_DB = 5
    CONFIG_DB = 6
    WORKFLOWS_DB = 7
    TEMP_DB = 9
    MONITORING_DB = 10
    RATE_LIMITING_DB = 11

    @classmethod
    def get_db_description(cls, db_number: int) -> str:
        """Get description for database number"""
        descriptions = {
            cls.MAIN_DB: "Main application data",
            cls.KNOWLEDGE_DB: "Knowledge base and documents",
            cls.CACHE_DB: "Application cache",
            cls.SESSIONS_DB: "User sessions",
            cls.METRICS_DB: "Performance metrics",
            cls.LOGS_DB: "Application logs",
            cls.CONFIG_DB: "Configuration data",
            cls.WORKFLOWS_DB: "Workflow definitions",
            cls.VECTORS_DB: "Vector embeddings",
            cls.TEMP_DB: "Temporary data",
            cls.MONITORING_DB: "System monitoring",
            cls.RATE_LIMITING_DB: "Rate limiting data",
        }
        return descriptions.get(db_number, f"Database {db_number}")


# Legacy compatibility - keep these for backward compatibility during refactoring
BACKEND_URL = ServiceURLs.BACKEND_API
FRONTEND_URL = ServiceURLs.FRONTEND_VM
REDIS_HOST = NetworkConstants.REDIS_VM_IP
REDIS_VM_IP = NetworkConstants.REDIS_VM_IP
MAIN_MACHINE_IP = NetworkConstants.MAIN_MACHINE_IP
LOCALHOST_IP = NetworkConstants.LOCALHOST_IP
