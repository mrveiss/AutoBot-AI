# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM client service discovery."""

import time

from backend.services.slm_client import ServiceDiscoveryCache


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
