# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for HybridVectorSearch AsyncInitializable migration (#3390).

Verifies lazy-init, idempotency, and that FAISS/GPU init happens inside
_initialize_impl rather than __init__.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


class TestHybridVectorSearchLazyInit:
    """HybridVectorSearch should not initialise FAISS at construction time."""

    def setup_method(self):
        import utils.gpu_vector_search as mod

        mod._hybrid_search = None

    def teardown_method(self):
        import utils.gpu_vector_search as mod

        mod._hybrid_search = None

    @pytest.mark.asyncio
    async def test_not_initialized_at_construction(self):
        from utils.gpu_vector_search import HybridVectorSearch

        hs = HybridVectorSearch()
        assert not hs.is_initialized
        # gpu_index should exist but not yet have a FAISS index built
        assert hs.gpu_index is not None

    @pytest.mark.asyncio
    async def test_initializes_on_first_call(self):
        from utils.gpu_vector_search import HybridVectorSearch

        hs = HybridVectorSearch()

        with patch.object(hs.gpu_index, "initialize", new_callable=AsyncMock, return_value=True):
            result = await hs.initialize()

        assert result is True
        assert hs.is_initialized

    @pytest.mark.asyncio
    async def test_idempotent_initialize(self):
        from utils.gpu_vector_search import HybridVectorSearch

        hs = HybridVectorSearch()
        init_call_count = 0

        original_impl = hs._initialize_impl

        async def _counted_impl():
            nonlocal init_call_count
            init_call_count += 1
            return await original_impl()

        hs._initialize_impl = _counted_impl

        with patch.object(hs.gpu_index, "initialize", new_callable=AsyncMock, return_value=False):
            r1 = await hs.initialize()
            r2 = await hs.initialize()
            r3 = await hs.initialize()

        assert r1 is r2 is r3 is True
        assert init_call_count == 1  # _initialize_impl called only once

    @pytest.mark.asyncio
    async def test_concurrent_initialize_safe(self):
        from utils.gpu_vector_search import HybridVectorSearch

        hs = HybridVectorSearch()

        with patch.object(hs.gpu_index, "initialize", new_callable=AsyncMock, return_value=False):
            results = await asyncio.gather(*[hs.initialize() for _ in range(6)])

        assert all(r is True for r in results)
        assert hs.is_initialized

    @pytest.mark.asyncio
    async def test_get_hybrid_vector_search_returns_initialized(self):
        from utils.gpu_vector_search import get_hybrid_vector_search

        with patch(
            "utils.gpu_vector_search.GPUVectorIndex.initialize",
            new_callable=AsyncMock,
            return_value=False,
        ):
            hs = await get_hybrid_vector_search()

        assert hs.is_initialized

    @pytest.mark.asyncio
    async def test_get_hybrid_vector_search_singleton(self):
        from utils.gpu_vector_search import get_hybrid_vector_search

        with patch(
            "utils.gpu_vector_search.GPUVectorIndex.initialize",
            new_callable=AsyncMock,
            return_value=False,
        ):
            hs1 = await get_hybrid_vector_search()
            hs2 = await get_hybrid_vector_search()

        assert hs1 is hs2

    @pytest.mark.asyncio
    async def test_chromadb_fallback_logged_when_faiss_unavailable(self, caplog):
        import logging

        from utils.gpu_vector_search import HybridVectorSearch

        hs = HybridVectorSearch()

        with patch.object(hs.gpu_index, "initialize", new_callable=AsyncMock, return_value=False):
            with caplog.at_level(logging.INFO, logger="utils.gpu_vector_search"):
                await hs.initialize()

        assert any("fallback" in msg.lower() or "chromadb" in msg.lower() for msg in caplog.messages)
