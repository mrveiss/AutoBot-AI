# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Statistics Module

Contains dataclasses for tracking Redis connection statistics:
- RedisStats: Per-database statistics
- PoolStatistics: Connection pool statistics
- ManagerStats: Overall manager statistics
- ConnectionMetrics: Connection metrics (legacy compatibility)

Extracted from redis_client.py as part of Issue #381 refactoring.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass
class RedisStats:
    """
    Per-database Redis statistics.

    Tracks operations, errors, and timing for a single database.
    Used for monitoring and debugging connection health.
    """

    database_name: str
    total_connections: int = 0
    active_connections: int = 0
    failed_connections: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    total_retry_attempts: int = 0
    circuit_breaker_trips: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    uptime_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        total = self.successful_operations + self.failed_operations
        if total == 0:
            return 100.0
        return (self.successful_operations / total) * 100.0


@dataclass
class PoolStatistics:
    """
    Connection pool statistics.

    Provides detailed metrics about connection pool state,
    useful for tuning pool size and identifying connection leaks.
    """

    database_name: str
    created_connections: int
    available_connections: int
    in_use_connections: int
    max_connections: int
    idle_connections: int
    last_cleanup: Optional[datetime] = None


@dataclass
class ManagerStats:
    """
    Overall manager statistics.

    Aggregates statistics across all databases for high-level
    monitoring and health dashboards.
    """

    total_databases: int
    healthy_databases: int
    degraded_databases: int
    failed_databases: int
    total_operations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    uptime_seconds: float = 0.0
    database_stats: Dict[str, RedisStats] = field(default_factory=dict)

    @property
    def overall_success_rate(self) -> float:
        """Calculate overall success rate across all databases."""
        total_success = sum(
            s.successful_operations for s in self.database_stats.values()
        )
        total_failed = sum(s.failed_operations for s in self.database_stats.values())
        total = total_success + total_failed
        if total == 0:
            return 100.0
        return (total_success / total) * 100.0


@dataclass
class ConnectionMetrics:
    """
    Connection metrics and statistics.

    Legacy dataclass kept for backward compatibility with existing
    code that uses the ConnectionMetrics interface.
    """

    created_connections: int = 0
    active_connections: int = 0
    failed_connections: int = 0
    reconnections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    avg_response_time_ms: float = 0.0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    last_success_time: Optional[float] = None
    circuit_breaker_state: str = "closed"

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 100.0
        successful = self.total_requests - self.failed_requests
        return (successful / self.total_requests) * 100.0
