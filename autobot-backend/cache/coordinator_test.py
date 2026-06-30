# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for CacheCoordinator AsyncInitializable migration (#3390).

Verifies lazy-init, idempotency, and singleton reset.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from cache.coordinator import CacheCoordinator, get_cache_coordinator
from cache.protocols import CacheProtocol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_cache(name: str = "test_cache") -> CacheProtocol:
    """Create a CacheProtocol mock."""
    mock = MagicMock(spec=CacheProtocol)
    mock.name = name
    mock.max_size = 100
    mock.size = 10
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCacheCoordinatorAsyncInit:
    """CacheCoordinator inherits AsyncInitializable — verify lazy-init contract."""

    def setup_method(self):
        CacheCoordinator.reset_instance()

    def teardown_method(self):
        CacheCoordinator.reset_instance()

    @pytest.mark.asyncio
    async def test_not_initialized_before_first_call(self):
        coord = CacheCoordinator()
        assert not coord.is_initialized

    @pytest.mark.asyncio
    async def test_initializes_on_first_call(self):
        coord = CacheCoordinator()
        result = await coord.initialize()
        assert result is True
        assert coord.is_initialized

    @pytest.mark.asyncio
    async def test_idempotent_initialize(self):
        coord = CacheCoordinator()
        r1 = await coord.initialize()
        r2 = await coord.initialize()
        r3 = await coord.initialize()
        assert r1 is r2 is r3 is True

    @pytest.mark.asyncio
    async def test_concurrent_initialize_safe(self):
        coord = CacheCoordinator()
        results = await asyncio.gather(*[coord.initialize() for _ in range(8)])
        assert all(r is True for r in results)
        assert coord.is_initialized

    @pytest.mark.asyncio
    async def test_get_cache_coordinator_returns_initialized(self):
        coordinator = await get_cache_coordinator()
        assert coordinator.is_initialized

    @pytest.mark.asyncio
    async def test_get_cache_coordinator_singleton(self):
        c1 = await get_cache_coordinator()
        c2 = await get_cache_coordinator()
        assert c1 is c2

    @pytest.mark.asyncio
    async def test_register_and_unregister_cache(self):
        coord = await get_cache_coordinator()
        mock_cache = _make_mock_cache("my_cache")
        coord.register(mock_cache)
        stats = coord.get_cache_stats()
        assert stats["registered_count"] == 1
        removed = coord.unregister("my_cache")
        assert removed is True
        assert coord.get_cache_stats()["registered_count"] == 0

    @pytest.mark.asyncio
    async def test_pressure_threshold_loaded_from_config(self):
        coord = await get_cache_coordinator()
        # Config provides a float in [0, 1]; just verify it's set
        assert isinstance(coord._pressure_threshold, float)
        assert 0.0 <= coord._pressure_threshold <= 1.0

    def test_reset_clears_singleton(self):
        CacheCoordinator.reset_instance()
        assert CacheCoordinator._instance is None
