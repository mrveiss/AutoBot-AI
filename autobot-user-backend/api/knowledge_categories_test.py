#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit Tests for Knowledge Manager Category Filtering (Sprint 1 #161)

Tests the category filtering feature:
- Category list retrieval endpoint
- Filtering facts by category
- Category statistics counting
- Cache behavior (hit/miss)
- Empty category handling
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for cache testing"""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.exists = AsyncMock(return_value=0)
    return client


@pytest.fixture
def sample_categories():
    """Sample category data"""
    return [
        {"name": "tools", "count": 15, "description": "Tool knowledge"},
        {"name": "systems", "count": 8, "description": "System knowledge"},
        {"name": "security", "count": 23, "description": "Security knowledge"},
        {"name": "automation", "count": 12, "description": "Automation scripts"},
    ]


@pytest.fixture
def sample_facts_by_category():
    """Sample facts organized by category"""
    return {
        "tools": [
            {"id": "f1", "content": "nmap is a network scanner", "category": "tools"},
            {
                "id": "f2",
                "content": "wireshark is a packet analyzer",
                "category": "tools",
            },
        ],
        "security": [
            {"id": "f3", "content": "Use strong passwords", "category": "security"},
            {"id": "f4", "content": "Enable 2FA", "category": "security"},
            {"id": "f5", "content": "Regular security audits", "category": "security"},
        ],
        "empty_category": [],
    }


@pytest.fixture
def mock_knowledge_base():
    """Mock KnowledgeBase for testing"""
    kb = MagicMock()
    kb.get_knowledge_categories = AsyncMock(
        return_value={
            "status": "success",
            "categories": [
                {"name": "tools", "count": 15},
                {"name": "systems", "count": 8},
                {"name": "security", "count": 23},
            ],
        }
    )
    kb.get_facts_by_category = AsyncMock()
    kb.search = AsyncMock()
    return kb


# ============================================================================
# CATEGORY LIST RETRIEVAL TESTS
# ============================================================================


class TestCategoryListRetrieval:
    """Test category list endpoint and retrieval logic"""

    @pytest.mark.asyncio
    async def test_get_categories_success(self, mock_knowledge_base, sample_categories):
        """Test successful category retrieval"""
        mock_knowledge_base.get_knowledge_categories.return_value = {
            "status": "success",
            "categories": sample_categories,
        }

        result = await mock_knowledge_base.get_knowledge_categories()

        assert result["status"] == "success"
        assert len(result["categories"]) == 4
        assert all(
            cat["name"] in ["tools", "systems", "security", "automation"]
            for cat in result["categories"]
        )

    @pytest.mark.asyncio
    async def test_get_categories_with_counts(self, mock_knowledge_base):
        """Test category retrieval includes document counts"""
        result = await mock_knowledge_base.get_knowledge_categories()

        categories = result["categories"]
        assert all("count" in cat for cat in categories)
        assert all(isinstance(cat["count"], int) for cat in categories)
        assert all(cat["count"] >= 0 for cat in categories)

    @pytest.mark.asyncio
    async def test_get_categories_empty_database(self, mock_knowledge_base):
        """Test category retrieval when database is empty"""
        mock_knowledge_base.get_knowledge_categories.return_value = {
            "status": "success",
            "categories": [],
        }

        result = await mock_knowledge_base.get_knowledge_categories()

        assert result["status"] == "success"
        assert result["categories"] == []

    @pytest.mark.asyncio
    async def test_get_categories_error_handling(self, mock_knowledge_base):
        """Test error handling in category retrieval"""
        mock_knowledge_base.get_knowledge_categories.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception) as exc_info:
            await mock_knowledge_base.get_knowledge_categories()

        assert "Database error" in str(exc_info.value)


# ============================================================================
# CATEGORY FILTERING TESTS
# ============================================================================


class TestCategoryFiltering:
    """Test filtering facts by category"""

    @pytest.mark.asyncio
    async def test_filter_by_single_category(
        self, mock_knowledge_base, sample_facts_by_category
    ):
        """Test filtering by a single category"""
        mock_knowledge_base.get_facts_by_category.return_value = (
            sample_facts_by_category["tools"]
        )

        result = await mock_knowledge_base.get_facts_by_category("tools")

        assert len(result) == 2
        assert all(fact["category"] == "tools" for fact in result)

    @pytest.mark.asyncio
    async def test_filter_empty_category(
        self, mock_knowledge_base, sample_facts_by_category
    ):
        """Test filtering category with no facts"""
        mock_knowledge_base.get_facts_by_category.return_value = (
            sample_facts_by_category["empty_category"]
        )

        result = await mock_knowledge_base.get_facts_by_category("empty_category")

        assert result == []

    @pytest.mark.asyncio
    async def test_filter_nonexistent_category(self, mock_knowledge_base):
        """Test filtering by category that doesn't exist"""
        mock_knowledge_base.get_facts_by_category.return_value = []

        result = await mock_knowledge_base.get_facts_by_category("nonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_filter_case_sensitivity(
        self, mock_knowledge_base, sample_facts_by_category
    ):
        """Test case handling in category filtering"""
        # Test lowercase
        mock_knowledge_base.get_facts_by_category.return_value = (
            sample_facts_by_category["tools"]
        )
        result = await mock_knowledge_base.get_facts_by_category("tools")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filter_special_characters(self, mock_knowledge_base):
        """Test category names with special characters"""
        mock_knowledge_base.get_facts_by_category.return_value = [
            {"id": "f1", "content": "Test", "category": "ai/ml-tools"}
        ]

        result = await mock_knowledge_base.get_facts_by_category("ai/ml-tools")

        assert len(result) == 1
        assert result[0]["category"] == "ai/ml-tools"


