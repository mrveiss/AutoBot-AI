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
"""

import logging

# Import the manager
from src.config.manager import UnifiedConfigManager, get_unified_config_manager

# Import settings for external use
from src.config.settings import UnifiedConfigSettings

# Import constants and classes from compat
from src.config.compat import (
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

logger = logging.getLogger(__name__)

# Create the singleton instance
unified_config_manager = get_unified_config_manager()

# Backward compatibility aliases
config_manager = unified_config_manager  # For utils/config_manager.py imports
global_config_manager = unified_config_manager  # For src/config.py imports
config = unified_config_manager  # General usage
cfg = unified_config_manager  # Short alias for ai_hardware_accelerator.py

# Legacy class wrapper instance
legacy_config = Config(unified_config_manager)


# Convenience functions bound to singleton
def get_config(key: str, default=None):
    """Get configuration value"""
    return unified_config_manager.get(key, default)


def get_config_section(section: str):
    """Get configuration section"""
    return unified_config_manager.get_nested(section, {})


def get_llm_config():
    """Get LLM configuration"""
    return unified_config_manager.get_llm_config()


def get_redis_config():
    """Get Redis configuration"""
    return unified_config_manager.get_redis_config()


def reload_config():
    """Reload configuration from files"""
    unified_config_manager.reload()


def validate_config():
    """Validate configuration and return status"""
    return unified_config_manager.validate_config()


# Async convenience functions
async def get_config_manager_async():
    """Get async config manager instance"""
    return unified_config_manager


async def load_config_async(config_type: str = "main"):
    """Load configuration asynchronously"""
    return await unified_config_manager.load_config_async(config_type)


async def save_config_async(config_type: str, data):
    """Save configuration asynchronously"""
    await unified_config_manager.save_config_async(config_type, data)


async def get_config_value_async(config_type: str, key: str, default=None):
    """Get configuration value asynchronously"""
    return await unified_config_manager.get_config_value_async(config_type, key, default)


async def set_config_value_async(config_type: str, key: str, value):
    """Set configuration value asynchronously"""
    await unified_config_manager.set_config_value_async(config_type, key, value)

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

logger.info("Unified Configuration Package initialized successfully")
