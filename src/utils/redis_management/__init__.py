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
    from src.utils.redis_management import (
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

# Types and constants
from src.utils.redis_management.types import (
    ConnectionState,
    DATABASE_MAPPING,
    RedisDatabase,
)

# Configuration classes
from src.utils.redis_management.config import (
    PoolConfig,
    RedisConfig,
    RedisConfigLoader,
)

# Statistics dataclasses
from src.utils.redis_management.statistics import (
    ConnectionMetrics,
    ManagerStats,
    PoolStatistics,
    RedisStats,
)

# Connection manager
from src.utils.redis_management.connection_manager import (
    RedisConnectionManager,
)

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
