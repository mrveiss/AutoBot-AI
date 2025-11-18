# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Compatibility Shim for Unified Config Migration

This module provides backward compatibility for code that imports from
src.unified_config while the codebase transitions to src.unified_config_manager.

Usage:
    # Old code continues to work:
    from src.unified_config import config, get_timeout

    # Automatically redirects to:
    # from src.unified_config_manager import ...

This shim will be removed after all imports are migrated (Issue #63).
"""

import warnings
from typing import Any, Dict, Optional

# Import from the canonical config manager
from src.unified_config_manager import UnifiedConfigManager

# Issue deprecation warning
warnings.warn(
    "src.unified_config is deprecated. Use src.unified_config_manager instead. "
    "See Issue #63 for migration details.",
    DeprecationWarning,
    stacklevel=2,
)


# Create adapter class that provides unified_config API
class UnifiedConfigAdapter:
    """
    Adapter that wraps UnifiedConfigManager to provide UnifiedConfig API.

    This ensures backward compatibility while consolidating to a single system.
    """

    def __init__(self):
        self._manager = UnifiedConfigManager()

    def get(self, path: str, default: Any = None) -> Any:
        """Delegate to get_nested for dotted path access"""
        return self._manager.get_nested(path, default)

    def set_nested(self, path: str, value: Any) -> None:
        """Delegate to set_nested"""
        return self._manager.set_nested(path, value)

    def get_host(self, service: str, default: str = "127.0.0.1") -> str:
        """Delegate to get_host"""
        return self._manager.get_host(service)

    def get_port(self, service: str, default: int = 8000) -> int:
        """Delegate to get_port"""
        return self._manager.get_port(service)

    def get_timeout(
        self,
        category: str,
        timeout_type: str = "default",
        default: float = 60.0,
    ) -> float:
        """Delegate to get_timeout"""
        return self._manager.get_timeout(category, timeout_type)

    def get_service_url(self, service: str, endpoint: str = None) -> str:
        """Delegate to get_service_url"""
        return self._manager.get_service_url(service, endpoint)

    def get_redis_config(self) -> Dict[str, Any]:
        """Delegate to get_redis_config"""
        return self._manager.get_redis_config()

    def get_cors_origins(self) -> list:
        """Delegate to get_cors_origins"""
        return self._manager.get_cors_origins()

    def is_feature_enabled(self, feature: str) -> bool:
        """Delegate to is_feature_enabled"""
        return self._manager.is_feature_enabled(feature)

    def get_path(self, category: str, name: str = None) -> str:
        """Delegate to get_path"""
        return self._manager.get_path(category, name)

    def get_timeout_for_env(
        self,
        category: str,
        timeout_type: str,
        environment: str = None,
        default: float = 60.0,
    ) -> float:
        """Delegate to get_timeout_for_env"""
        return self._manager.get_timeout_for_env(
            category, timeout_type, environment, default
        )

    def get_timeout_group(
        self, category: str, environment: str = None
    ) -> Dict[str, float]:
        """Delegate to get_timeout_group"""
        return self._manager.get_timeout_group(category, environment)

    def validate_timeouts(self) -> Dict[str, Any]:
        """Delegate to validate_timeouts"""
        return self._manager.validate_timeouts()

    def reload(self) -> None:
        """Delegate to reload"""
        return self._manager.reload()

    def validate(self) -> Dict[str, Any]:
        """Delegate to validate_config"""
        return self._manager.validate_config()

    def get_security_config(self) -> Dict[str, Any]:
        """Delegate to get_security_config"""
        return self._manager.get_security_config()


# Create singleton instance for backward compatibility
config = UnifiedConfigAdapter()


# Convenience functions for backward compatibility
def get_host(service: str, default: str = "127.0.0.1") -> str:
    return config.get_host(service, default)


def get_port(service: str, default: int = 8000) -> int:
    return config.get_port(service, default)


def get_service_url(service: str, endpoint: str = None) -> str:
    return config.get_service_url(service, endpoint)


def get_timeout(
    category: str, timeout_type: str = "default", default: float = 60.0
) -> float:
    return config.get_timeout(category, timeout_type, default)


def get_timeout_for_env(
    category: str,
    timeout_type: str,
    environment: str = None,
    default: float = 60.0,
) -> float:
    return config.get_timeout_for_env(category, timeout_type, environment, default)


def get_timeout_group(category: str, environment: str = None) -> Dict[str, float]:
    return config.get_timeout_group(category, environment)


# Import and re-export module-level constants from unified_config_manager
from src.unified_config_manager import API_BASE_URL, OLLAMA_URL


# Export commonly used items
__all__ = [
    "config",
    "UnifiedConfigAdapter",
    "get_host",
    "get_port",
    "get_service_url",
    "get_timeout",
    "get_timeout_for_env",
    "get_timeout_group",
    "API_BASE_URL",
    "OLLAMA_URL",
]
