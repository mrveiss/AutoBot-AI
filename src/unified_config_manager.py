#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Configuration Manager for AutoBot

DEPRECATED: This module is now a thin wrapper around src/config package.
The original monolithic file has been modularized (Issues #286, #290).

Original file (1,632 lines) has been split into:
- src/config/settings.py (~40 lines) - Pydantic settings
- src/config/defaults.py (~220 lines) - Default config generation
- src/config/loader.py (~200 lines) - Config loading/merging
- src/config/sync_ops.py (~140 lines) - Synchronous operations
- src/config/async_ops.py (~220 lines) - Async operations
- src/config/model_config.py (~120 lines) - LLM/model management
- src/config/service_config.py (~240 lines) - Service/host/port config
- src/config/timeout_config.py (~140 lines) - Timeout management
- src/config/file_watcher.py (~110 lines) - File watching & callbacks
- src/config/validation.py (~60 lines) - Config validation
- src/config/manager.py (~80 lines) - Core manager class
- src/config/compat.py (~110 lines) - Backward compatibility
- src/config/__init__.py (~120 lines) - Package initialization

For new code, prefer:
    from src.config import unified_config_manager

For backward compatibility, this module still provides all original exports.
"""

# Re-export everything from the modular package
from src.config import (
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
    UnifiedConfigManager,
    UnifiedConfigSettings,
    cfg,
    config,
    config_manager,
    get_config,
    get_config_manager_async,
    get_config_section,
    get_config_value_async,
    get_llm_config,
    get_redis_config,
    get_vnc_direct_url,
    global_config_manager,
    load_config_async,
    reload_config,
    save_config_async,
    set_config_value_async,
    unified_config_manager,
    validate_config,
)

# Ensure all original exports are available
__all__ = [
    # Core classes
    "UnifiedConfigManager",
    "UnifiedConfigSettings",
    "Config",
    # Singleton instances
    "unified_config_manager",
    "config_manager",
    "global_config_manager",
    "config",
    "cfg",
    # Convenience functions
    "get_config",
    "get_config_section",
    "get_llm_config",
    "get_redis_config",
    "reload_config",
    "validate_config",
    # Async functions
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
