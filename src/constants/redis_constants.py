# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized Redis Key Constants for AutoBot
============================================

Single source of truth for all Redis key patterns and connection configuration.

SSOT Migration (Issue #763):
    Database numbers now use ConfigRegistry with five-tier fallback:
    Cache → Redis → Environment → Registry Defaults → Caller Default

    For Redis connection parameters, prefer:
        from src.config.registry import ConfigRegistry
        db_main = int(ConfigRegistry.get("redis.db_main", "0"))

Usage:
    from src.constants.redis_constants import REDIS_KEY, REDIS_CONFIG

    # Get Redis keys
    key = REDIS_KEY.PROMPTS_FILE_STATES

    # Get connection config
    timeout = REDIS_CONFIG.SOCKET_TIMEOUT
"""

import os
from dataclasses import dataclass


def _get_redis_config(key: str, default: str) -> str:
    """Get Redis config from env or default (avoids circular import)."""
    env_key = f"AUTOBOT_{key.upper().replace('.', '_')}"
    return os.getenv(env_key, default)


@dataclass(frozen=True)
class RedisConnectionConfig:
    """
    Centralized Redis connection configuration.

    SSOT Migration (Issue #602):
        For host/port/database numbers, use SSOT config directly:
            from src.config.ssot_config import config
            host = config.vm.redis
            port = config.port.redis
    """

    # Socket timeouts (seconds)
    SOCKET_TIMEOUT: int = 5
    SOCKET_CONNECT_TIMEOUT: int = 3

    # Connection pool settings (Issue #743: Optimized for memory efficiency)
    MAX_CONNECTIONS: int = 10  # Default for simple connections
    MAX_CONNECTIONS_POOL: int = 20  # Optimized for memory - pools reuse connections
    MIN_CONNECTIONS_POOL: int = 2  # Minimum connections in pool
    HEALTH_CHECK_INTERVAL: int = 30

    # Circuit breaker settings (Issue #611)
    CIRCUIT_BREAKER_THRESHOLD: int = 5  # failures before tripping
    CIRCUIT_BREAKER_TIMEOUT: int = 60  # seconds to wait before retry

    # Retry settings
    RETRY_ON_TIMEOUT: bool = True

    # Database assignments (Issue #763: Uses env vars with defaults)
    @property
    def db_main(self) -> int:
        """Main database number."""
        return int(_get_redis_config("redis.db_main", "0"))

    @property
    def db_knowledge(self) -> int:
        """Knowledge database number."""
        return int(_get_redis_config("redis.db_knowledge", "1"))

    @property
    def db_cache(self) -> int:
        """Cache database number."""
        return int(_get_redis_config("redis.db_cache", "5"))

    @property
    def db_sessions(self) -> int:
        """Sessions database number."""
        return int(_get_redis_config("redis.db_sessions", "6"))


@dataclass(frozen=True)
class RedisKeyConstants:
    """Centralized Redis key patterns - NO HARDCODED KEYS"""

    # Namespace prefix
    NAMESPACE: str = "autobot"

    # Prompts and templates
    PROMPTS_FILE_STATES: str = f"{NAMESPACE}:prompts:file_states"

    # System knowledge
    SYSTEM_KNOWLEDGE_FILE_STATES: str = f"{NAMESPACE}:system_knowledge:file_states"

    # Workflow management
    WORKFLOW_CLASSIFICATION_RULES: str = f"{NAMESPACE}:workflow:classification:rules"
    WORKFLOW_CLASSIFICATION_KEYWORDS: str = (
        f"{NAMESPACE}:workflow:classification:keywords"
    )

    # Sandbox security
    SANDBOX_SECURITY_EVENTS: str = f"{NAMESPACE}:sandbox:security:events"
    SANDBOX_METRICS: str = f"{NAMESPACE}:sandbox:metrics"

    # Entity resolution
    ENTITY_MAPPINGS: str = "entity_mappings"
    ENTITY_EMBEDDINGS: str = "entity_embeddings"
    ENTITY_RESOLUTION_HISTORY: str = "entity_resolution_history"

    # System metrics
    KB_CACHE_STATS: str = "kb_cache_stats"

    # Fact extraction
    ATOMIC_FACTS_INDEX: str = "atomic_facts_index"
    FACT_EXTRACTION_HISTORY: str = "fact_extraction_history"

    # Temporal invalidation
    TEMPORAL_INVALIDATION_RULES: str = "temporal_invalidation_rules"
    TEMPORAL_INVALIDATION_HISTORY: str = "temporal_invalidation_history"
    INVALIDATED_FACTS_INDEX: str = "invalidated_facts_index"
    INVALIDATION_SCHEDULE: str = "invalidation_schedule"

    # LLM caching
    LLM_MODELS_CACHE: str = "llm_models"

    @classmethod
    def get_key(cls, key_pattern: str, *args) -> str:
        """Build Redis key with dynamic parts"""
        if args:
            return f"{key_pattern}:{':'.join(str(arg) for arg in args)}"
        return key_pattern

    @classmethod
    def get_sandbox_event_key(cls, sandbox_id: str) -> str:
        """Get sandbox security event key"""
        return f"{cls.SANDBOX_SECURITY_EVENTS}:{sandbox_id}"

    @classmethod
    def get_sandbox_metrics_key(cls, sandbox_id: str) -> str:
        """Get sandbox metrics key"""
        return f"{cls.SANDBOX_METRICS}:{sandbox_id}"


# Export constants instances
REDIS_KEY = RedisKeyConstants()
REDIS_CONFIG = RedisConnectionConfig()
