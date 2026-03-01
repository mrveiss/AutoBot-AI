#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backward compatibility wrappers and legacy class support.

SSOT Migration (Issue #639):
    Constants now source from SSOT config when available,
    with fallback to NetworkConstants for backward compatibility.
"""

from typing import Any, Dict

from config.registry import ConfigRegistry
from constants.network_constants import NetworkConstants


class Config:
    """Backward compatibility wrapper for legacy code"""

    def __init__(self, manager):
        """Initialize compatibility wrapper with config manager."""
        self._manager = manager

    @property
    def config(self) -> Dict[str, Any]:
        """Return full configuration as dictionary."""
        return self._manager.to_dict()

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key with optional default."""
        return self._manager.get(key, default)


# Convenience functions for common operations
def get_config(manager, key: str, default: Any = None) -> Any:
    """Get configuration value"""
    return manager.get(key, default)


def get_config_section(manager, section: str) -> Dict[str, Any]:
    """Get configuration section"""
    return manager.get_nested(section, {})


def get_llm_config(manager) -> Dict[str, Any]:
    """Get LLM configuration"""
    return manager.get_llm_config()


def get_redis_config(manager) -> Dict[str, Any]:
    """Get Redis configuration"""
    return manager.get_redis_config()


def reload_config(manager) -> None:
    """Reload configuration from files"""
    manager.reload()


def validate_config(manager) -> Dict[str, Any]:
    """Validate configuration and return status"""
    return manager.validate_config()


# ASYNC CONVENIENCE FUNCTIONS


async def get_config_manager_async(manager):
    """Get async config manager instance"""
    return manager


async def load_config_async(manager, config_type: str = "main") -> Dict[str, Any]:
    """Load configuration asynchronously"""
    return await manager.load_config_async(config_type)


async def save_config_async(manager, config_type: str, data: Dict[str, Any]) -> None:
    """Save configuration asynchronously"""
    await manager.save_config_async(config_type, data)


async def get_config_value_async(
    manager, config_type: str, key: str, default: Any = None
) -> Any:
    """Get configuration value asynchronously"""
    return await manager.get_config_value_async(config_type, key, default)


async def set_config_value_async(
    manager, config_type: str, key: str, value: Any
) -> None:
    """Set configuration value asynchronously"""
    await manager.set_config_value_async(config_type, key, value)


# Export host and service constants for backward compatibility
# Issue #763: Now uses ConfigRegistry with fallback to NetworkConstants
# Issue #1214: Ollama fallback corrected — was AI_STACK_HOST (.24), now 127.0.0.1
HTTP_PROTOCOL = "http"
OLLAMA_HOST_IP = ConfigRegistry.get("vm.ollama", "127.0.0.1")
OLLAMA_PORT = int(ConfigRegistry.get("port.ollama", str(NetworkConstants.OLLAMA_PORT)))
REDIS_HOST_IP = ConfigRegistry.get("vm.redis", NetworkConstants.REDIS_VM_IP)
OLLAMA_URL = f"http://{OLLAMA_HOST_IP}:{OLLAMA_PORT}"

# Backend/API service constants
BACKEND_HOST_IP = ConfigRegistry.get("vm.main", NetworkConstants.MAIN_MACHINE_IP)
BACKEND_PORT = int(
    ConfigRegistry.get("port.backend", str(NetworkConstants.BACKEND_PORT))
)
API_BASE_URL = f"http://{BACKEND_HOST_IP}:{BACKEND_PORT}"

# Playwright/Browser service constants
PLAYWRIGHT_HOST_IP = ConfigRegistry.get("vm.browser", NetworkConstants.BROWSER_VM_IP)
PLAYWRIGHT_VNC_PORT = int(
    ConfigRegistry.get("port.vnc", str(NetworkConstants.VNC_PORT))
)
PLAYWRIGHT_VNC_URL = f"http://{PLAYWRIGHT_HOST_IP}:{PLAYWRIGHT_VNC_PORT}/vnc.html"


# VNC Direct URL function
def get_vnc_direct_url():
    """Get the direct VNC connection URL with appropriate port"""
    return f"http://{PLAYWRIGHT_HOST_IP}:{PLAYWRIGHT_VNC_PORT}/vnc.html"
