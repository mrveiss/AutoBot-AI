#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Network Constants for AutoBot
=============================

Centralized network configuration constants. This module now reads from
the SSOT (Single Source of Truth) configuration system while maintaining
full backward compatibility with existing code.

MIGRATION (Issue #602):
    All values are now sourced from src/config/ssot_config.py which reads
    from the .env file. Hardcoded fallbacks are only used if .env is missing.

Usage:
    from src.constants.network_constants import NetworkConstants, ServiceURLs

    # Use VM IP addresses (now reads from SSOT)
    redis_url = f"redis://{NetworkConstants.REDIS_VM_IP}:6379"

    # Use service URLs (now reads from SSOT)
    backend_url = ServiceURLs.BACKEND_API

    # Preferred: Use SSOT directly
    from src.config.ssot_config import config
    redis_url = config.redis_url
"""

import os
import warnings
from functools import cached_property
from typing import Optional


def _get_ssot_config():
    """
    Get SSOT config with graceful fallback.

    Returns the SSOT config instance. If SSOT fails to load (e.g., during
    early imports or missing dependencies), returns None and callers should
    use hardcoded fallbacks.

    Issue #602: Import is inside function to prevent circular imports.
    The chain src.config.__init__ -> manager -> loader -> defaults -> network_constants
    would cause a circular import if we imported at module level.
    """
    try:
        # Import inside function to avoid circular import
        from src.config.ssot_config import get_config

        return get_config()
    except Exception:
        # During early initialization or if .env is missing, SSOT may fail
        # In that case, we use hardcoded fallbacks below
        return None


# Get config once at module load time for efficiency
_ssot = _get_ssot_config()

# Deprecation flag - set to True to enable deprecation warnings
# This helps during migration to identify code still using old patterns
_SHOW_DEPRECATION_WARNINGS = os.getenv("AUTOBOT_SHOW_DEPRECATION_WARNINGS", "").lower() == "true"


def _emit_deprecation_warning(old_pattern: str, new_pattern: str) -> None:
    """
    Emit a deprecation warning if enabled.

    Issue #602: Helps identify code that should migrate to SSOT.
    Enable with: AUTOBOT_SHOW_DEPRECATION_WARNINGS=true
    """
    if _SHOW_DEPRECATION_WARNINGS:
        warnings.warn(
            f"SSOT Migration: '{old_pattern}' is deprecated. "
            f"Use '{new_pattern}' instead. (Issue #602)",
            DeprecationWarning,
            stacklevel=3
        )


class NetworkConstants:
    """
    Core network constants for AutoBot distributed infrastructure.

    SSOT Migration (Issue #602):
        All values now read from SSOT config (.env file) with hardcoded
        fallbacks only used if .env is missing or malformed.

    Usage remains unchanged for backward compatibility:
        from src.constants.network_constants import NetworkConstants
        host = NetworkConstants.MAIN_MACHINE_IP
    """

    # === VM Infrastructure IPs (from SSOT) ===

    # Main machine (WSL)
    MAIN_MACHINE_IP: str = _ssot.vm.main if _ssot else "172.16.168.20"

    # VM Infrastructure IPs
    FRONTEND_VM_IP: str = _ssot.vm.frontend if _ssot else "172.16.168.21"
    NPU_WORKER_VM_IP: str = _ssot.vm.npu if _ssot else "172.16.168.22"
    REDIS_VM_IP: str = _ssot.vm.redis if _ssot else "172.16.168.23"
    AI_STACK_VM_IP: str = _ssot.vm.aistack if _ssot else "172.16.168.24"
    BROWSER_VM_IP: str = _ssot.vm.browser if _ssot else "172.16.168.25"

    # Backward compatibility aliases
    AI_STACK_HOST: str = _ssot.vm.aistack if _ssot else "172.16.168.24"

    # === Local/Localhost addresses (static - not from SSOT) ===
    LOCALHOST_IP: str = "127.0.0.1"
    LOCALHOST_IPV6: str = "::1"  # IPv6 loopback address
    LOCALHOST_NAME: str = "localhost"
    BIND_ALL_INTERFACES: str = "0.0.0.0"  # Bind server to all network interfaces

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

    # === Standard ports (from SSOT) ===
    BACKEND_PORT: int = _ssot.port.backend if _ssot else 8001
    FRONTEND_PORT: int = _ssot.port.frontend if _ssot else 5173
    REDIS_PORT: int = _ssot.port.redis if _ssot else 6379
    OLLAMA_PORT: int = _ssot.port.ollama if _ssot else 11434
    VNC_PORT: int = _ssot.port.vnc if _ssot else 6080
    BROWSER_SERVICE_PORT: int = _ssot.port.browser if _ssot else 3000
    AI_STACK_PORT: int = _ssot.port.aistack if _ssot else 8080
    NPU_WORKER_PORT: int = _ssot.port.npu if _ssot else 8081
    NPU_WORKER_WINDOWS_PORT: int = 8082  # Windows NPU worker (static)
    CHROME_DEBUGGER_PORT: int = 9222  # Chrome DevTools Protocol port (static)

    # Issue #474: Monitoring stack ports (from SSOT)
    PROMETHEUS_PORT: int = _ssot.port.prometheus if _ssot else 9090
    ALERTMANAGER_PORT: int = 9093  # Not in SSOT currently
    GRAFANA_PORT: int = _ssot.port.grafana if _ssot else 3000

    # Development ports (aliases)
    DEV_FRONTEND_PORT: int = _ssot.port.frontend if _ssot else 5173
    DEV_BACKEND_PORT: int = _ssot.port.backend if _ssot else 8001

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

    SSOT Migration (Issue #602):
        URLs are now computed from SSOT config values. For direct SSOT access,
        use the computed properties in AutoBotConfig:
            from src.config.ssot_config import config
            backend = config.backend_url
            redis = config.redis_url
    """

    # Backend API URLs (from SSOT)
    BACKEND_API: str = _ssot.backend_url if _ssot else (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"
    )
    BACKEND_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.BACKEND_PORT}"
    )

    # Frontend URLs (from SSOT)
    FRONTEND_VM: str = _ssot.frontend_url if _ssot else (
        f"http://{NetworkConstants.FRONTEND_VM_IP}:{NetworkConstants.FRONTEND_PORT}"
    )
    FRONTEND_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.FRONTEND_PORT}"
    )

    # Redis URLs (from SSOT)
    REDIS_VM: str = _ssot.redis_url if _ssot else (
        f"redis://{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.REDIS_PORT}"
    )
    REDIS_LOCAL: str = (
        f"redis://{NetworkConstants.LOCALHOST_IP}:{NetworkConstants.REDIS_PORT}"
    )

    # Ollama LLM URLs (from SSOT)
    OLLAMA_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.OLLAMA_PORT}"
    )
    OLLAMA_MAIN: str = _ssot.ollama_url if _ssot else (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.OLLAMA_PORT}"
    )

    # VNC Desktop URLs (from SSOT)
    VNC_DESKTOP: str = _ssot.vnc_url if _ssot else (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.VNC_PORT}/vnc.html"
    )

    # Chrome DevTools Protocol URLs (static)
    CHROME_DEBUGGER_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.CHROME_DEBUGGER_PORT}"
    )
    VNC_LOCAL: str = (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.VNC_PORT}/vnc.html"
    )

    # Browser automation service (from SSOT)
    BROWSER_SERVICE: str = _ssot.browser_service_url if _ssot else (
        f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}"
    )

    # AI Stack service (from SSOT)
    AI_STACK_SERVICE: str = _ssot.aistack_url if _ssot else (
        f"http://{NetworkConstants.AI_STACK_VM_IP}:{NetworkConstants.AI_STACK_PORT}"
    )

    # NPU Worker services (from SSOT)
    NPU_WORKER_SERVICE: str = _ssot.npu_worker_url if _ssot else (
        f"http://{NetworkConstants.NPU_WORKER_VM_IP}:{NetworkConstants.NPU_WORKER_PORT}"
    )
    NPU_WORKER_WINDOWS_SERVICE: str = (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.NPU_WORKER_WINDOWS_PORT}"
    )

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

    SSOT Migration (Issue #602):
        This class now delegates to SSOT config for most values.
        For direct access, prefer using SSOT directly:
            from src.config.ssot_config import config
            url = config.get_service_url("backend")
    """

    def __init__(self):
        """Initialize network config using SSOT values."""
        self._ssot = _ssot
        # Read from SSOT if available, otherwise from environment
        if self._ssot:
            self._deployment_mode = self._ssot.deployment_mode
            self._is_development = self._ssot.environment == "development"
        else:
            self._deployment_mode = os.getenv("AUTOBOT_DEPLOYMENT_MODE", "distributed")
            self._is_development = os.getenv("AUTOBOT_ENV", "production") == "development"

    @property
    def backend_url(self) -> str:
        """Get backend URL based on deployment context"""
        if self._ssot:
            if self._deployment_mode == "local":
                return ServiceURLs.BACKEND_LOCAL
            return self._ssot.backend_url
        if self._deployment_mode == "local":
            return ServiceURLs.BACKEND_LOCAL
        return ServiceURLs.BACKEND_API

    @property
    def frontend_url(self) -> str:
        """Get frontend URL based on deployment context"""
        if self._ssot:
            if self._deployment_mode == "local":
                return ServiceURLs.FRONTEND_LOCAL
            return self._ssot.frontend_url
        if self._deployment_mode == "local":
            return ServiceURLs.FRONTEND_LOCAL
        return ServiceURLs.FRONTEND_VM

    @property
    def redis_url(self) -> str:
        """Get Redis URL based on deployment context"""
        if self._ssot:
            if self._deployment_mode == "local":
                return ServiceURLs.REDIS_LOCAL
            return self._ssot.redis_url
        if self._deployment_mode == "local":
            return ServiceURLs.REDIS_LOCAL
        return ServiceURLs.REDIS_VM

    @property
    def ollama_url(self) -> str:
        """Get Ollama URL based on deployment context"""
        if self._ssot:
            return self._ssot.ollama_url
        return ServiceURLs.OLLAMA_LOCAL  # Always local for now

    @cached_property
    def _service_map(self) -> dict:
        """Issue #380: Cache service map to avoid repeated dict creation."""
        if self._ssot:
            return {
                "backend": self.backend_url,
                "frontend": self.frontend_url,
                "redis": self.redis_url,
                "ollama": self.ollama_url,
                "browser": self._ssot.browser_service_url,
                "ai_stack": self._ssot.aistack_url,
                "npu_worker": self._ssot.npu_worker_url,
                "vnc": self._ssot.vnc_url,
            }
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

        SSOT Migration (Issue #602):
            Prefer using SSOT directly:
                from src.config.ssot_config import config
                url = config.get_service_url("backend")

        Args:
            service_name: Name of the service (backend, frontend, redis, etc.)

        Returns:
            Service URL or None if not found
        """
        # Delegate to SSOT if available
        if self._ssot:
            url = self._ssot.get_service_url(service_name)
            if url:
                return url
        return self._service_map.get(service_name)

    @cached_property
    def _vm_map(self) -> dict:
        """Issue #380: Cache VM map to avoid repeated dict creation."""
        if self._ssot:
            return {
                "main": self._ssot.vm.main,
                "frontend": self._ssot.vm.frontend,
                "npu_worker": self._ssot.vm.npu,
                "redis": self._ssot.vm.redis,
                "ai_stack": self._ssot.vm.aistack,
                "browser": self._ssot.vm.browser,
            }
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

        SSOT Migration (Issue #602):
            Prefer using SSOT directly:
                from src.config.ssot_config import config
                ip = config.get_vm_ip("redis")

        Args:
            vm_name: Name of the VM (frontend, redis, ai_stack, etc.)

        Returns:
            IP address or None if not found
        """
        # Delegate to SSOT if available
        if self._ssot:
            ip = self._ssot.get_vm_ip(vm_name)
            if ip:
                return ip
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
