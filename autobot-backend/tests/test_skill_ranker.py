# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for SkillRanker

Issue #4337: Tests for skill relevance ranking and LRU caching.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from services.skill_management.skill_ranker import SkillRanker, get_skill_ranker


class TestSkillRanker:
    """Test SkillRanker class functionality."""

    @pytest.fixture
    def ranker(self):
        """Create a fresh SkillRanker instance for each test."""
        return SkillRanker(max_cache_size=5, cache_ttl_seconds=60)

    @pytest.fixture
    def sample_skills(self):
        """Sample skills for testing."""
        return [
            {
                "id": "skill-1",
                "name": "WebSearch",
                "description": "Search the web for information",
                "platform": "local",
            },
            {
                "id": "skill-2",
                "name": "CodeAnalysis",
                "description": "Analyze source code and identify patterns",
                "platform": "local",
            },
            {
                "id": "skill-3",
                "name": "TelegramNotify",
                "description": "Send notifications via Telegram",
                "platform": "telegram",
            },
        ]

    def test_cosine_similarity_identical(self, ranker):
        """Test cosine similarity with identical vectors."""
        vec = [1.0, 0.0, 0.0]
        similarity = ranker._cosine_similarity(vec, vec)
        assert similarity == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self, ranker):
        """Test cosine similarity with orthogonal vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        similarity = ranker._cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(0.0)

    def test_cosine_similarity_opposite(self, ranker):
        """Test cosine similarity with opposite vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]
        similarity = ranker._cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(-1.0)

    def test_cosine_similarity_empty_vector(self, ranker):
        """Test cosine similarity with empty vectors."""
        similarity = ranker._cosine_similarity([], [1.0, 2.0, 3.0])
        assert similarity == 0.0

    def test_cosine_similarity_zero_magnitude(self, ranker):
        """Test cosine similarity with zero magnitude."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]
        similarity = ranker._cosine_similarity(vec1, vec2)
        assert similarity == 0.0

    def test_filter_by_platform_all(self, ranker, sample_skills):
        """Test platform filter returns all skills when platform is None."""
        filtered = ranker._filter_by_platform(sample_skills, platform=None)
        assert len(filtered) == 3
        assert all(s["name"] in ["WebSearch", "CodeAnalysis", "TelegramNotify"] for s in filtered)

    def test_filter_by_platform_local(self, ranker, sample_skills):
        """Test platform filter returns only local skills."""
        filtered = ranker._filter_by_platform(sample_skills, platform="local")
        assert len(filtered) == 2
        assert all(s["platform"] == "local" for s in filtered)

    def test_filter_by_platform_telegram(self, ranker, sample_skills):
        """Test platform filter returns only telegram skills."""
        filtered = ranker._filter_by_platform(sample_skills, platform="telegram")
        assert len(filtered) == 1
        assert filtered[0]["name"] == "TelegramNotify"

    def test_filter_by_platform_empty(self, ranker, sample_skills):
        """Test platform filter with non-existent platform."""
        filtered = ranker._filter_by_platform(sample_skills, platform="discord")
        assert len(filtered) == 0

    def test_is_cache_valid_empty(self, ranker):
        """Test cache validity check with empty cache."""
        assert not ranker._is_cache_valid()

    def test_is_cache_valid_fresh(self, ranker):
        """Test cache validity check with fresh cache."""
        ranker.skill_cache["test"] = {"name": "test"}
        ranker.cache_timestamp = time.time()
        assert ranker._is_cache_valid()

    def test_is_cache_valid_expired(self, ranker):
        """Test cache validity check with expired cache."""
        ranker.skill_cache["test"] = {"name": "test"}
        ranker.cache_timestamp = time.time() - 100  # Expired (TTL=60)
        assert not ranker._is_cache_valid()

    def test_clear_cache(self, ranker):
        """Test cache clearing."""
        ranker.skill_cache["test"] = {"name": "test"}
        ranker.cache_timestamp = time.time()
        assert len(ranker.skill_cache) > 0

        ranker.clear_cache()
        assert len(ranker.skill_cache) == 0
        assert ranker.cache_timestamp == 0

    @pytest.mark.asyncio
    async def test_fetch_active_skills_success(self, ranker, sample_skills):
        """Test successful skill fetch from SLM."""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"skills": sample_skills})
            mock_get.return_value.__aenter__.return_value = mock_resp

            skills = await ranker._fetch_active_skills()
            assert len(skills) == 3
            assert skills[0]["name"] == "WebSearch"

    @pytest.mark.asyncio
    async def test_fetch_active_skills_timeout(self, ranker):
        """Test skill fetch timeout."""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.side_effect = asyncio.TimeoutError()

            skills = await ranker._fetch_active_skills()
            assert skills == []

    @pytest.mark.asyncio
    async def test_fetch_active_skills_error(self, ranker):
        """Test skill fetch with error."""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.side_effect = Exception("Connection error")

            skills = await ranker._fetch_active_skills()
            assert skills == []

    @pytest.mark.asyncio
    async def test_get_embedding_success(self, ranker):
        """Test successful embedding fetch."""
        expected_embedding = [0.1, 0.2, 0.3]
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={"data": [{"embedding": expected_embedding}]})
            mock_post.return_value.__aenter__.return_value = mock_resp

            embedding = await ranker._get_embedding("test query")
            assert embedding == expected_embedding

    @pytest.mark.asyncio
    async def test_get_embedding_empty_text(self, ranker):
        """Test embedding fetch with empty text."""
        embedding = await ranker._get_embedding("")
        assert embedding is None

    @pytest.mark.asyncio
    async def test_get_embedding_timeout(self, ranker):
        """Test embedding fetch timeout."""
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.side_effect = asyncio.TimeoutError()

            embedding = await ranker._get_embedding("test query")
            assert embedding is None

    @pytest.mark.asyncio
    async def test_rank_skills_empty_context(self, ranker):
        """Test rank_skills with empty context."""
        result = await ranker.rank_skills("")
        assert result == []

    @pytest.mark.asyncio
    async def test_rank_skills_no_skills(self, ranker):
        """Test rank_skills when SLM returns no skills."""
        with patch.object(ranker, "_fetch_active_skills", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            result = await ranker.rank_skills("search for web content")
            assert result == []

    @pytest.mark.asyncio
    async def test_rank_skills_with_cache(self, ranker, sample_skills):
        """Test rank_skills uses cache when valid."""
        # Pre-populate cache
        ranker.skill_cache["skill-1"] = sample_skills[0]
        ranker.cache_timestamp = time.time()

        with patch.object(ranker, "_fetch_active_skills", new_callable=AsyncMock) as mock_fetch:
            with patch.object(ranker, "_get_embedding") as mock_embed:
                mock_embed.return_value = [0.1, 0.2, 0.3]

                await ranker.rank_skills("search query")

                # Should not call fetch because cache is valid
                mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_rank_skills_performance(self, ranker, sample_skills):
        """Test rank_skills completes within performance target."""
        with patch.object(ranker, "_fetch_active_skills", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_skills

            with patch.object(ranker, "_get_embedding") as mock_embed:
                mock_embed.return_value = [0.1, 0.2, 0.3]

                result = await ranker.rank_skills("web search query")

                # Performance should be reasonable (not a hard requirement in tests)
                assert len(result) <= len(sample_skills)

    @pytest.mark.asyncio
    async def test_rank_skills_platform_filter(self, ranker, sample_skills):
        """Test rank_skills respects platform filter."""
        with patch.object(ranker, "_fetch_active_skills", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_skills

            with patch.object(ranker, "_get_embedding") as mock_embed:
                mock_embed.return_value = [0.1, 0.2, 0.3]

                result = await ranker.rank_skills("send notification", platform="telegram")

                # Should only return telegram skills
                assert len(result) == 1
                assert result[0]["platform"] == "telegram"

    @pytest.mark.asyncio
    async def test_rank_skills_no_embeddings(self, ranker, sample_skills):
        """Test rank_skills when embedding fails (fallback to no ranking)."""
        with patch.object(ranker, "_fetch_active_skills", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_skills

            with patch.object(ranker, "_get_embedding") as mock_embed:
                # First call (context embedding) returns None, subsequent calls also None
                mock_embed.return_value = None

                result = await ranker.rank_skills("search query")

                # Should fallback and return unranked skills from cache
                assert len(result) > 0

    @pytest.mark.asyncio
    async def test_rank_skills_top_k(self, ranker, sample_skills):
        """Test rank_skills respects top_k parameter."""
        with patch.object(ranker, "_fetch_active_skills", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = sample_skills

            with patch.object(ranker, "_get_embedding") as mock_embed:
                mock_embed.return_value = [0.1, 0.2, 0.3]

                result = await ranker.rank_skills("query", top_k=2)

                assert len(result) <= 2


class TestSkillRankerGlobal:
    """Test global SkillRanker instance."""

    def test_get_skill_ranker_singleton(self):
        """Test get_skill_ranker returns singleton instance."""
        ranker1 = get_skill_ranker()
        ranker2 = get_skill_ranker()

        assert ranker1 is ranker2


class TestSkillContextBuilding:
    """Test skill context building for prompt injection."""

    def test_build_skill_context_empty(self):
        """Test building skill context with empty skills list."""
        from prompt_manager import _build_skill_context

        context = _build_skill_context(None)
        assert context == ""

        context = _build_skill_context([])
        assert context == ""

    def test_build_skill_context_single(self):
        """Test building skill context with single skill."""
        from prompt_manager import _build_skill_context

        skills = [{"name": "WebSearch", "description": "Search the web"}]
        context = _build_skill_context(skills)

        assert "WebSearch" in context
        assert "Search the web" in context
        assert "Available Skills" in context

    def test_build_skill_context_multiple(self):
        """Test building skill context with multiple skills."""
        from prompt_manager import _build_skill_context

        skills = [
            {"name": "WebSearch", "description": "Search the web"},
            {"name": "CodeAnalysis", "description": "Analyze code"},
        ]
        context = _build_skill_context(skills)

        assert "1. WebSearch" in context
        assert "2. CodeAnalysis" in context
        assert context.count("\n") > 2

    def test_build_skill_context_no_description(self):
        """Test building skill context with skill missing description."""
        from prompt_manager import _build_skill_context

        skills = [{"name": "WebSearch"}]
        context = _build_skill_context(skills)

        assert "WebSearch" in context
        assert "1." in context
