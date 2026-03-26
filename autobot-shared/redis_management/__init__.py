# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Management Package (#2313).

Canonical location for Redis connection management. Moved from
autobot-backend/utils/redis_management/ to autobot-shared/ so all
components (backend, SLM backend, standalone scripts) share the same code.

Package Structure:
- types.py: Enums (RedisDatabase, ConnectionState) and database mapping
- config.py: RedisConfig, RedisConfigLoader, PoolConfig
- statistics.py: RedisStats, PoolStatistics, ManagerStats, ConnectionMetrics
- connection_manager.py: RedisConnectionManager class

Usage:
    from autobot_shared.redis_management import (
        RedisDatabase, ConnectionState,
        RedisConfig, RedisConfigLoader, PoolConfig,
        RedisStats, PoolStatistics, ManagerStats, ConnectionMetrics,
        RedisConnectionManager,
        DATABASE_MAPPING,
    )
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
