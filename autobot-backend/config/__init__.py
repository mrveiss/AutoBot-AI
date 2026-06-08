#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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

    Issue #1882: model_constants previously imported ConfigRegistry at module level AND
    called ConfigRegistry.get() in class/dataclass body (executed at import time), creating
    a second cycle: manager → loader → defaults → model_constants → config.registry.
    Fixed by removing the module-level ConfigRegistry import from model_constants and
    making ConfigRegistry calls in ModelConstants.get_ollama_url() lazy (inside the method).
"""

import logging
from typing import TYPE_CHECKING

from autobot_shared.ssot_config import config

# Use stdlib logging here to avoid circular import:
# constants → network_constants → autobot_shared/network_constants → config.registry →
# config/__init__ → get_logger → logging_manager → from config import config_manager (incomplete)
# GH#7765
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
    from config.manager import ConfigManager, get_config_manager
    from config.settings import ConfigSettings

# Cache for lazily imported modules/objects
_lazy_cache: dict = {}
# Re-entry guard: True while _lazy_import_manager() is executing (#1862).
# During ConfigManager init, load_configuration() can trigger imports that
# re-enter __getattr__ looking for "config_manager" before it's cached.
_manager_initializing = False


class _ConfigStub:
    """Minimal stub returned during re-entrant config init (#1862)."""

    def get(self, key, default=None):
        return default

    def get_nested(self, key, default=None):
        return default

    def get_redis_config(self):
        """Env-var fallback so redis_client.get_redis_client() survives re-entry (#3491)."""

        return {
            "enabled": config.redis_enabled.lower() == "true",
            "host": config.redis_host,
            "port": int(config.redis_port),
            "db": int(config.redis_db_main),
        }

    def get_llm_config(self):
        return {}

    def reload(self):
        pass

    def validate_config(self):
        return {}

    def is_feature_enabled(self, feature):
        return False

    async def load_config_async(self, config_type="main"):
        return {}

    async def save_config_async(self, config_type, data):
        pass

    async def get_config_value_async(self, config_type, key, default=None):
        return default

    async def set_config_value_async(self, config_type, key, value):
        pass

    def __bool__(self):
        return False


def _lazy_import_manager():
    """Lazily import the manager module.

    Uses a re-entry guard (#1862) because ConfigManager() init can
    trigger imports that circle back to config.__getattr__. During
    re-entry, _get_cached_config_manager() returns _ConfigStub.
    """
    global _manager_initializing
    if "config_manager" in _lazy_cache:
        return _lazy_cache.get("manager", {})
    if _manager_initializing:
        return _lazy_cache.get("manager", {})
    _manager_initializing = True
    try:
        from config.manager import (
            ConfigManager,
            UnifiedConfigManager,
            get_config_manager,
            get_unified_config_manager,
        )

        _lazy_cache["manager"] = {
            "ConfigManager": ConfigManager,
            "get_config_manager": get_config_manager,
            # Deprecated aliases
            "UnifiedConfigManager": UnifiedConfigManager,
            "get_unified_config_manager": get_unified_config_manager,
        }
        _lazy_cache["config_manager"] = get_config_manager()
    finally:
        _manager_initializing = False
    return _lazy_cache.get("manager", {})


def _get_cached_config_manager():
    """Return cached config_manager, or a no-op stub during init (#1862).

    During ConfigManager initialization, re-entrant calls to __getattr__
    arrive before config_manager is cached. Return a stub that responds
    to .get() with defaults so callers degrade gracefully.
    """
    if "config_manager" in _lazy_cache:
        return _lazy_cache["config_manager"]
    if _manager_initializing:
        return _ConfigStub()
    _lazy_import_manager()
    return _lazy_cache["config_manager"]


def _lazy_import_settings():
    """Lazily import the settings module."""
    if "settings" not in _lazy_cache:
        from config.settings import ConfigSettings, UnifiedConfigSettings

        _lazy_cache["settings"] = {
            "ConfigSettings": ConfigSettings,
            # Deprecated alias
            "UnifiedConfigSettings": UnifiedConfigSettings,
        }
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
    # Manager-related attributes (new names + deprecated aliases)
    if name in (
        "ConfigManager",
        "get_config_manager",
        "UnifiedConfigManager",
        "get_unified_config_manager",
    ):
        return _lazy_import_manager()[name]

    if name in ("config_manager", "unified_config_manager"):
        return _get_cached_config_manager()

    # Backward compatibility aliases
    if name in ("global_config_manager", "config", "cfg"):
        return _get_cached_config_manager()

    if name == "legacy_config":
        _lazy_import_manager()
        compat = _lazy_import_compat()
        if "legacy_config" not in _lazy_cache:
            _lazy_cache["legacy_config"] = compat["Config"](_get_cached_config_manager())
        return _lazy_cache["legacy_config"]

    # Settings (new name + deprecated alias)
    if name in ("ConfigSettings", "UnifiedConfigSettings"):
        return _lazy_import_settings()[name]

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


# Convenience functions - use _get_cached_config_manager for re-entry safety (#1862)
def get_config(key: str, default=None):
    """Get configuration value"""
    return _get_cached_config_manager().get(key, default)


def get_config_section(section: str):
    """Get configuration section"""
    return _get_cached_config_manager().get_nested(section, {})


def get_llm_config():
    """Get LLM configuration"""
    return _get_cached_config_manager().get_llm_config()


def get_redis_config():
    """Get Redis configuration"""
    return _get_cached_config_manager().get_redis_config()


def reload_config():
    """Reload configuration from files"""
    _get_cached_config_manager().reload()


def validate_config():
    """Validate configuration and return status"""
    return _get_cached_config_manager().validate_config()


def is_feature_enabled(feature: str) -> bool:
    """Check if a feature is enabled (e.g. 'multimodal.vision', 'npu')."""
    return _get_cached_config_manager().is_feature_enabled(feature)


# Async convenience functions
async def get_config_manager_async():
    """Get async config manager instance"""
    return _get_cached_config_manager()


async def load_config_async(config_type: str = "main"):
    """Load configuration asynchronously"""
    return await _get_cached_config_manager().load_config_async(config_type)


async def save_config_async(config_type: str, data):
    """Save configuration asynchronously"""
    await _get_cached_config_manager().save_config_async(config_type, data)


async def get_config_value_async(config_type: str, key: str, default=None):
    """Get configuration value asynchronously"""
    return await _get_cached_config_manager().get_config_value_async(config_type, key, default)


async def set_config_value_async(config_type: str, key: str, value):
    """Set configuration value asynchronously"""
    await _get_cached_config_manager().set_config_value_async(config_type, key, value)


# Export all public symbols
__all__ = [
    # Core manager
    "ConfigManager",
    "config_manager",
    "get_config_manager",
    # Deprecated aliases (remove after one release cycle)
    "UnifiedConfigManager",
    "unified_config_manager",
    "get_unified_config_manager",
    # Settings
    "ConfigSettings",
    # Deprecated alias (remove after one release cycle)
    "UnifiedConfigSettings",
    # Backward compatibility aliases
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
