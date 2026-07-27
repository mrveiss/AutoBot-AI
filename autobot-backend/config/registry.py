#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Config Registry - Centralized Configuration Access
===================================================

Redis-backed configuration registry with lazy loading and graceful fallbacks.
Eliminates duplicate _get_ssot_config() functions across the codebase.

ARCHITECTURE:
- Lazy Redis connection (only when first accessed)
- Local cache with TTL (default 60s)
- Five-tier fallback: Cache -> Redis -> Environment -> Registry Defaults -> Caller Default

USAGE:
    from config.registry import ConfigRegistry

    # Get single value with fallback
    redis_host = ConfigRegistry.get("redis.host")  # SSOT default via registry_defaults

    # Get section as dict
    redis_config = ConfigRegistry.get_section("redis")

Issue: #751 - Consolidate Common Utilities
"""

import logging
import os
import threading
import time
from typing import Any, Dict

# stdlib logging avoids circular import: network_constants → config.registry → get_logger
# → logging_manager → from config import config_manager (partially initialized) GH#7765
logger = logging.getLogger(__name__)

# Redis key prefix for all config values
REDIS_CONFIG_PREFIX = "autobot:config:"

# Issue #12674: how long to stop re-dialling Redis after a failed connect.
# Without this the registry re-attempted a blocking sync connect on EVERY
# lookup, so a single import that resolves ~29 config keys with Redis
# unreachable opened 29 connections and tripped the 'main' circuit breaker.
# Bounded so a Redis that comes up after the config layer is still picked up.
REDIS_RETRY_INTERVAL_SECONDS = float(os.getenv("AUTOBOT_CONFIG_REGISTRY_REDIS_RETRY_SECONDS", "30"))


class ConfigRegistry:
    """
    Centralized configuration registry with Redis backing.

    Thread-safe singleton that provides:
    - Lazy Redis connection (deferred until first access)
    - Local caching with configurable TTL
    - Graceful fallback chain: Cache -> Redis -> Env -> Registry Defaults -> Caller Default
    """

    _redis_client = None
    _cache: Dict[str, Any] = {}
    _cache_timestamps: Dict[str, float] = {}
    _lock = threading.RLock()
    _ttl_seconds = 60
    _initialized = False
    # Issue #12674: monotonic deadline before which _get_redis() skips dialling
    # Redis because the previous connect attempt failed.
    _redis_retry_after: float = 0.0

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
            env_value = os.getenv(env_key)  # ssot-config-exempt: dynamic config key lookup
            if env_value is not None:
                cls._update_cache(key, env_value)
                return env_value

            # Try registry defaults
            from config.registry_defaults import get_default

            registry_default = get_default(key)
            if registry_default is not None:
                return registry_default

            # Return caller's default (don't cache defaults)
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
    def _fetch_from_redis(cls, key: str) -> str | None:
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
        """Lazy Redis connection - only when first needed.

        Issue #12674: a failed connect is remembered for
        ``REDIS_RETRY_INTERVAL_SECONDS`` instead of being retried on every
        lookup. Redis is an optional tier in the fallback chain, so when it is
        unreachable the registry must degrade to env/registry_defaults without
        spending a blocking connect (and a circuit-breaker failure) per key.
        """
        if cls._redis_client is not None:
            return cls._redis_client

        with cls._lock:
            if cls._redis_client is not None:
                return cls._redis_client
            if time.monotonic() < cls._redis_retry_after:
                return None

            try:
                from autobot_shared.redis_client import get_redis_client
            except ImportError as e:
                # Transient, NOT a Redis outage: autobot_shared.redis_client
                # imports network_constants, whose module-level constants resolve
                # through this registry while network_constants is still
                # mid-import. Returning None lets the caller fall back to
                # env/registry_defaults; arming the retry guard here would
                # wrongly suppress Redis-backed config on a healthy system.
                logger.debug("Redis client not importable yet (circular import): %s", e)
                return None

            try:
                client = get_redis_client(database="main")
            except Exception as e:
                logger.debug("Redis connection failed: %s", e)
                client = None

            if client is None:
                cls._redis_retry_after = time.monotonic() + REDIS_RETRY_INTERVAL_SECONDS
                return None

            cls._redis_client = client
            return client

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached values. Useful for testing."""
        with cls._lock:
            cls._cache.clear()
            cls._cache_timestamps.clear()
            cls._redis_client = None
            # Issue #12674: also drop the failed-connect backoff so a cleared
            # registry re-probes Redis immediately instead of staying degraded.
            cls._redis_retry_after = 0.0

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
