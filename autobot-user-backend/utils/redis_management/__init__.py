# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Management Package

This package contains the Redis connection management system for AutoBot.
It was split from the monolithic redis_client.py as part of Issue #381.

Package Structure:
- types.py: Enums (RedisDatabase, ConnectionState) and database mapping
- config.py: RedisConfig, RedisConfigLoader, PoolConfig
- statistics.py: RedisStats, PoolStatistics, ManagerStats, ConnectionMetrics
- connection_manager.py: RedisConnectionManager class

Usage:
    from utils.redis_management import (
        # Enums
        RedisDatabase, ConnectionState,
        # Configuration
        RedisConfig, RedisConfigLoader, PoolConfig,
        # Statistics
        RedisStats, PoolStatistics, ManagerStats, ConnectionMetrics,
        # Manager
        RedisConnectionManager,
        # Constants
        DATABASE_MAPPING,
    )

For backward compatibility, the original redis_client.py module
still exports all classes and functions directly.
"""

# Configuration classes
from .config import PoolConfig, RedisConfig, RedisConfigLoader

# Connection manager
from .connection_manager import RedisConnectionManager

# Statistics dataclasses
from .statistics import ConnectionMetrics, ManagerStats, PoolStatistics, RedisStats

# Types and constants
from .types import DATABASE_MAPPING, ConnectionState, RedisDatabase

# Re-export for convenience
__all__ = [
    # Enums
    "RedisDatabase",
    "ConnectionState",
    # Constants
    "DATABASE_MAPPING",
    # Configuration
    "RedisConfig",
    "RedisConfigLoader",
    "PoolConfig",
    # Statistics
    "RedisStats",
    "PoolStatistics",
    "ManagerStats",
    "ConnectionMetrics",
    # Manager
    "RedisConnectionManager",
]
