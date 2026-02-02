#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Config Registry - Centralized Configuration Access
===================================================

Redis-backed configuration registry with lazy loading and graceful fallbacks.
Eliminates duplicate _get_ssot_config() functions across the codebase.

ARCHITECTURE:
- Lazy Redis connection (only when first accessed)
- Local cache with TTL (default 60s)
- Four-tier fallback: Cache -> Redis -> Environment -> Default

USAGE:
    from src.config.registry import ConfigRegistry

    # Get single value with fallback
    redis_host = ConfigRegistry.get("redis.host", "172.16.168.23")

    # Get section as dict
    redis_config = ConfigRegistry.get_section("redis")

Issue: #751 - Consolidate Common Utilities
"""

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Redis key prefix for all config values
REDIS_CONFIG_PREFIX = "autobot:config:"


class ConfigRegistry:
    """
    Centralized configuration registry with Redis backing.

    Thread-safe singleton that provides:
    - Lazy Redis connection (deferred until first access)
    - Local caching with configurable TTL
    - Graceful fallback chain: Cache -> Redis -> Env -> Default
    """

    _redis_client = None
    _cache: Dict[str, Any] = {}
    _cache_timestamps: Dict[str, float] = {}
    _lock = threading.RLock()
    _ttl_seconds = 60
    _initialized = False

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """
        Get configuration value with fallback chain.

        Args:
            key: Config key in dot notation (e.g., "redis.host")
            default: Default value if not found anywhere

        Returns:
            Configuration value from Redis, env, or default
        """
        try:
            # Check local cache first
            with cls._lock:
                if cls._is_cache_valid(key):
                    return cls._cache[key]

            # Try Redis
            value = cls._fetch_from_redis(key)
            if value is not None:
                cls._update_cache(key, value)
                return value

            # Try environment variable (AUTOBOT_REDIS_HOST format)
            env_key = f"AUTOBOT_{key.upper().replace('.', '_')}"
            env_value = os.getenv(env_key)
            if env_value is not None:
                cls._update_cache(key, env_value)
                return env_value

            # Return default (don't cache defaults)
            return default

        except Exception as e:
            logger.warning("Config lookup failed for %s: %s", key, e)
            return default

    @classmethod
    def _is_cache_valid(cls, key: str) -> bool:
        """Check if cached value exists and is not expired."""
        if key not in cls._cache:
            return False
        if key not in cls._cache_timestamps:
            return False
        age = time.time() - cls._cache_timestamps[key]
        return age < cls._ttl_seconds

    @classmethod
    def _update_cache(cls, key: str, value: Any) -> None:
        """Update cache with new value and timestamp."""
        with cls._lock:
            cls._cache[key] = value
            cls._cache_timestamps[key] = time.time()

    @classmethod
    def _fetch_from_redis(cls, key: str) -> Optional[str]:
        """Fetch value from Redis. Returns None if not found or error."""
        try:
            redis_client = cls._get_redis()
            if redis_client is None:
                return None
            redis_key = f"{REDIS_CONFIG_PREFIX}{key}"
            value = redis_client.get(redis_key)
            if value is not None:
                return value.decode("utf-8") if isinstance(value, bytes) else value
            return None
        except Exception as e:
            logger.debug("Redis fetch failed for %s: %s", key, e)
            return None

    @classmethod
    def _get_redis(cls):
        """Lazy Redis connection - only when first needed."""
        if cls._redis_client is None:
            try:
                from src.utils.redis_client import get_redis_client

                cls._redis_client = get_redis_client(database="main")
            except Exception as e:
                logger.debug("Redis connection failed: %s", e)
                return None
        return cls._redis_client

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached values. Useful for testing."""
        with cls._lock:
            cls._cache.clear()
            cls._cache_timestamps.clear()
            cls._redis_client = None

    @classmethod
    def get_section(cls, prefix: str) -> Dict[str, Any]:
        """
        Get all config values matching a prefix as a dictionary.

        Args:
            prefix: Key prefix (e.g., "redis" returns all "redis.*" keys)

        Returns:
            Dictionary with keys stripped of prefix
        """
        result = {}
        prefix_dot = f"{prefix}."

        with cls._lock:
            for key, value in cls._cache.items():
                if key.startswith(prefix_dot):
                    short_key = key[len(prefix_dot) :]
                    result[short_key] = value

        return result

    @classmethod
    def set(cls, key: str, value: Any) -> bool:
        """
        Set configuration value in Redis and local cache.

        Args:
            key: Config key in dot notation
            value: Value to store

        Returns:
            True if successfully stored in Redis, False otherwise
        """
        try:
            redis_client = cls._get_redis()
            if redis_client is not None:
                redis_key = f"{REDIS_CONFIG_PREFIX}{key}"
                redis_client.set(redis_key, str(value))

            cls._update_cache(key, value)
            return True
        except Exception as e:
            logger.warning("Config set failed for %s: %s", key, e)
            cls._update_cache(key, value)  # Still cache locally
            return False

    @classmethod
    def refresh(cls, key: str) -> Any:
        """
        Force refresh a key from Redis, bypassing cache.

        Args:
            key: Config key to refresh

        Returns:
            Fresh value from Redis or None
        """
        with cls._lock:
            if key in cls._cache:
                del cls._cache[key]
            if key in cls._cache_timestamps:
                del cls._cache_timestamps[key]

        return cls.get(key)