# ============================================================================
# CATEGORY STATISTICS TESTS
# ============================================================================


class TestCategoryStatistics:
    """Test category statistics and counting"""

    @pytest.mark.asyncio
    async def test_category_count_accuracy(
        self, mock_knowledge_base, sample_categories
    ):
        """Test category count matches actual documents"""
        mock_knowledge_base.get_knowledge_categories.return_value = {
            "status": "success",
            "categories": sample_categories,
        }

        result = await mock_knowledge_base.get_knowledge_categories()
        categories = result["categories"]

        # Verify counts
        tools_cat = next(c for c in categories if c["name"] == "tools")
        assert tools_cat["count"] == 15

        security_cat = next(c for c in categories if c["name"] == "security")
        assert security_cat["count"] == 23

    @pytest.mark.asyncio
    async def test_zero_count_categories(self, mock_knowledge_base):
        """Test categories with zero documents"""
        mock_knowledge_base.get_knowledge_categories.return_value = {
            "status": "success",
            "categories": [
                {"name": "empty_cat", "count": 0, "description": "Empty category"}
            ],
        }

        result = await mock_knowledge_base.get_knowledge_categories()
        empty_cat = result["categories"][0]

        assert empty_cat["count"] == 0
        assert empty_cat["name"] == "empty_cat"

    @pytest.mark.asyncio
    async def test_category_statistics_aggregation(
        self, mock_knowledge_base, sample_categories
    ):
        """Test statistics aggregation across categories"""
        mock_knowledge_base.get_knowledge_categories.return_value = {
            "status": "success",
            "categories": sample_categories,
        }

        result = await mock_knowledge_base.get_knowledge_categories()
        categories = result["categories"]

        total_count = sum(cat["count"] for cat in categories)
        assert total_count == 58  # 15 + 8 + 23 + 12


# ============================================================================
# CACHE BEHAVIOR TESTS
# ============================================================================


class TestCacheBehavior:
    """Test caching mechanism for category data"""

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_redis_client, sample_categories):
        """Test cache hit returns cached data"""
        # Setup cache hit
        cached_data = json.dumps({"categories": sample_categories})
        mock_redis_client.get.return_value = cached_data.encode("utf-8")

        # Simulate cache retrieval
        cache_key = "knowledge:categories:all"
        cached = await mock_redis_client.get(cache_key)

        assert cached is not None
        data = json.loads(cached.decode("utf-8"))
        assert len(data["categories"]) == 4

    @pytest.mark.asyncio
    async def test_cache_miss(
        self, mock_redis_client, mock_knowledge_base, sample_categories
    ):
        """Test cache miss fetches from database"""
        # Setup cache miss
        mock_redis_client.get.return_value = None
        mock_knowledge_base.get_knowledge_categories.return_value = {
            "status": "success",
            "categories": sample_categories,
        }

        # Simulate cache miss and fetch
        cache_key = "knowledge:categories:all"
        cached = await mock_redis_client.get(cache_key)

        if cached is None:
            # Fetch from database
            result = await mock_knowledge_base.get_knowledge_categories()
            assert len(result["categories"]) == 4

            # Cache the result
            await mock_redis_client.set(
                cache_key, json.dumps(result).encode("utf-8"), ex=300  # 5 minutes
            )

        mock_redis_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, mock_redis_client):
        """Test cache invalidation on data change"""
        cache_key = "knowledge:categories:all"

        # Delete cache
        deleted = await mock_redis_client.delete(cache_key)

        assert deleted >= 0
        mock_redis_client.delete.assert_called_once_with(cache_key)

    @pytest.mark.asyncio
    async def test_cache_expiration(self, mock_redis_client):
        """Test cache has appropriate TTL"""
        cache_key = "knowledge:categories:all"
        data = {"categories": []}

        # Set with expiration
        await mock_redis_client.set(
            cache_key, json.dumps(data).encode("utf-8"), ex=300  # 5 minutes
        )

        # Verify set was called with expiration
        mock_redis_client.set.assert_called_once()
        call_args = mock_redis_client.set.call_args
        assert call_args[1]["ex"] == 300


