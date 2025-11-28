"""
Unit tests for MCP Registry Caching (Issue #50)

Tests the MCPToolCache class for proper TTL behavior, hit/miss tracking,
and invalidation logic.
"""

import time
from datetime import datetime, timedelta

import pytest

# Import cache class (will be monkeypatched for testing)
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestMCPToolCache:
    """Test MCPToolCache class functionality"""

    @pytest.fixture
    def cache(self):
        """Create fresh cache instance for each test"""
        # Import here to avoid module-level import issues
        from backend.api.mcp_registry import MCPToolCache
        return MCPToolCache(ttl_seconds=2)  # Short TTL for testing

    @pytest.fixture
    def sample_tools_data(self):
        """Sample tools response"""
        return {
            "status": "success",
            "total_tools": 25,
            "total_bridges": 5,
            "healthy_bridges": 5,
            "tools": [
                {
                    "name": "search_knowledge_base",
                    "description": "Search knowledge base",
                    "bridge": "knowledge_mcp",
                }
            ],
            "last_updated": datetime.now().isoformat(),
            "cached": False,
        }

    @pytest.fixture
    def sample_bridges_data(self):
        """Sample bridges response"""
        return {
            "status": "success",
            "total_bridges": 5,
            "healthy_bridges": 5,
            "bridges": [
                {
                    "name": "knowledge_mcp",
                    "status": "healthy",
                    "tool_count": 7,
                }
            ],
            "last_checked": datetime.now().isoformat(),
            "cached": False,
        }

    def test_cache_initially_empty(self, cache):
        """Test that cache starts empty"""
        assert cache.get_tools() is None
        assert cache.get_bridges() is None

    def test_set_and_get_tools(self, cache, sample_tools_data):
        """Test setting and getting tools cache"""
        cache.set_tools(sample_tools_data)
        cached = cache.get_tools()

        assert cached is not None
        assert cached["total_tools"] == 25
        assert cached["total_bridges"] == 5

    def test_set_and_get_bridges(self, cache, sample_bridges_data):
        """Test setting and getting bridges cache"""
        cache.set_bridges(sample_bridges_data)
        cached = cache.get_bridges()

        assert cached is not None
        assert cached["total_bridges"] == 5
        assert cached["healthy_bridges"] == 5

    def test_cache_expiration(self, cache, sample_tools_data):
        """Test that cache expires after TTL"""
        cache.set_tools(sample_tools_data)

        # Should be cached
        assert cache.get_tools() is not None

        # Wait for TTL to expire (2 seconds)
        time.sleep(2.1)

        # Should be expired
        assert cache.get_tools() is None

    def test_cache_hit_tracking(self, cache, sample_tools_data):
        """Test that cache hits are tracked"""
        cache.set_tools(sample_tools_data)

        # Get cached data multiple times
        cache.get_tools()
        cache.get_tools()
        cache.get_tools()

        stats = cache.get_stats()
        assert stats["cache_hits"] >= 3

    def test_cache_miss_tracking(self, cache):
        """Test that cache misses are tracked"""
        # Get from empty cache
        cache.get_tools()
        cache.get_bridges()

        stats = cache.get_stats()
        assert stats["cache_misses"] >= 2

    def test_cache_invalidation(self, cache, sample_tools_data, sample_bridges_data):
        """Test cache invalidation clears all data"""
        cache.set_tools(sample_tools_data)
        cache.set_bridges(sample_bridges_data)

        # Both should be cached
        assert cache.get_tools() is not None
        assert cache.get_bridges() is not None

        # Invalidate
        cache.invalidate_all()

        # Both should be cleared
        # Note: get_tools returns None but also increments miss counter
        stats_before = cache.get_stats()
        miss_before = stats_before["cache_misses"]

        cached_tools = cache.get_tools()
        cached_bridges = cache.get_bridges()

        assert cached_tools is None
        assert cached_bridges is None

        stats_after = cache.get_stats()
        assert stats_after["invalidations"] == 1
        # Should have 2 more misses
        assert stats_after["cache_misses"] == miss_before + 2

    def test_cache_hit_rate_calculation(self, cache, sample_tools_data):
        """Test hit rate percentage calculation"""
        # 1 miss (empty cache)
        cache.get_tools()

        # Set cache
        cache.set_tools(sample_tools_data)

        # 3 hits
        cache.get_tools()
        cache.get_tools()
        cache.get_tools()

        stats = cache.get_stats()
        # 3 hits out of 4 total = 75%
        assert stats["hit_rate_percent"] == 75.0

    def test_cache_age_tracking(self, cache, sample_tools_data):
        """Test cache age is tracked correctly"""
        cache.set_tools(sample_tools_data)
        time.sleep(0.5)  # Wait 500ms

        stats = cache.get_stats()
        assert stats["tools_cached"] is True
        # Age should be around 0.5 seconds
        assert 0.4 <= stats["tools_cache_age_seconds"] <= 1.0

    def test_separate_tools_and_bridges_caches(self, cache, sample_tools_data, sample_bridges_data):
        """Test that tools and bridges have independent caches"""
        cache.set_tools(sample_tools_data)
        # Only tools should be cached
        assert cache.get_tools() is not None
        assert cache.get_bridges() is None

        cache.set_bridges(sample_bridges_data)
        # Both should be cached now
        assert cache.get_tools() is not None
        assert cache.get_bridges() is not None

    def test_cache_returns_same_data(self, cache, sample_tools_data):
        """Test that cached data matches original data"""
        original_tools = sample_tools_data.copy()
        cache.set_tools(sample_tools_data)
        cached = cache.get_tools()

        assert cached["total_tools"] == original_tools["total_tools"]
        assert cached["total_bridges"] == original_tools["total_bridges"]
        assert cached["healthy_bridges"] == original_tools["healthy_bridges"]

    def test_multiple_invalidations(self, cache, sample_tools_data):
        """Test multiple invalidations increment counter"""
        cache.set_tools(sample_tools_data)
        cache.invalidate_all()
        cache.invalidate_all()
        cache.invalidate_all()

        stats = cache.get_stats()
        assert stats["invalidations"] == 3

    def test_stats_when_cache_empty(self, cache):
        """Test stats report correctly when cache is empty"""
        stats = cache.get_stats()
        assert stats["tools_cached"] is False
        assert stats["bridges_cached"] is False
        assert stats["tools_cache_age_seconds"] is None
        assert stats["bridges_cache_age_seconds"] is None

    def test_ttl_configuration(self):
        """Test that TTL can be configured"""
        from backend.api.mcp_registry import MCPToolCache

        cache_short = MCPToolCache(ttl_seconds=10)
        cache_long = MCPToolCache(ttl_seconds=300)

        assert cache_short.ttl == timedelta(seconds=10)
        assert cache_long.ttl == timedelta(seconds=300)


