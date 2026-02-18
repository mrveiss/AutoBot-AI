#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Configuration Package

Modularized config system split from unified_config_manager.py (Issues #286, #290).

Architecture:
- settings.py: Pydantic settings model
- defaults.py: Default config generation
- loader.py: Config loading and merging
- sync_ops.py: Synchronous operations
- async_ops.py: Asynchronous operations
- model_config.py: LLM/model management
- service_config.py: Service/host/port configuration
- timeout_config.py: Timeout management
- file_watcher.py: File watching and callbacks
- validation.py: Config validation
- manager.py: Core manager class (composition of mixins)
- compat.py: Backward compatibility wrappers

Note: Uses lazy imports via __getattr__ to avoid circular import with NetworkConstants.
    Cycle: network_constants → ConfigRegistry → src.config.__init__ → manager → network_constants
"""

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# Type hints for IDE support without runtime import
if TYPE_CHECKING:
    from config.compat import (
        API_BASE_URL,
        BACKEND_HOST_IP,
        BACKEND_PORT,
        HTTP_PROTOCOL,
        OLLAMA_HOST_IP,
        OLLAMA_PORT,
        OLLAMA_URL,
        PLAYWRIGHT_HOST_IP,
        PLAYWRIGHT_VNC_PORT,
        PLAYWRIGHT_VNC_URL,
        REDIS_HOST_IP,
        Config,
        get_vnc_direct_url,
    )
    from config.manager import UnifiedConfigManager, get_unified_config_manager
    from config.settings import UnifiedConfigSettings

# Cache for lazily imported modules/objects
_lazy_cache: dict = {}


def _lazy_import_manager():
    """Lazily import the manager module."""
    if "manager" not in _lazy_cache:
        from config.manager import UnifiedConfigManager, get_unified_config_manager

        _lazy_cache["manager"] = {
            "UnifiedConfigManager": UnifiedConfigManager,
            "get_unified_config_manager": get_unified_config_manager,
        }
        # Initialize singleton
        _lazy_cache["unified_config_manager"] = get_unified_config_manager()
    return _lazy_cache["manager"]


def _lazy_import_settings():
    """Lazily import the settings module."""
    if "settings" not in _lazy_cache:
        from config.settings import UnifiedConfigSettings

        _lazy_cache["settings"] = {"UnifiedConfigSettings": UnifiedConfigSettings}
    return _lazy_cache["settings"]


def _lazy_import_compat():
    """Lazily import the compat module."""
    if "compat" not in _lazy_cache:
        from config.compat import (
            API_BASE_URL,
            BACKEND_HOST_IP,
            BACKEND_PORT,
            HTTP_PROTOCOL,
            OLLAMA_HOST_IP,
            OLLAMA_PORT,
            OLLAMA_URL,
            PLAYWRIGHT_HOST_IP,
            PLAYWRIGHT_VNC_PORT,
            PLAYWRIGHT_VNC_URL,
            REDIS_HOST_IP,
            Config,
            get_vnc_direct_url,
        )

        _lazy_cache["compat"] = {
            "API_BASE_URL": API_BASE_URL,
            "BACKEND_HOST_IP": BACKEND_HOST_IP,
            "BACKEND_PORT": BACKEND_PORT,
            "HTTP_PROTOCOL": HTTP_PROTOCOL,
            "OLLAMA_HOST_IP": OLLAMA_HOST_IP,
            "OLLAMA_PORT": OLLAMA_PORT,
            "OLLAMA_URL": OLLAMA_URL,
            "PLAYWRIGHT_HOST_IP": PLAYWRIGHT_HOST_IP,
            "PLAYWRIGHT_VNC_PORT": PLAYWRIGHT_VNC_PORT,
            "PLAYWRIGHT_VNC_URL": PLAYWRIGHT_VNC_URL,
            "REDIS_HOST_IP": REDIS_HOST_IP,
            "Config": Config,
            "get_vnc_direct_url": get_vnc_direct_url,
        }
    return _lazy_cache["compat"]


def __getattr__(name: str):
    """Lazy attribute lookup for module-level imports."""
    # Manager-related attributes
    if name in ("UnifiedConfigManager", "get_unified_config_manager"):
        return _lazy_import_manager()[name]

    if name == "unified_config_manager":
        _lazy_import_manager()
        return _lazy_cache["unified_config_manager"]

    # Backward compatibility aliases
    if name in ("config_manager", "global_config_manager", "config", "cfg"):
        _lazy_import_manager()
        return _lazy_cache["unified_config_manager"]

    if name == "legacy_config":
        _lazy_import_manager()
        compat = _lazy_import_compat()
        if "legacy_config" not in _lazy_cache:
            _lazy_cache["legacy_config"] = compat["Config"](
                _lazy_cache["unified_config_manager"]
            )
        return _lazy_cache["legacy_config"]

    # Settings
    if name == "UnifiedConfigSettings":
        return _lazy_import_settings()["UnifiedConfigSettings"]

    # Compat constants and classes
    compat_names = {
        "API_BASE_URL",
        "BACKEND_HOST_IP",
        "BACKEND_PORT",
        "HTTP_PROTOCOL",
        "OLLAMA_HOST_IP",
        "OLLAMA_PORT",
        "OLLAMA_URL",
        "PLAYWRIGHT_HOST_IP",
        "PLAYWRIGHT_VNC_PORT",
        "PLAYWRIGHT_VNC_URL",
        "REDIS_HOST_IP",
        "Config",
        "get_vnc_direct_url",
    }
    if name in compat_names:
        return _lazy_import_compat()[name]

    raise AttributeError(f"module 'src.config' has no attribute '{name}'")


# Convenience functions - these trigger lazy import when called
def get_config(key: str, default=None):
    """Get configuration value"""
    _lazy_import_manager()
    return _lazy_cache["unified_config_manager"].get(key, default)


def get_config_section(section: str):
    """Get configuration section"""
    _lazy_import_manager()
    return _lazy_cache["unified_config_manager"].get_nested(section, {})


def get_llm_config():
    """Get LLM configuration"""
    _lazy_import_manager()
    return _lazy_cache["unified_config_manager"].get_llm_config()


def get_redis_config():
    """Get Redis configuration"""
    _lazy_import_manager()
    return _lazy_cache["unified_config_manager"].get_redis_config()


def reload_config():
    """Reload configuration from files"""
    _lazy_import_manager()
    _lazy_cache["unified_config_manager"].reload()


def validate_config():
    """Validate configuration and return status"""
    _lazy_import_manager()
    return _lazy_cache["unified_config_manager"].validate_config()


# Async convenience functions
async def get_config_manager_async():
    """Get async config manager instance"""
    _lazy_import_manager()
    return _lazy_cache["unified_config_manager"]


async def load_config_async(config_type: str = "main"):
    """Load configuration asynchronously"""
    _lazy_import_manager()
    return await _lazy_cache["unified_config_manager"].load_config_async(config_type)


async def save_config_async(config_type: str, data):
    """Save configuration asynchronously"""
    _lazy_import_manager()
    await _lazy_cache["unified_config_manager"].save_config_async(config_type, data)


async def get_config_value_async(config_type: str, key: str, default=None):
    """Get configuration value asynchronously"""
    _lazy_import_manager()
    return await _lazy_cache["unified_config_manager"].get_config_value_async(
        config_type, key, default
    )


async def set_config_value_async(config_type: str, key: str, value):
    """Set configuration value asynchronously"""
    _lazy_import_manager()
    await _lazy_cache["unified_config_manager"].set_config_value_async(
        config_type, key, value
    )


# Export all public symbols
__all__ = [
    # Core manager
    "UnifiedConfigManager",
    "unified_config_manager",
    "get_unified_config_manager",
    # Settings
    "UnifiedConfigSettings",
    # Backward compatibility aliases
    "config_manager",
    "global_config_manager",
    "config",
    "cfg",
    "Config",
    "legacy_config",
    # Convenience functions
    "get_config",
    "get_config_section",
    "get_llm_config",
    "get_redis_config",
    "reload_config",
    "validate_config",
    # Async convenience functions
    "get_config_manager_async",
    "load_config_async",
    "save_config_async",
    "get_config_value_async",
    "set_config_value_async",
    # Constants
    "HTTP_PROTOCOL",
    "OLLAMA_HOST_IP",
    "OLLAMA_PORT",
    "OLLAMA_URL",
    "REDIS_HOST_IP",
    "BACKEND_HOST_IP",
    "BACKEND_PORT",
    "API_BASE_URL",
    "PLAYWRIGHT_HOST_IP",
    "PLAYWRIGHT_VNC_PORT",
    "PLAYWRIGHT_VNC_URL",
    "get_vnc_direct_url",
]
