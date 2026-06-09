# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Fallback Manager

Issue #4342: Fallback chains for critical paths.
Primary → secondary → minimal-feature mode.
"""

import asyncio

import pytest

from services.resilience.fallback_manager import (
    FallbackChain,
    FallbackManager,
)


class TestFallbackChain:
    """Test suite for fallback chain."""

    def test_single_fallback_success(self):
        """Test single fallback succeeds."""
        chain = FallbackChain("search")
        chain.add("primary", lambda: {"results": []})

        result = chain.execute()
        assert result == {"results": []}

    def test_primary_fails_uses_secondary(self):
        """Test that secondary fallback is used when primary fails."""
        chain = FallbackChain("search")
        chain.add("primary", lambda: (_ for _ in ()).throw(RuntimeError("Primary down")))
        chain.add("secondary", lambda: {"cached": True})

        result = chain.execute()
        assert result == {"cached": True}

    def test_all_fallbacks_fail_raises_error(self):
        """Test that error is raised when all fallbacks fail."""
        chain = FallbackChain("search")
        chain.add("primary", lambda: (_ for _ in ()).throw(RuntimeError("Primary down")))
        chain.add("secondary", lambda: (_ for _ in ()).throw(RuntimeError("Secondary down")))

        with pytest.raises(RuntimeError, match="All fallbacks exhausted"):
            chain.execute()

    def test_fallback_chain_with_args(self):
        """Test fallback chain with arguments."""
        chain = FallbackChain("fetch_user")
        chain.add("db", lambda uid: {"id": uid, "cached": False})
        chain.add("cache", lambda uid: {"id": uid, "cached": True})

        result = chain.execute(123)
        assert result["id"] == 123

    def test_fallback_chain_order_matters(self):
        """Test that fallback chain tries in order."""
        calls = []

        def primary():
            calls.append("primary")
            raise RuntimeError("Primary failed")

        def secondary():
            calls.append("secondary")
            return "secondary_result"

        chain = FallbackChain("fetch")
        chain.add("primary", primary)
        chain.add("secondary", secondary)

        result = chain.execute()
        assert calls == ["primary", "secondary"]
        assert result == "secondary_result"

    def test_fallback_chain_statistics(self):
        """Test fallback chain statistics."""
        chain = FallbackChain("fetch")
        chain.add("primary", lambda: (_ for _ in ()).throw(RuntimeError()))
        chain.add("secondary", lambda: "result")

        chain.execute()
        assert chain.attempted == 2
        assert chain.succeeded is True

    @pytest.mark.asyncio
    async def test_async_fallback_chain(self):
        """Test async fallback chain."""

        async def primary():
            await asyncio.sleep(0.01)
            raise RuntimeError("Primary down")

        async def secondary():
            await asyncio.sleep(0.01)
            return "async_result"

        chain = FallbackChain("async_fetch")
        chain.add("primary", primary, is_async=True)
        chain.add("secondary", secondary, is_async=True)

        result = await chain.execute_async()
        assert result == "async_result"

    @pytest.mark.asyncio
    async def test_mixed_sync_async_fallbacks(self):
        """Test chain with both sync and async fallbacks."""

        def sync_fallback():
            return "sync_result"

        async def async_fallback():
            await asyncio.sleep(0.01)
            return "async_result"

        chain = FallbackChain("mixed")
        chain.add("primary", lambda: (_ for _ in ()).throw(RuntimeError()))
        chain.add("secondary", sync_fallback)
        chain.add("tertiary", async_fallback, is_async=True)

        result = await chain.execute_async()
        assert result == "sync_result"  # Secondary succeeds


class TestFallbackManager:
    """Test suite for fallback manager."""

    def test_manager_creates_chain(self):
        """Test that manager creates new chain."""
        manager = FallbackManager()
        chain = manager.create_chain("search")

        assert chain is not None
        assert chain.name == "search"

    def test_manager_retrieves_chain(self):
        """Test that manager retrieves existing chain."""
        manager = FallbackManager()
        chain1 = manager.create_chain("search")
        chain2 = manager.get_chain("search")

        assert chain1 is chain2

    def test_manager_duplicate_chain_raises(self):
        """Test that creating duplicate chain raises error."""
        manager = FallbackManager()
        manager.create_chain("search")

        with pytest.raises(ValueError, match="already exists"):
            manager.create_chain("search")

    def test_manager_execute_chain(self):
        """Test executing chain through manager."""
        manager = FallbackManager()
        chain = manager.create_chain("fetch")
        chain.add("primary", lambda: (_ for _ in ()).throw(RuntimeError()))
        chain.add("secondary", lambda: "fallback")

        result = manager.execute("fetch")
        assert result == "fallback"

    def test_manager_execute_nonexistent_chain(self):
        """Test executing nonexistent chain raises error."""
        manager = FallbackManager()

        with pytest.raises(ValueError, match="not found"):
            manager.execute("nonexistent")

    def test_manager_tracks_multiple_chains(self):
        """Test manager tracks multiple chains."""
        manager = FallbackManager()

        chain1 = manager.create_chain("search")
        chain1.add("primary", lambda: "search_result")

        chain2 = manager.create_chain("fetch")
        chain2.add("primary", lambda: "fetch_result")

        result1 = manager.execute("search")
        result2 = manager.execute("fetch")

        assert result1 == "search_result"
        assert result2 == "fetch_result"

    def test_manager_status(self):
        """Test manager status report."""
        manager = FallbackManager()
        chain = manager.create_chain("search")
        chain.add("primary", lambda: "result")

        status = manager.get_status()
        assert "search" in status
        assert status["search"]["fallback_count"] == 1

    @pytest.mark.asyncio
    async def test_manager_async_execute(self):
        """Test executing async chain through manager."""
        manager = FallbackManager()
        chain = manager.create_chain("fetch")
        chain.add("primary", lambda: (_ for _ in ()).throw(RuntimeError()))

        async def secondary():
            await asyncio.sleep(0.01)
            return "async_fallback"

        chain.add("secondary", secondary, is_async=True)

        result = await manager.execute_async("fetch")
        assert result == "async_fallback"


class TestGracefulDegradation:
    """Test graceful degradation with fallback chains."""

    def test_search_degradation_to_cache(self):
        """Test search degrades to cached results."""
        manager = FallbackManager()
        chain = manager.create_chain("search")

        # Primary: live search
        def live_search(query):
            raise RuntimeError("Search service down")

        # Secondary: cached results
        def cached_search(query):
            return {"cached": True, "results": []}

        chain.add("live", live_search)
        chain.add("cached", cached_search)

        result = manager.execute("search", "test query")
        assert result["cached"] is True

    def test_database_degradation(self):
        """Test database query degradation."""
        manager = FallbackManager()
        chain = manager.create_chain("fetch_user")

        # Primary: database
        def fetch_from_db(user_id):
            raise RuntimeError("Database down")

        # Secondary: cache
        def fetch_from_cache(user_id):
            return {"id": user_id, "name": "cached_user"}

        # Tertiary: minimal data
        def minimal_user_data(user_id):
            return {"id": user_id}

        chain.add("db", fetch_from_db)
        chain.add("cache", fetch_from_cache)
        chain.add("minimal", minimal_user_data)

        result = manager.execute("fetch_user", 123)
        assert result == {"id": 123, "name": "cached_user"}

    def test_all_fallbacks_exhausted_graceful_error(self):
        """Test that exhausting all fallbacks provides graceful error."""
        manager = FallbackManager()
        chain = manager.create_chain("operation")

        chain.add("primary", lambda: (_ for _ in ()).throw(RuntimeError()))
        chain.add("secondary", lambda: (_ for _ in ()).throw(RuntimeError()))

        with pytest.raises(RuntimeError):
            manager.execute("operation")


class TestCriticalPaths:
    """Test fallback chains for critical paths."""

    def test_knowledge_retrieval_fallback(self):
        """Test knowledge retrieval with fallback."""
        manager = FallbackManager()
        chain = manager.create_chain("knowledge")

        # Primary: ChromaDB
        def search_chromadb(query):
            raise RuntimeError("ChromaDB timeout")

        # Secondary: Redis cache
        def search_redis(query):
            return {"source": "cache", "results": []}

        chain.add("chromadb", search_chromadb)
        chain.add("redis", search_redis)

        result = manager.execute("knowledge", "test")
        assert result["source"] == "cache"

    def test_agent_execution_fallback(self):
        """Test agent execution with fallback."""
        manager = FallbackManager()
        chain = manager.create_chain("agent")

        # Primary: full agent
        def run_full_agent():
            raise RuntimeError("Agent framework down")

        # Secondary: simple execution
        def run_simple():
            return {"mode": "simple", "output": ""}

        chain.add("full", run_full_agent)
        chain.add("simple", run_simple)

        result = manager.execute("agent")
        assert result["mode"] == "simple"

    def test_skill_execution_fallback(self):
        """Test skill execution with fallback."""
        manager = FallbackManager()
        chain = manager.create_chain("skill")

        # Primary: execute skill
        def execute_skill():
            raise RuntimeError("Skill failed")

        # Secondary: return empty result
        def empty_result():
            return {"status": "skipped", "data": None}

        chain.add("execute", execute_skill)
        chain.add("empty", empty_result)

        result = manager.execute("skill")
        assert result["status"] == "skipped"