class TestMCPCacheDisabled:
    """Test cache behavior when disabled via environment variable"""

    @pytest.fixture
    def disabled_cache(self):
        """Create cache with disabled caching"""
        # Temporarily patch the CACHE_ENABLED flag
        from backend.api import mcp_registry
        original_value = mcp_registry.CACHE_ENABLED
        mcp_registry.CACHE_ENABLED = False

        cache = mcp_registry.MCPToolCache(ttl_seconds=60)
        yield cache

        # Restore
        mcp_registry.CACHE_ENABLED = original_value

    @pytest.fixture
    def sample_tools_data(self):
        """Sample tools response"""
        return {
            "status": "success",
            "total_tools": 25,
            "total_bridges": 5,
            "healthy_bridges": 5,
            "tools": [],
            "last_updated": datetime.now().isoformat(),
            "cached": False,
        }

    def test_cache_returns_none_when_disabled(self, disabled_cache, sample_tools_data):
        """Test that cache always returns None when disabled"""
        disabled_cache.set_tools(sample_tools_data)
        # Should return None even after setting
        assert disabled_cache.get_tools() is None

    def test_cache_doesnt_store_when_disabled(self, disabled_cache, sample_tools_data):
        """Test that cache doesn't store data when disabled"""
        disabled_cache.set_tools(sample_tools_data)
        # Internal cache should still be None
        assert disabled_cache._tools_cache is None


class TestMCPCacheIntegration:
    """Integration tests for cache with actual endpoints"""

    @pytest.fixture
    def mock_cache_enabled(self, monkeypatch):
        """Ensure cache is enabled for tests"""
        monkeypatch.setenv("MCP_REGISTRY_CACHE_ENABLED", "true")
        monkeypatch.setenv("MCP_REGISTRY_CACHE_TTL", "60")

    def test_environment_variable_loading(self):
        """Test that environment variables are loaded correctly"""
        from backend.api import mcp_registry

        # Check default values are reasonable
        assert mcp_registry.CACHE_TTL_SECONDS == 60  # Default
        assert isinstance(mcp_registry.CACHE_ENABLED, bool)

    def test_global_cache_instance_exists(self):
        """Test that global cache instance is created"""
        from backend.api.mcp_registry import mcp_cache

        assert mcp_cache is not None
        assert hasattr(mcp_cache, "get_tools")
        assert hasattr(mcp_cache, "get_bridges")
        assert hasattr(mcp_cache, "invalidate_all")


class TestMCPCacheEdgeCases:
    """Edge case tests for cache behavior"""

    @pytest.fixture
    def cache(self):
        """Create fresh cache instance"""
        from backend.api.mcp_registry import MCPToolCache
        return MCPToolCache(ttl_seconds=5)

    def test_zero_hit_rate_when_no_requests(self, cache):
        """Test hit rate is 0 when no requests made"""
        stats = cache.get_stats()
        assert stats["hit_rate_percent"] == 0

    def test_hundred_percent_hit_rate(self, cache):
        """Test 100% hit rate when all requests hit cache"""
        sample = {"data": "test", "cached": False}
        cache.set_tools(sample)

        # Only hits, no misses
        cache.get_tools()
        cache.get_tools()
        cache.get_tools()

        stats = cache.get_stats()
        assert stats["hit_rate_percent"] == 100.0

    def test_empty_data_can_be_cached(self, cache):
        """Test that empty response can be cached"""
        empty_response = {
            "status": "success",
            "total_tools": 0,
            "total_bridges": 0,
            "healthy_bridges": 0,
            "tools": [],
            "last_updated": datetime.now().isoformat(),
            "cached": False,
        }
        cache.set_tools(empty_response)
        cached = cache.get_tools()

        assert cached is not None
        assert cached["total_tools"] == 0

    def test_large_data_can_be_cached(self, cache):
        """Test that large response can be cached"""
        large_response = {
            "status": "success",
            "total_tools": 1000,
            "tools": [{"name": f"tool_{i}"} for i in range(1000)],
            "cached": False,
        }
        cache.set_tools(large_response)
        cached = cache.get_tools()

        assert cached is not None
        assert cached["total_tools"] == 1000
        assert len(cached["tools"]) == 1000
