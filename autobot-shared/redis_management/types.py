# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Types Module

Contains enums and constants for Redis connection management:
- RedisDatabase: Type-safe database enumeration
- ConnectionState: Circuit breaker connection states

Extracted from redis_client.py as part of Issue #381 refactoring.
"""

from enum import Enum


class RedisDatabase(Enum):
    """
    Type-safe database enumeration for Redis database selection.

    Each value corresponds to a Redis database number (0-15).
    Using named databases improves code readability and reduces errors.
    """

    MAIN = 0
    KNOWLEDGE = 1
    PROMPTS = 2
    AGENTS = 3
    METRICS = 4
    LOGS = 5
    SESSIONS = 6
    WORKFLOWS = 7
    VECTORS = 8
    MODELS = 9
    CACHE = 10  # General application cache (consolidated from redis_pool.py)
    MEMORY = 0  # Uses DB 0 - required for RediSearch indexing (FT.* commands)
    ANALYTICS = 11
    AUDIT = 10  # Note: Shares DB 10 with CACHE - review if separation needed
    FACTS = 11  # Knowledge facts and rules (consolidated from redis_pool.py)
    NOTIFICATIONS = 12
    JOBS = 13
    SEARCH = 14
    TIMESERIES = 15
    TESTING = 15  # Shares with timeseries


class ConnectionState(Enum):
    """
    Redis connection states for circuit breaker pattern.

    States:
    - HEALTHY: Connection is working normally
    - DEGRADED: Connection experiencing intermittent issues
    - FAILED: Connection is down, circuit breaker may be open
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


# Database name to number mapping — aligned with redis-databases.yaml (#2670)
# Canonical allocation: autobot-infrastructure/shared/config/redis-databases.yaml
DATABASE_MAPPING = {
    # Core databases (0-6)
    "main": 0,
    "memory": 0,  # Alias — RediSearch indexing (FT.* commands) on main DB
    "knowledge": 1,
    "prompts": 2,
    "agents": 3,
    "conversations": 3,  # Alias for agents (conversation storage)
    "metrics": 4,
    "cache": 5,
    "sessions": 6,
    "locks": 6,  # Alias for sessions (distributed locks)
    # Extended databases (7-11)
    "workflows": 7,
    "monitoring": 7,  # Alias for workflows
    "logs": 8,
    "vectors": 8,  # Legacy alias — vector_search.py uses this; shares DB with logs
    "temp": 9,
    "audit": 10,
    "analytics": 11,
    "codebase": 11,  # Alias for analytics
    # Reserved (12 unused, 13 testing, 14-15 Celery)
    "testing": 13,
    "celery_broker": 14,
    "celery_results": 15,
}
