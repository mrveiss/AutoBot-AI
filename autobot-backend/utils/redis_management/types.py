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


# Database name to number mapping (canonical source)
# Complete mapping matching all usage across AutoBot codebase
DATABASE_MAPPING = {
    # Core databases
    "main": 0,
    "knowledge": 1,
    "prompts": 2,
    "agents": 3,
    "conversations": 3,  # Alias for agents (conversation storage)
    "metrics": 4,
    "cache": 5,
    "sessions": 6,
    "locks": 6,  # Alias for sessions (distributed locks)
    "workflows": 7,
    "monitoring": 7,  # Alias for workflows (monitoring data)
    "vectors": 8,
    "rate_limiting": 8,  # Alias for vectors (rate limit counters)
    "models": 9,
    "memory": 0,  # Uses DB 0 - required for RediSearch indexing (FT.* commands)
    "analytics": 9,  # Maps to models database
    "websockets": 10,
    "config": 11,  # CRITICAL: Cache configuration storage
    "facts": 11,  # Knowledge facts and rules (consolidated from redis_pool.py)
    "audit": 12,  # Security audit logging (OWASP/NIST compliant)
}
