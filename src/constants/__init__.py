"""
AutoBot Constants Package
========================

Centralized constants to eliminate hardcoded values throughout the codebase.
"""

from .network_constants import (
    NetworkConstants,
    ServiceURLs,
    NetworkConfig,
    DatabaseConstants,
    get_network_config,
    # Legacy compatibility exports
    BACKEND_URL,
    FRONTEND_URL,
    REDIS_HOST,
    MAIN_MACHINE_IP,
    LOCALHOST_IP,
)

from .path_constants import PATH

__all__ = [
    "NetworkConstants",
    "ServiceURLs",
    "NetworkConfig",
    "DatabaseConstants",
    "get_network_config",
    # Legacy compatibility
    "BACKEND_URL",
    "FRONTEND_URL",
    "REDIS_HOST",
    "MAIN_MACHINE_IP",
    "LOCALHOST_IP",
    # Path constants
    "PATH",
]
