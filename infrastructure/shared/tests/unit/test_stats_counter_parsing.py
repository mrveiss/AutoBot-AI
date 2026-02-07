# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit Tests for StatsMixin._get_all_stats() - Issue #428 Fix

Tests that the _get_all_stats() method correctly handles:
1. Integer counter fields (total_facts, total_vectors, etc.)
2. Metadata fields with timestamp strings (initialized_at, last_corrected)
3. Edge cases with malformed data

The fix ensures timestamp strings don't cause int() parsing failures.
"""

from unittest.mock import AsyncMock

import pytest


class TestStatsCounterParsing:
    """Test suite for Issue #428 - Stats counters parsing fix."""

    @pytest.fixture
    def stats_mixin_instance(self):
        """Create a minimal StatsMixin instance for testing."""
        from src.knowledge.stats import StatsMixin

        # Create a simple class that inherits from StatsMixin for testing
        class TestStats(StatsMixin):
            def __init__(self):
                self.aioredis_client = AsyncMock()
                self._stats_key = "kb:stats"  # Required by _get_all_stats()

        instance = TestStats()
        return instance

    @pytest.mark.asyncio
    async def test_get_all_stats_skips_metadata_fields(self, stats_mixin_instance):
        """Test that metadata fields (initialized_at, last_corrected) are skipped."""
        # Mock Redis response with mixed counter and metadata fields
        stats_mixin_instance.aioredis_client.hgetall = AsyncMock(
            return_value={
                b"total_facts": b"100",
                b"total_vectors": b"50",
                b"total_documents": b"50",
                b"total_chunks": b"50",
                b"initialized_at": b"2025-11-29T22:37:42.891176",
                b"last_corrected": b"2025-12-01T10:00:00.000000",
            }
        )

        result = await stats_mixin_instance._get_all_stats()

        # Should have counter fields but NOT metadata fields
        assert "total_facts" in result
        assert "total_vectors" in result
        assert result["total_facts"] == 100
        assert result["total_vectors"] == 50

        # Metadata fields should be excluded
        assert "initialized_at" not in result
        assert "last_corrected" not in result

    @pytest.mark.asyncio
    async def test_get_all_stats_handles_string_keys(self, stats_mixin_instance):
        """Test that string keys (not bytes) are also handled correctly."""
        # Mock Redis response with string keys
        stats_mixin_instance.aioredis_client.hgetall = AsyncMock(
            return_value={
                "total_facts": "200",
                "total_vectors": "75",
                "initialized_at": "2025-11-29T22:37:42.891176",
            }
        )

        result = await stats_mixin_instance._get_all_stats()

        assert result["total_facts"] == 200
        assert result["total_vectors"] == 75
        assert "initialized_at" not in result

    @pytest.mark.asyncio
    async def test_get_all_stats_handles_invalid_integer_values(
        self, stats_mixin_instance, caplog
    ):
        """Test that invalid integer values are logged and skipped."""
        # Mock Redis response with an unexpected non-integer value
        stats_mixin_instance.aioredis_client.hgetall = AsyncMock(
            return_value={
                b"total_facts": b"100",
                b"unknown_field": b"not_an_integer",
            }
        )

        import logging

        with caplog.at_level(logging.WARNING):
            result = await stats_mixin_instance._get_all_stats()

        # Valid counter should be present
        assert result["total_facts"] == 100

        # Invalid field should be skipped
        assert "unknown_field" not in result

        # Warning should be logged
        assert "non-integer value" in caplog.text

    @pytest.mark.asyncio
    async def test_get_all_stats_returns_empty_dict_on_error(
        self, stats_mixin_instance
    ):
        """Test that an empty dict is returned when Redis fails."""
        stats_mixin_instance.aioredis_client.hgetall = AsyncMock(
            side_effect=Exception("Redis connection failed")
        )

        result = await stats_mixin_instance._get_all_stats()

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_all_stats_returns_empty_dict_without_client(self):
        """Test that an empty dict is returned when aioredis_client is None."""
        from src.knowledge.stats import StatsMixin

        instance = object.__new__(StatsMixin)
        instance.aioredis_client = None

        result = await instance._get_all_stats()

        assert result == {}

    @pytest.mark.asyncio
    async def test_metadata_fields_frozenset_is_correct(self):
        """Test that _METADATA_FIELDS contains expected values."""
        from src.knowledge.stats import StatsMixin

        assert "initialized_at" in StatsMixin._METADATA_FIELDS
        assert "last_corrected" in StatsMixin._METADATA_FIELDS
        assert len(StatsMixin._METADATA_FIELDS) == 2
