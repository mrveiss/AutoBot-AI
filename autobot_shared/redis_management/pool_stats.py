# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pool statistics for ``RedisConnectionManager``, grouped by database (#18553).

A database can hold two pools -- the YAML decode mode under the bare name and the opposite mode under
``<name>#decode=<bool>`` (``RedisConnectionManager._pool_key``). Statistics report the database name
with a ``decode_responses`` field, never the registry key, so a caller asking about ``main`` finds
both variants and a dashboard does not list ``main#decode=False`` as a database of its own.
"""

import logging
from datetime import datetime
from typing import Any

from autobot_shared.redis_management.statistics import PoolStatistics

logger = logging.getLogger(__name__)

DECODE_MARKER = "#decode="


def split_pool_key(key: str) -> tuple[str, bool | None]:
    """Inverse of ``_pool_key``: ``(database, decode)``; decode is None for a bare database name."""
    database, marker, mode = key.partition(DECODE_MARKER)
    return (database, mode == "True") if marker else (key, None)


def count_idle_connections(available_conns: list, threshold: int = 60) -> int:
    """Count connections idle longer than *threshold* seconds."""
    return sum(
        1
        for conn in available_conns
        if hasattr(conn, "_last_use") and (datetime.now() - conn._last_use).total_seconds() > threshold
    )


def pool_statistics(pool: Any, database: str, decode_responses: bool | None) -> PoolStatistics:
    """Thread-safe snapshot of *pool*; zero counters (real ``max_connections``) if it cannot be read."""
    try:
        with pool._lock:
            available_conns = getattr(pool, "_available_connections", [])
            return PoolStatistics(
                database_name=database,
                created_connections=getattr(pool, "_created_connections", 0),
                available_connections=len(available_conns),
                in_use_connections=len(getattr(pool, "_in_use_connections", [])),
                max_connections=pool.max_connections,
                idle_connections=count_idle_connections(available_conns),
                decode_responses=decode_responses,
            )
    except Exception as e:
        logger.error("Error getting pool statistics for '%s': %s", database, e)
        return PoolStatistics(database, 0, 0, 0, pool.max_connections, 0, decode_responses=decode_responses)
