#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Network Constants for AutoBot
=============================

Centralized network configuration constants.

MIGRATION (Issue #763):
    All values now use ConfigRegistry with five-tier fallback:
    Cache → Redis → Environment → Registry Defaults → Caller Default

Usage:
    from constants.network_constants import NetworkConstants, ServiceURLs

    # A Redis URL comes from the one endpoint resolver (#19232), never from these constants:
    #   autobot_shared.redis_management.endpoint.resolve_redis_endpoint().url(db)

    # Use service URLs
    backend_url = ServiceURLs.BACKEND_API

    # Preferred: Use ConfigRegistry directly
    from config.registry import ConfigRegistry
    redis_ip = ConfigRegistry.get("vm.redis", "")
"""

import os
import warnings
from functools import cached_property

from autobot_shared import deployment_profile as _profile


def _get_config_value(key: str, default: str | None) -> str:
    """Get configuration value with lazy ConfigRegistry import.

    ConfigRegistry lives in autobot-backend. This function imports it only
    when needed, avoiding dependency issues when autobot_shared is used
    independently (e.g., in autobot-slm-backend or CI tooling).

    Issue #7526: Explicit import from autobot_shared pattern, not bare 'config'.
    A ``None`` default is the SSOT value at *key* itself, never a restated literal (#19325).
    """
    if default is None:
        from autobot_shared.ssot_value import ssot_value

        default = ssot_value(key)
    try:
        from config.registry import ConfigRegistry

        return ConfigRegistry.get(key, default)
    except (ImportError, ModuleNotFoundError):
        return default


# Deprecation flag - set to True to enable deprecation warnings
_SHOW_DEPRECATION_WARNINGS = (
    os.getenv("AUTOBOT_SHOW_DEPRECATION_WARNINGS", "").lower() == "true"
)  # ssot-config-exempt: module-level init


def _emit_deprecation_warning(old_pattern: str, new_pattern: str) -> None:
    """
    Emit a deprecation warning if enabled.

    Issue #763: Helps identify code that should migrate to ConfigRegistry.
    Enable with: AUTOBOT_SHOW_DEPRECATION_WARNINGS=true
    """
    if _SHOW_DEPRECATION_WARNINGS:
        warnings.warn(
            f"ConfigRegistry Migration: '{old_pattern}' is deprecated. " f"Use '{new_pattern}' instead. (Issue #763)",
            DeprecationWarning,
            stacklevel=3,
        )


# #12773: these were resolved eagerly in the class body, so importing this module
# performed ~25 ConfigRegistry lookups — which dial Redis, through a
# network_constants -> config.registry -> redis_client import cycle. Two
# consequences outlived that connection storm: values were frozen for the process
# lifetime (defeating the ConfigRegistry TTL, so an SSOT/SLM change never reached
# a running process), and import order decided which values a process saw.
#
# Resolving on access costs one lookup per use, and ConfigRegistry has its own
# cache and TTL — which is where that caching belongs.
# name -> (config key, default, type); a port's default is None -- its SSOT value (#19325)
_LAZY_CONFIG_VALUES: dict = {
    "MAIN_MACHINE_IP": ("vm.main", "", str),
    "FRONTEND_VM_IP": ("vm.frontend", "", str),
    "NPU_WORKER_VM_IP": ("vm.npu", "", str),
    "REDIS_VM_IP": ("vm.redis", "", str),
    "AI_STACK_VM_IP": ("vm.aistack", "", str),
    "BROWSER_VM_IP": ("vm.browser", "", str),
    "SLM_VM_IP": ("vm.slm", "", str),
    "AI_STACK_HOST": ("vm.aistack", "", str),
    "BACKEND_PORT": ("port.backend", None, int),
    "FRONTEND_PORT": ("port.frontend", None, int),
    "REDIS_PORT": ("port.redis", None, int),
    "OLLAMA_PORT": ("port.ollama", None, int),
    "VNC_PORT": ("port.vnc", None, int),
    "BROWSER_SERVICE_PORT": ("port.browser", None, int),
    "AI_STACK_PORT": ("port.aistack", None, int),
    "NPU_WORKER_PORT": ("port.npu", None, int),
    "SLM_PORT": ("port.slm", None, int),
    "NPU_WORKER_WINDOWS_PORT": ("port.npu_windows", None, int),
    "DESKTOP_DISPLAY": ("desktop.display", ":1", str),
    "PROMETHEUS_PORT": ("port.prometheus", None, int),
    "GRAFANA_PORT": ("port.grafana", None, int),
    "DEV_FRONTEND_PORT": ("port.frontend", None, int),
    "DEV_BACKEND_PORT": ("port.backend", None, int),
}


class _LazyConfigMeta(type):
    """Resolves the ConfigRegistry-backed constants on access, not at import.

    A metaclass ``__getattr__`` fires only when normal class lookup fails, which
    is why the class body carries annotations without values — assigning them
    would shadow this and restore the eager behaviour.
    """

    def __getattr__(cls, name: str):
        spec = _LAZY_CONFIG_VALUES.get(name)
        if spec is None:
            raise AttributeError(f"type object '{cls.__name__}' has no attribute '{name}'")
        key, default, caster = spec
        return caster(_get_config_value(key, default))

    def __dir__(cls):
        return sorted(set(super().__dir__()) | set(_LAZY_CONFIG_VALUES))


class NetworkConstants(metaclass=_LazyConfigMeta):
    """
    Core network constants for AutoBot distributed infrastructure.

    SSOT Migration (Issue #763):
        All values now use ConfigRegistry with five-tier fallback.

    Usage remains unchanged for backward compatibility:
        from constants.network_constants import NetworkConstants
        host = NetworkConstants.MAIN_MACHINE_IP
    """

    # === VM Infrastructure IPs (from ConfigRegistry) ===

    # Main machine (WSL)
    MAIN_MACHINE_IP: str

    # VM Infrastructure IPs
    FRONTEND_VM_IP: str
    NPU_WORKER_VM_IP: str
    REDIS_VM_IP: str
    AI_STACK_VM_IP: str
    BROWSER_VM_IP: str
    SLM_VM_IP: str

    # Backward compatibility aliases
    AI_STACK_HOST: str

    # === Local/Localhost addresses (static - not from SSOT) ===
    LOCALHOST_IP: str = "127.0.0.1"
    LOCALHOST_IPV6: str = "::1"  # IPv6 loopback address
    LOCALHOST_NAME: str = "localhost"
    BIND_ALL_INTERFACES: str = "0.0.0.0"  # nosec B104  # intentional for servers

    # === Loopback/Local IP sets for O(1) membership checks (#625) ===
    # Use these frozensets instead of inline lists for `in` checks
    # nosec B104  # These contain intentional bind-all-interfaces for loopback checking
    LOOPBACK_IPS: frozenset = frozenset({"127.0.0.1", "localhost", "0.0.0.0", "::1"})  # nosec B104
    LOOPBACK_IPS_V4: frozenset = frozenset({"127.0.0.1", "localhost", "0.0.0.0"})  # nosec B104

    # === Network prefixes for IP validation (static) ===
    # All RFC 1918 private IP prefixes — deployment-agnostic
    PRIVATE_IP_PREFIXES: tuple = (
        "10.",
        *[f"172.{n}." for n in range(16, 32)],
        "192.168.",
        "127.",
    )
    DEFAULT_SCAN_NETWORK: str = ""  # Set via NETWORK_SUBNET env var at deploy time
    PUBLIC_DNS_IP: str = "8.8.8.8"  # Google Public DNS for connectivity testing

    # === Special purpose IPs (static) ===
    DUMMY_ROUTE_IP: str = "10.255.255.255"  # Dummy IP for local IP detection via socket routing
    TEST_HOST_IP: str = "10.0.0.99"  # Test host IP for unit tests (not a real VM)

    # === Standard ports (from ConfigRegistry) ===
    BACKEND_PORT: int
    FRONTEND_PORT: int
    REDIS_PORT: int
    OLLAMA_PORT: int
    VNC_PORT: int
    BROWSER_SERVICE_PORT: int
    AI_STACK_PORT: int
    NPU_WORKER_PORT: int
    SLM_PORT: int
    NPU_WORKER_WINDOWS_PORT: int
    CHROME_DEBUGGER_PORT: int = 9222  # Chrome DevTools Protocol port (static)

    # Issue #11579: Canonical desktop-control display. SINGLE source of truth
    # shared by gui_controller.py (pyautogui) and api/vnc_manager.py + api/
    # vnc_mcp.py (xdotool/x11vnc). Both stacks MUST act on this same X
    # display so the human observer (noVNC) always sees what the agent does.
    # Override via env var AUTOBOT_DESKTOP_DISPLAY (ConfigRegistry convention).
    # #11506 T1 (control-lock) will arbitrate simultaneous agent/human access
    # to this shared display — not implemented here.
    DESKTOP_DISPLAY: str

    # Issue #474: Monitoring stack ports (from ConfigRegistry)
    PROMETHEUS_PORT: int
    ALERTMANAGER_PORT: int = 9093  # Not in ConfigRegistry currently
    GRAFANA_PORT: int

    # Development ports (aliases)
    DEV_FRONTEND_PORT: int
    DEV_BACKEND_PORT: int

    # === External service URLs (static) ===
    GOOGLE_SEARCH_BASE_URL: str = "https://www.google.com/search"

    # === Docker user/group IDs (static) ===
    DEFAULT_UID: str = "1000"
    DEFAULT_GID: str = "1000"
    DEFAULT_USER_GROUP: str = "1000:1000"

    # === Issue #372: Feature Envy Reduction Methods ===

    @classmethod
    def get_host_configs(cls) -> list:
        """Get list of host configurations for all AutoBot VMs.

        Returns all infrastructure machines so that features like CORS
        can iterate the full fleet without cherry-picking.
        (Issue #372 - reduces feature envy, Issue #815 - dynamic CORS)
        """
        return [
            {
                "id": "slm",
                "name": "SLM Server",
                "ip": cls.SLM_VM_IP,
                "port": cls.SLM_PORT,
                "description": "System Lifecycle Manager",
            },
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
        """Get WebSocket URL for frontend (Issue #372).

        Delegates to ``AutoBotConfig.websocket_url`` (#18731), the one
        implementation of the TLS-aware URL (#6303/#6302).
        """
        from autobot_shared.ssot_config import config  # lazy to avoid circular import

        return config.websocket_url


# #12773: these URLs were composed in the class body from NetworkConstants
# values, so importing this module resolved every one of them — which is how the
# import-time ConfigRegistry lookups survived making NetworkConstants itself
# lazy. Each entry is now built on access, from whatever the constants resolve
# to at that moment, so an SSOT change reaches a running process.
_LAZY_SERVICE_URLS: dict = {
    "BACKEND_API": lambda: f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}",
    "BACKEND_LOCAL": lambda: f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.BACKEND_PORT}",
    "FRONTEND_VM": _profile.served_frontend_url,
    "FRONTEND_LOCAL": lambda: _profile.served_frontend_url(NetworkConstants.LOCALHOST_NAME),
    "OLLAMA_LOCAL": lambda: f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.OLLAMA_PORT}",
    "VNC_DESKTOP": lambda: f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.VNC_PORT}/vnc.html",
    "CHROME_DEBUGGER_LOCAL": lambda: (
        f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.CHROME_DEBUGGER_PORT}"
    ),
    "VNC_LOCAL": lambda: f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.VNC_PORT}/vnc.html",
    "BROWSER_SERVICE": lambda: f"http://{NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT}",
    "AI_STACK_SERVICE": lambda: f"http://{NetworkConstants.AI_STACK_VM_IP}:{NetworkConstants.AI_STACK_PORT}",
    "NPU_WORKER_SERVICE": lambda: f"http://{NetworkConstants.NPU_WORKER_VM_IP}:{NetworkConstants.NPU_WORKER_PORT}",
    "NPU_WORKER_WINDOWS_SERVICE": lambda: (
        f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.NPU_WORKER_WINDOWS_PORT}"
    ),
    "PROMETHEUS_API": lambda: f"http://{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.PROMETHEUS_PORT}",
    "ALERTMANAGER_API": lambda: f"http://{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.ALERTMANAGER_PORT}",
    "GRAFANA_URL": lambda: f"http://{NetworkConstants.REDIS_VM_IP}:{NetworkConstants.GRAFANA_PORT}",
}


class _LazyURLMeta(type):
    """Builds a service URL on attribute access rather than at import."""

    def __getattr__(cls, name: str):
        builder = _LAZY_SERVICE_URLS.get(name)
        if builder is None:
            raise AttributeError(f"type object '{cls.__name__}' has no attribute '{name}'")
        return builder()

    def __dir__(cls):
        return sorted(set(super().__dir__()) | set(_LAZY_SERVICE_URLS))


class ServiceURLs(metaclass=_LazyURLMeta):
    """
    Pre-built service URLs for common AutoBot services.

    SSOT Migration (Issue #763):
        URLs are now computed from ConfigRegistry values.
        For direct access, use:
            from config.registry import ConfigRegistry
            backend = f"http://{ConfigRegistry.get('vm.main', '...')}:..."
    """

    # Backend API URLs (computed from ConfigRegistry)
    BACKEND_API: str

    BACKEND_LOCAL: str

    # Frontend URLs (computed from ConfigRegistry)
    FRONTEND_VM: str

    FRONTEND_LOCAL: str

    # No Redis URLs here: endpoint.resolve_redis_endpoint is the one builder (#19232).

    # Ollama LLM URLs (computed from ConfigRegistry)
    # Ollama runs on the local host (.20); OLLAMA_MAIN pointed to .24 (wrong).
    OLLAMA_LOCAL: str

    # VNC Desktop URLs (computed from ConfigRegistry)
    VNC_DESKTOP: str

    # Chrome DevTools Protocol URLs (static)
    CHROME_DEBUGGER_LOCAL: str
    VNC_LOCAL: str

    # Browser automation service (computed from ConfigRegistry)
    BROWSER_SERVICE: str

    # AI Stack service (computed from ConfigRegistry)
    AI_STACK_SERVICE: str

    # NPU Worker services (computed from ConfigRegistry)
    NPU_WORKER_SERVICE: str

    NPU_WORKER_WINDOWS_SERVICE: str

    # Issue #474: Monitoring stack services (hosted on Redis VM)
    PROMETHEUS_API: str

    ALERTMANAGER_API: str

    GRAFANA_URL: str


class NetworkConfig:
    """
    Dynamic network configuration based on environment.
    Provides context-aware URL generation.

    SSOT Migration (Issue #763):
        The mode comes from the one resolver (#19316, #19372):
            from autobot_shared import service_registry_core
            mode = service_registry_core.resolve_deployment_mode().value
    """

    def __init__(self) -> None:
        """Initialize network config using ConfigRegistry values."""
        from autobot_shared.service_registry_core import resolve_deployment_mode  # lazy (ssot_config); #19316

        self._deployment_mode = resolve_deployment_mode().value
        self._is_development = _get_config_value("deployment.environment", _profile.environment_name()) == "development"

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
        """The Redis URL without credentials, from the one endpoint resolver (#19232)."""
        from autobot_shared.redis_management.endpoint import resolve_redis_endpoint

        return resolve_redis_endpoint().url(with_auth=False)

    @property
    def ollama_url(self) -> str:
        """Get Ollama URL based on deployment context"""
        return ServiceURLs.OLLAMA_LOCAL

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

    def get_service_url(self, service_name: str) -> str | None:
        """
        Get service URL by name.

        Issue #763: Prefer using ConfigRegistry directly:
            from config.registry import ConfigRegistry
            host = ConfigRegistry.get("vm.redis", "")

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
            "slm": NetworkConstants.SLM_VM_IP,
            "main": NetworkConstants.MAIN_MACHINE_IP,
            "frontend": NetworkConstants.FRONTEND_VM_IP,
            "npu_worker": NetworkConstants.NPU_WORKER_VM_IP,
            "redis": NetworkConstants.REDIS_VM_IP,
            "ai_stack": NetworkConstants.AI_STACK_VM_IP,
            "browser": NetworkConstants.BROWSER_VM_IP,
        }

    def get_vm_ip(self, vm_name: str) -> str | None:
        """
        Get VM IP address by name.

        Issue #763: Prefer using ConfigRegistry directly:
            from config.registry import ConfigRegistry
            ip = ConfigRegistry.get("vm.redis", "")

        Args:
            vm_name: Name of the VM (frontend, redis, ai_stack, etc.)

        Returns:
            IP address or None if not found
        """
        return self._vm_map.get(vm_name)


# #12773: instantiating this at import resolved deployment.mode/environment and
# built every VM URL, which is where the last 9 import-time ConfigRegistry
# lookups came from after the constants themselves were made lazy. Built on
# first use instead; get_network_config() is the accessor callers already use.
_network_config: "NetworkConfig | None" = None


def get_network_config() -> NetworkConfig:
    """Get the global network configuration instance, building it on first use."""
    global _network_config
    if _network_config is None:
        _network_config = NetworkConfig()
    return _network_config


#: ``DatabaseConstants`` attribute -> the database it names. Names only (#19232): the
#: numbers come from the one table, read on access because importing it here would cycle.
_DB_TARGETS: tuple[str, ...] = ("main", "knowledge", "prompts", "agents", "metrics", "cache", "sessions", "logs")
_DB_TARGETS += ("temp", "audit", "analytics", "testing", "celery_broker", "celery_results")
_DATABASE_CONSTANT_NAMES = {f"{n.upper()}_DB": n for n in _DB_TARGETS} | {"TASKS_DB": "workflows", "BACKUP_DB": "audit"}


class _DatabaseConstantsMeta(type):
    """Resolves ``DatabaseConstants.MAIN_DB`` etc. through ``database_number`` on access."""

    def __getattr__(cls, name: str) -> int:
        target = _DATABASE_CONSTANT_NAMES.get(name)
        if target is None:
            raise AttributeError(name)
        from autobot_shared.redis_management.database_names import database_number

        return database_number(target)


class DatabaseConstants(metaclass=_DatabaseConstantsMeta):
    """Redis database numbers by constant name, read from the one table (#2670, #19232).

    Formerly a literal mirror of redis-databases.yaml that ``AUTOBOT_REDIS_DB_*``
    overrides could not move.
    """

    @classmethod
    def get_db_description(cls, db_number: int) -> str:
        """Get description for database number."""
        descriptions = {
            cls.MAIN_DB: "Main application data",
            cls.KNOWLEDGE_DB: "Knowledge base and documents",
            cls.PROMPTS_DB: "Prompt templates and configurations",
            cls.AGENTS_DB: "Agent state and definitions",
            cls.METRICS_DB: "Performance metrics",
            cls.CACHE_DB: "Application cache",
            cls.SESSIONS_DB: "User sessions",
            cls.TASKS_DB: "Workflow state and execution",
            cls.LOGS_DB: "Log data and history",
            cls.TEMP_DB: "Temporary data",
            cls.AUDIT_DB: "Security audit logging",
            cls.ANALYTICS_DB: "Codebase analytics",
            cls.CELERY_BROKER_DB: "Celery task broker",
            cls.CELERY_RESULTS_DB: "Celery task results backend",
            cls.TESTING_DB: "Test isolation database",
        }
        return descriptions.get(db_number, f"Database {db_number}")


# Legacy compatibility - keep these for backward compatibility during refactoring.
# #12773: resolved via module __getattr__ (PEP 562) rather than assigned here.
# Assigning them re-read every underlying constant at import — the last source of
# import-time ConfigRegistry lookups once the classes themselves were made lazy —
# and re-froze the values these aliases hand out.
_LEGACY_ALIASES: dict = {
    "BACKEND_URL": lambda: ServiceURLs.BACKEND_API,
    "FRONTEND_URL": lambda: ServiceURLs.FRONTEND_VM,
    "REDIS_HOST": lambda: NetworkConstants.REDIS_VM_IP,
    "REDIS_VM_IP": lambda: NetworkConstants.REDIS_VM_IP,
    "MAIN_MACHINE_IP": lambda: NetworkConstants.MAIN_MACHINE_IP,
    "LOCALHOST_IP": lambda: NetworkConstants.LOCALHOST_IP,
}


def __getattr__(name: str):
    """Resolve the legacy module-level aliases on access (#12773)."""
    builder = _LEGACY_ALIASES.get(name)
    if builder is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return builder()


def __dir__():
    return sorted(set(globals()) | set(_LEGACY_ALIASES))
