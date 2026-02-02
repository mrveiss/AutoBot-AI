#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for ConfigRegistry."""

import os
import time
from unittest.mock import MagicMock, patch


class TestConfigRegistryBasic:
    """Basic ConfigRegistry functionality tests."""

    def test_get_returns_default_when_no_value(self):
        """Test that get() returns default when key not found anywhere."""
        from src.config.registry import ConfigRegistry

        # Clear any cached state
        ConfigRegistry.clear_cache()

        # Mock Redis to return None
        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                result = ConfigRegistry.get("nonexistent.key", default="fallback")
                assert result == "fallback"

    def test_get_returns_redis_value_when_available(self):
        """Test that get() returns Redis value when available."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        # Mock Redis to return a value
        with patch.object(
            ConfigRegistry, "_fetch_from_redis", return_value="redis_value"
        ):
            result = ConfigRegistry.get("some.key", default="default")
            assert result == "redis_value"

    def test_get_returns_env_value_when_redis_unavailable(self):
        """Test that get() falls back to env when Redis unavailable."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        # Mock Redis to return None (not found)
        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            # Set environment variable (AUTOBOT_REDIS_HOST format)
            with patch.dict(os.environ, {"AUTOBOT_REDIS_HOST": "env_host"}):
                result = ConfigRegistry.get("redis.host", default="default_host")
                assert result == "env_host"

    def test_get_uses_cache_on_subsequent_calls(self):
        """Test that get() uses cache on repeated calls."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        # First call - fetch from Redis
        with patch.object(
            ConfigRegistry, "_fetch_from_redis", return_value="cached_value"
        ) as mock_redis:
            result1 = ConfigRegistry.get("cache.test.key")
            assert result1 == "cached_value"
            assert mock_redis.call_count == 1

            # Second call - should use cache, not call Redis again
            result2 = ConfigRegistry.get("cache.test.key")
            assert result2 == "cached_value"
            # Redis should NOT be called again
            assert mock_redis.call_count == 1

    def test_clear_cache_resets_state(self):
        """Test that clear_cache() properly resets all cached state."""
        from src.config.registry import ConfigRegistry

        # Populate cache
        ConfigRegistry._cache["test.key"] = "test_value"
        ConfigRegistry._cache_timestamps["test.key"] = time.time()

        # Clear cache
        ConfigRegistry.clear_cache()

        # Verify cache is empty
        assert len(ConfigRegistry._cache) == 0
        assert len(ConfigRegistry._cache_timestamps) == 0
        assert ConfigRegistry._redis_client is None

    def test_get_handles_none_default(self):
        """Test that get() properly handles None as default."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                result = ConfigRegistry.get("missing.key")
                assert result is None

    def test_get_returns_default_on_exception(self):
        """Test that get() returns default when an exception occurs."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        # Mock Redis to raise an exception
        with patch.object(
            ConfigRegistry, "_fetch_from_redis", side_effect=Exception("Test error")
        ):
            with patch.dict(os.environ, {}, clear=True):
                result = ConfigRegistry.get("error.key", default="safe_default")
                assert result == "safe_default"

    def test_get_falls_back_to_env_var(self):
        """Test that get() falls back to environment variable."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            with patch.dict(
                os.environ, {"AUTOBOT_REDIS_HOST": "10.0.0.99"}, clear=True
            ):
                result = ConfigRegistry.get("redis.host", default="172.16.168.23")
                assert result == "10.0.0.99"

    def test_env_var_key_conversion(self):
        """Test that dot notation converts to underscore for env vars."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            with patch.dict(
                os.environ, {"AUTOBOT_BACKEND_API_PORT": "9000"}, clear=True
            ):
                result = ConfigRegistry.get("backend.api.port", default="8001")
                assert result == "9000"


class TestConfigRegistryCaching:
    """ConfigRegistry caching behavior tests."""

    def test_cached_value_returned_without_redis_call(self):
        """Test that cached values don't trigger Redis fetch."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        mock_fetch = MagicMock(return_value="cached_value")
        with patch.object(ConfigRegistry, "_fetch_from_redis", mock_fetch):
            # First call should fetch from Redis
            result1 = ConfigRegistry.get("test.key")
            assert result1 == "cached_value"
            assert mock_fetch.call_count == 1

            # Second call should use cache
            result2 = ConfigRegistry.get("test.key")
            assert result2 == "cached_value"
            assert mock_fetch.call_count == 1  # Still 1, not 2

    def test_cache_expires_after_ttl(self):
        """Test that cache expires after TTL seconds."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()
        original_ttl = ConfigRegistry._ttl_seconds
        ConfigRegistry._ttl_seconds = 0.1  # 100ms for testing

        try:
            mock_fetch = MagicMock(return_value="value")
            with patch.object(ConfigRegistry, "_fetch_from_redis", mock_fetch):
                ConfigRegistry.get("expiring.key")
                assert mock_fetch.call_count == 1

                # Wait for expiration
                time.sleep(0.15)

                ConfigRegistry.get("expiring.key")
                assert mock_fetch.call_count == 2  # Cache expired, fetched again
        finally:
            ConfigRegistry._ttl_seconds = original_ttl

    def test_clear_cache_removes_all_values(self):
        """Test that clear_cache removes all cached values."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value="val"):
            ConfigRegistry.get("key1")
            ConfigRegistry.get("key2")

        assert "key1" in ConfigRegistry._cache
        assert "key2" in ConfigRegistry._cache

        ConfigRegistry.clear_cache()

        assert "key1" not in ConfigRegistry._cache
        assert "key2" not in ConfigRegistry._cache