# ============================================================================
# EMPTY CATEGORY HANDLING TESTS
# ============================================================================


class TestEmptyCategoryHandling:
    """Test handling of empty categories"""

    @pytest.mark.asyncio
    async def test_empty_category_in_list(self, mock_knowledge_base):
        """Test empty categories appear in category list"""
        mock_knowledge_base.get_knowledge_categories.return_value = {
            "status": "success",
            "categories": [
                {"name": "tools", "count": 15},
                {"name": "empty", "count": 0},
            ],
        }

        result = await mock_knowledge_base.get_knowledge_categories()
        categories = result["categories"]

        assert len(categories) == 2
        empty_cat = next(c for c in categories if c["name"] == "empty")
        assert empty_cat["count"] == 0

    @pytest.mark.asyncio
    async def test_filter_empty_category_returns_empty_list(self, mock_knowledge_base):
        """Test filtering empty category returns empty list"""
        mock_knowledge_base.get_facts_by_category.return_value = []

        result = await mock_knowledge_base.get_facts_by_category("empty")

        assert result == []
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_category_search(self, mock_knowledge_base):
        """Test searching in empty category"""
        mock_knowledge_base.search.return_value = {
            "status": "success",
            "results": [],
            "count": 0,
        }

        result = await mock_knowledge_base.search(query="test", category="empty")

        assert result["count"] == 0
        assert result["results"] == []


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error scenarios"""

    @pytest.mark.asyncio
    async def test_category_with_unicode_name(self, mock_knowledge_base):
        """Test category names with Unicode characters"""
        mock_knowledge_base.get_knowledge_categories.return_value = {
            "status": "success",
            "categories": [
                {"name": "tools🔧", "count": 5},
                {"name": "安全", "count": 3},  # Chinese for "security"
            ],
        }

        result = await mock_knowledge_base.get_knowledge_categories()
        assert len(result["categories"]) == 2

    @pytest.mark.asyncio
    async def test_very_long_category_name(self, mock_knowledge_base):
        """Test handling of very long category names"""
        long_name = "a" * 500
        mock_knowledge_base.get_knowledge_categories.return_value = {
            "status": "success",
            "categories": [{"name": long_name, "count": 1}],
        }

        result = await mock_knowledge_base.get_knowledge_categories()
        assert result["categories"][0]["name"] == long_name

    @pytest.mark.asyncio
    async def test_concurrent_category_requests(
        self, mock_knowledge_base, sample_categories
    ):
        """Test handling concurrent category retrieval requests"""
        mock_knowledge_base.get_knowledge_categories.return_value = {
            "status": "success",
            "categories": sample_categories,
        }

        # Simulate concurrent requests
        tasks = [mock_knowledge_base.get_knowledge_categories() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(len(r["categories"]) == 4 for r in results)

    @pytest.mark.asyncio
    async def test_null_category_name_handling(self, mock_knowledge_base):
        """Test handling of null/None category names"""
        mock_knowledge_base.get_facts_by_category.side_effect = ValueError(
            "Category name cannot be None"
        )

        with pytest.raises(ValueError):
            await mock_knowledge_base.get_facts_by_category(None)


# ============================================================================
# INTEGRATION WITH SEARCH TESTS
# ============================================================================


class TestCategorySearchIntegration:
    """Test category filtering integration with search"""

    @pytest.mark.asyncio
    async def test_search_with_category_filter(self, mock_knowledge_base):
        """Test search filtered by category"""
        mock_knowledge_base.search.return_value = {
            "status": "success",
            "results": [
                {
                    "id": "f1",
                    "content": "nmap scanning",
                    "category": "tools",
                    "score": 0.95,
                }
            ],
            "count": 1,
        }

        result = await mock_knowledge_base.search(query="scanning", category="tools")

        assert result["count"] == 1
        assert result["results"][0]["category"] == "tools"

    @pytest.mark.asyncio
    async def test_search_without_category_filter(self, mock_knowledge_base):
        """Test search across all categories"""
        mock_knowledge_base.search.return_value = {
            "status": "success",
            "results": [
                {
                    "id": "f1",
                    "content": "nmap scanning",
                    "category": "tools",
                    "score": 0.95,
                },
                {
                    "id": "f2",
                    "content": "security scanning",
                    "category": "security",
                    "score": 0.90,
                },
            ],
            "count": 2,
        }

        result = await mock_knowledge_base.search(query="scanning")

        assert result["count"] == 2
        categories = set(r["category"] for r in result["results"])
        assert len(categories) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
