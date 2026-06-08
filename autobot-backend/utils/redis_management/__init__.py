# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Management — backward-compatibility shim (Issue #2313).

The canonical implementation has moved to autobot_shared.redis_management.
All existing imports of ``from utils.redis_management import ...``
continue to work unchanged via this re-export.

Preferred import:
    from autobot_shared.redis_management import RedisConnectionManager
"""

from autobot_shared.redis_management import (  # noqa: F401
    DATABASE_MAPPING,
    ConnectionMetrics,
    ConnectionState,
    ManagerStats,
    PoolConfig,
    PoolStatistics,
    RedisConfig,
    RedisConfigLoader,
    RedisConnectionManager,
    RedisDatabase,
    RedisStats,
)

__all__ = [
    "RedisDatabase",
    "ConnectionState",
    "DATABASE_MAPPING",
    "RedisConfig",
    "RedisConfigLoader",
    "PoolConfig",
    "RedisStats",
    "PoolStatistics",
    "ManagerStats",
    "ConnectionMetrics",
    "RedisConnectionManager",
]
