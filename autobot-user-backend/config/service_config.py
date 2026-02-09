#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service, host, port, and URL configuration management.
"""

import logging
import os
from typing import Any, Dict

from constants.network_constants import NetworkConstants
from constants.path_constants import PATH

logger = logging.getLogger(__name__)

# Issue #380: Module-level cached maps to avoid repeated dictionary creation
_HOST_SERVICE_MAP = {
    "slm": NetworkConstants.SLM_VM_IP,
    "backend": NetworkConstants.MAIN_MACHINE_IP,
    "redis": NetworkConstants.REDIS_VM_IP,
    "frontend": NetworkConstants.FRONTEND_VM_IP,
    "npu_worker": NetworkConstants.NPU_WORKER_VM_IP,
    "ai_stack": NetworkConstants.AI_STACK_VM_IP,
    "browser": NetworkConstants.BROWSER_VM_IP,
    "ollama": NetworkConstants.AI_STACK_HOST,
    "browser_service": NetworkConstants.BROWSER_VM_IP,
    "openai": "api.openai.com",
    "anthropic": "api.anthropic.com",
    "vllm": "localhost",
    "lmstudio": "localhost",
}

_PORT_SERVICE_MAP = {
    "slm": NetworkConstants.SLM_PORT,
    "backend": NetworkConstants.BACKEND_PORT,
    "redis": NetworkConstants.REDIS_PORT,
    "frontend": NetworkConstants.FRONTEND_PORT,
    "npu_worker": NetworkConstants.NPU_WORKER_PORT,
    "ai_stack": NetworkConstants.AI_STACK_PORT,
    "browser": NetworkConstants.BROWSER_SERVICE_PORT,
    "ollama": NetworkConstants.OLLAMA_PORT,
    "browser_service": NetworkConstants.BROWSER_SERVICE_PORT,
    "openai": 443,
    "anthropic": 443,
    "vllm": 8000,
    "lmstudio": 1234,
}


class ServiceConfigMixin:
    """Mixin providing service, host, port, and URL configuration"""

    def get_host(self, service: str) -> str:
        """
        Get host address for a service.

        Provides compatibility with config_helper.cfg.get_host()
        for config consolidation (Issue #63).

        Priority order:
        1. Environment variable AUTOBOT_{SERVICE}_HOST
        2. Config file infrastructure.hosts.{service}
        3. Hardcoded fallback map

        Args:
            service: Service name (e.g., 'backend', 'redis', 'frontend', 'ollama')

        Returns:
            Host address string
        """
        # 1. Try environment variable first (highest priority)
        env_key = f"AUTOBOT_{service.upper()}_HOST"
        env_host = os.getenv(env_key)
        if env_host:
            return env_host

        # 2. Try infrastructure.hosts from config file
        host = self.get_nested(f"infrastructure.hosts.{service}")
        if host:
            return host

        # 3. Fallback to module-level cached map (Issue #380)
        return _HOST_SERVICE_MAP.get(service, "localhost")

    def get_port(self, service: str) -> int:
        """
        Get port number for a service.

        Provides compatibility with config_helper.cfg.get_port()
        for config consolidation (Issue #63).

        Priority order:
        1. Environment variable AUTOBOT_{SERVICE}_PORT
        2. Config file infrastructure.ports.{service}
        3. Hardcoded fallback map

        Args:
            service: Service name (e.g., 'backend', 'redis', 'frontend', 'ollama')

        Returns:
            Port number
        """
        # 1. Try environment variable first (highest priority)
        env_key = f"AUTOBOT_{service.upper()}_PORT"
        env_port = os.getenv(env_key)
        if env_port:
            return int(env_port)

        # 2. Try infrastructure.ports from config file
        port = self.get_nested(f"infrastructure.ports.{service}")
        if port:
            return int(port)

        # 3. Fallback to module-level cached map (Issue #380)
        return _PORT_SERVICE_MAP.get(service, 8000)

    def get_service_url(self, service: str, endpoint: str = None) -> str:
        """
        Get full URL for a service with optional endpoint.

        Provides compatibility with config_helper.cfg.get_service_url()
        for config consolidation (Issue #63).

        Args:
            service: Service name (e.g., 'backend', 'redis', 'frontend')
            endpoint: Optional endpoint path to append

        Returns:
            Full service URL string
        """
        host = self.get_host(service)
        port = self.get_port(service)
        url = f"http://{host}:{port}"
        if endpoint:
            url = f"{url}/{endpoint.lstrip('/')}"
        return url

    def get_backend_config(self) -> Dict[str, Any]:
        """Get backend configuration with fallback defaults"""
        backend_config = self.get_nested("backend", {})

        defaults = {
            "server_host": NetworkConstants.BIND_ALL_INTERFACES,
            "server_port": int(
                os.getenv("AUTOBOT_BACKEND_PORT", str(NetworkConstants.BACKEND_PORT))
            ),
            "api_endpoint": (
                f"http://localhost:{os.getenv('AUTOBOT_BACKEND_PORT', str(NetworkConstants.BACKEND_PORT))}"
            ),
            "timeout": 60,
            "max_retries": 3,
            "streaming": False,
            "cors_origins": self.get_cors_origins(),
            "allowed_hosts": ["*"],
            "max_request_size": 10485760,  # 10MB
        }

        from config.loader import deep_merge

        return deep_merge(defaults, backend_config)

    def get_config_section(self, section: str) -> Dict[str, Any]:
        """Get configuration section with fallback defaults"""
        return self.get_nested(section, {})

    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration from SSOT config (single source of truth)."""
        from autobot_shared.ssot_config import config as ssot

        return {
            "enabled": ssot.redis.enabled,
            "host": ssot.vm.redis,
            "port": ssot.port.redis,
            "password": ssot.redis.password,
            "db": ssot.redis.db_main,
        }

    def get_ollama_url(self) -> str:
        """Get the Ollama service URL from configuration (backward compatibility)"""
        # First check environment variable
        env_url = os.getenv("AUTOBOT_OLLAMA_URL")
        if env_url:
            return env_url

        # Then check configuration
        endpoint = self.get_nested("backend.llm.local.providers.ollama.endpoint")
        if endpoint:
            return endpoint.replace("/api/generate", "")  # Get base URL

        host = self.get_nested("backend.llm.local.providers.ollama.host")
        if host:
            return host

        # Finally fall back to configured host (Issue #63 consolidation)
        ollama_host = self.get_host("ollama")
        ollama_port = self.get_port("ollama")
        if ollama_host and ollama_port:
            return f"http://{ollama_host}:{ollama_port}"
        return (
            f"http://{NetworkConstants.LOCALHOST_NAME}:{NetworkConstants.OLLAMA_PORT}"
        )

    def get_redis_url(self) -> str:
        """Get the Redis service URL from configuration (backward compatibility)"""
        env_url = os.getenv("AUTOBOT_REDIS_URL")
        if env_url:
            return env_url

        host = self.get_nested("memory.redis.host", NetworkConstants.LOCALHOST_IP)
        port = self.get_nested("memory.redis.port", NetworkConstants.REDIS_PORT)
        return f"redis://{host}:{port}"

    def get_distributed_services_config(self) -> Dict[str, Any]:
        """Get distributed services configuration from NetworkConstants"""
        return {
            "frontend": {
                "host": str(NetworkConstants.FRONTEND_VM_IP),
                "port": NetworkConstants.FRONTEND_PORT,
            },
            "npu_worker": {
                "host": str(NetworkConstants.NPU_WORKER_VM_IP),
                "port": NetworkConstants.NPU_WORKER_PORT,
            },
            "redis": {
                "host": str(NetworkConstants.REDIS_VM_IP),
                "port": NetworkConstants.REDIS_PORT,
            },
            "ai_stack": {
                "host": str(NetworkConstants.AI_STACK_VM_IP),
                "port": NetworkConstants.AI_STACK_PORT,
            },
            "browser": {
                "host": str(NetworkConstants.BROWSER_VM_IP),
                "port": NetworkConstants.BROWSER_SERVICE_PORT,
            },
        }

    def get_cors_origins(self) -> list:
        """Generate CORS origins from ALL infrastructure machines (#815).

        Iterates every VM in ``NetworkConstants.get_host_configs()`` so
        that adding a new machine automatically allows CORS from it.
        ``security.cors_origins`` in the config file still overrides.
        """
        explicit_origins = self.get_nested("security.cors_origins", [])
        if explicit_origins:
            return explicit_origins

        origins: set[str] = set()

        # Localhost variants for development
        dev_ports = {
            NetworkConstants.FRONTEND_PORT,
            NetworkConstants.BACKEND_PORT,
            NetworkConstants.BROWSER_SERVICE_PORT,
        }
        for port in dev_ports:
            origins.add(f"http://{NetworkConstants.LOCALHOST_NAME}:{port}")
            origins.add(f"http://{NetworkConstants.LOCALHOST_IP}:{port}")

        # Every AutoBot VM with its primary service port
        for host in NetworkConstants.get_host_configs():
            origins.add(f"http://{host['ip']}:{host['port']}")

        return sorted(origins)

    def get_path(self, category: str, name: str = None) -> str:
        """
        Get filesystem path from configuration.

        Provides compatibility with config_helper.cfg.get_path()
        for config consolidation (Issue #63).

        Args:
            category: Path category (e.g., 'logs', 'data', 'config')
            name: Optional specific path name within category

        Returns:
            Filesystem path string
        """
        if name:
            path = self.get_nested(f"paths.{category}.{name}")
        else:
            path = self.get_nested(f"paths.{category}")

        if path:
            return str(path)

        # Fallback defaults using centralized PathConstants (Issue #380)
        defaults = {
            "logs": str(PATH.LOGS_DIR),
            "data": str(PATH.DATA_DIR),
            "config": str(PATH.CONFIG_DIR),
            "reports": str(PATH.REPORTS_DIR),
        }
        return defaults.get(category, str(PATH.PROJECT_ROOT))

    def get_api_key(self, provider: str) -> str:
        """Get API key for a cloud LLM provider (#536).

        Priority: env AUTOBOT_{PROVIDER}_API_KEY > config > empty string.
        """
        env_val = os.getenv(f"AUTOBOT_{provider.upper()}_API_KEY")
        if env_val:
            return env_val
        return self.get_nested(f"backend.llm.cloud.providers.{provider}.api_key", "")

    def get_active_provider(self) -> str:
        """Get the currently active LLM provider (#536).

        Priority: env AUTOBOT_LLM_PROVIDER > config > 'ollama'.
        """
        env_provider = os.getenv("AUTOBOT_LLM_PROVIDER")
        if env_provider:
            return env_provider
        return self.get_nested("backend.llm.active_provider", "ollama")
