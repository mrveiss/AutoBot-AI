# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
DEPRECATED: This module redirects to unified_config_manager.py

All functionality has been consolidated into src.unified_config_manager.
This file exists only for backward compatibility during migration.

Migration Status: Issue #63
Expected Removal: After all 20 imports are migrated to unified_config_manager

Usage:
    # Old imports continue to work but show deprecation warning:
    from src.unified_config import config, get_timeout

    # New recommended import:
    from src.unified_config_manager import UnifiedConfigManager
"""

# Re-export everything from the compatibility shim
from src.unified_config_shim import (
    UnifiedConfigAdapter,
    config,
    get_host,
    get_port,
    get_service_url,
    get_timeout,
    get_timeout_for_env,
    get_timeout_group,
)

# Also provide UnifiedConfig as alias for backward compatibility
UnifiedConfig = UnifiedConfigAdapter

__all__ = [
    "config",
    "UnifiedConfig",
    "UnifiedConfigAdapter",
    "get_host",
    "get_port",
    "get_service_url",
    "get_timeout",
    "get_timeout_for_env",
    "get_timeout_group",
]
