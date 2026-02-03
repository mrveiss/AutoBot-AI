# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM client service discovery."""

import os
import time
from unittest.mock import patch

import pytest

from backend.services.slm_client import (
    ENV_VAR_MAP,
    ServiceDiscoveryCache,
    ServiceNotConfiguredError,
    _discovery_cache,
    discover_service,
)


class TestServiceDiscoveryCache:
    """Test ServiceDiscoveryCache class."""

    def test_cache_miss_returns_none(self):
        """Cache returns None for unknown service."""
        cache = ServiceDiscoveryCache(ttl_seconds=60)
        assert cache.get("unknown-service") is None

    def test_cache_hit_returns_url(self):
        """Cache returns URL for known service."""
        cache = ServiceDiscoveryCache(ttl_seconds=60)
        cache.set("redis", {"url": "http://172.16.168.23:6379", "healthy": True})
        result = cache.get("redis")
        assert result == "http://172.16.168.23:6379"

    def test_cache_expires_after_ttl(self):
        """Cache entry expires after TTL."""
        cache = ServiceDiscoveryCache(ttl_seconds=1)
        cache.set("redis", {"url": "http://172.16.168.23:6379", "healthy": True})
        time.sleep(1.1)
        assert cache.get("redis") is None


class TestDiscoverService:
    """Test discover_service function."""

    @pytest.mark.asyncio
    async def test_discover_service_from_cache(self):
        """Returns URL from cache when available."""
        _discovery_cache.set("test-service", {"url": "http://cached:8080"})
        try:
            url = await discover_service("test-service")
            assert url == "http://cached:8080"
        finally:
            _discovery_cache.clear()

    @pytest.mark.asyncio
    async def test_discover_service_env_fallback(self):
        """Falls back to env var when SLM unavailable."""
        _discovery_cache.clear()
        with patch("backend.services.slm_client.get_slm_client", return_value=None):
            with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379"}):
                url = await discover_service("redis")
                assert url == "redis://localhost:6379"

    @pytest.mark.asyncio
    async def test_discover_service_raises_when_not_configured(self):
        """Raises error when service not configured anywhere."""
        _discovery_cache.clear()
        with patch("backend.services.slm_client.get_slm_client", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(ServiceNotConfiguredError):
                    await discover_service("unknown-service")


class TestEnvVarMap:
    """Test ENV_VAR_MAP constant."""

    def test_env_var_map_contains_required_services(self):
        """ENV_VAR_MAP has all required service mappings."""
        required = ["redis", "ollama", "slm-server", "autobot-backend"]
        for service in required:
            assert service in ENV_VAR_MAP, f"Missing {service} in ENV_VAR_MAP"