class TestConfigRegistrySections:
    """ConfigRegistry section operations tests."""

    def test_get_section_returns_dict(self):
        """Test that get_section returns a dictionary of matching keys."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        # Pre-populate cache with section values
        ConfigRegistry._cache = {
            "redis.host": "172.16.168.23",
            "redis.port": "6379",
            "redis.database": "0",
            "backend.port": "8001",
        }
        ConfigRegistry._cache_timestamps = {
            k: time.time() for k in ConfigRegistry._cache
        }

        result = ConfigRegistry.get_section("redis")
        assert result == {
            "host": "172.16.168.23",
            "port": "6379",
            "database": "0",
        }

    def test_get_section_returns_empty_for_no_matches(self):
        """Test that get_section returns empty dict when no keys match."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        ConfigRegistry._cache = {
            "redis.host": "172.16.168.23",
        }
        ConfigRegistry._cache_timestamps = {
            k: time.time() for k in ConfigRegistry._cache
        }

        result = ConfigRegistry.get_section("nonexistent")
        assert result == {}

    def test_set_updates_cache(self):
        """Test that set() updates the local cache."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        # Mock Redis to avoid actual connection
        with patch.object(ConfigRegistry, "_get_redis", return_value=None):
            result = ConfigRegistry.set("test.key", "test_value")

        assert result is True
        assert ConfigRegistry._cache["test.key"] == "test_value"
        assert "test.key" in ConfigRegistry._cache_timestamps

    def test_set_stores_in_redis(self):
        """Test that set() stores value in Redis."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        mock_redis = MagicMock()
        with patch.object(ConfigRegistry, "_get_redis", return_value=mock_redis):
            result = ConfigRegistry.set("redis.host", "10.0.0.1")

        assert result is True
        mock_redis.set.assert_called_once_with("autobot:config:redis.host", "10.0.0.1")

    def test_set_returns_false_on_redis_error(self):
        """Test that set() returns False but still caches on Redis error."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        mock_redis = MagicMock()
        mock_redis.set.side_effect = Exception("Connection failed")
        with patch.object(ConfigRegistry, "_get_redis", return_value=mock_redis):
            result = ConfigRegistry.set("fail.key", "value")

        assert result is False
        # Value should still be cached locally
        assert ConfigRegistry._cache["fail.key"] == "value"

    def test_refresh_bypasses_cache(self):
        """Test that refresh() bypasses cache and fetches fresh from Redis."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        # Pre-populate cache with old value
        ConfigRegistry._cache["refresh.key"] = "old_value"
        ConfigRegistry._cache_timestamps["refresh.key"] = time.time()

        with patch.object(
            ConfigRegistry, "_fetch_from_redis", return_value="new_value"
        ) as mock_fetch:
            result = ConfigRegistry.refresh("refresh.key")

        assert result == "new_value"
        mock_fetch.assert_called_once()

    def test_refresh_clears_cache_entry(self):
        """Test that refresh() clears the cache entry before fetching."""
        from src.config.registry import ConfigRegistry

        ConfigRegistry.clear_cache()

        ConfigRegistry._cache["clear.key"] = "cached"
        ConfigRegistry._cache_timestamps["clear.key"] = time.time()

        with patch.object(ConfigRegistry, "_fetch_from_redis", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                ConfigRegistry.refresh("clear.key")

        # After refresh with no Redis value and no env, key should not be in cache
        # (since we don't cache defaults)
        assert "clear.key" not in ConfigRegistry._cache
