# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for WebResearcher's rate-limiter wiring (Issue #12646).

WebResearcher used to carry its own local, in-memory ``RateLimiter`` class
(blocking-wait, single window). It now delegates to the shared
``autobot_shared.rate_limiter.RateLimiter``'s custom single-window mode
(``acquire_window``/``get_remaining_in_window``). The window/limit algorithm
itself is covered by ``autobot_shared/rate_limiter_test.py``; these tests
pin the wiring: correct max_requests/window_seconds sourced from config,
independent per-instance keys, and the ``get_cache_stats()`` introspection
shape consumed by the frontend (``current_requests``/``max_requests``/
``window_seconds``).
"""

from unittest.mock import AsyncMock, patch

import pytest

from agents.web_researcher import WebResearcher

_PATCH_TARGET = "autobot_shared.rate_limiter.get_async_redis_client"


class TestRateLimiterWiring:
    def test_defaults_match_prior_fork_values(self) -> None:
        """Default max_requests=5, window_seconds=60 (prior RateLimiter defaults)."""
        researcher = WebResearcher()
        assert researcher._rl_max_requests == 5
        assert researcher._rl_window_seconds == 60

    def test_config_overrides_applied(self) -> None:
        researcher = WebResearcher({"rate_limit_requests": 9, "rate_limit_window": 30})
        assert researcher._rl_max_requests == 9
        assert researcher._rl_window_seconds == 30

    def test_distinct_instances_get_distinct_keys(self) -> None:
        """Two WebResearcher instances must not share a rate-limit bucket."""
        a = WebResearcher()
        b = WebResearcher()
        assert a._rl_key != b._rl_key


class TestGetCacheStats:
    @pytest.mark.asyncio
    async def test_shape_matches_frontend_contract(self) -> None:
        """cache_stats.rate_limiter must expose max_requests/window_seconds/
        current_requests — consumed by WebResearchSettings.vue (#12646)."""
        researcher = WebResearcher({"rate_limit_requests": 5, "rate_limit_window": 60})

        with patch(_PATCH_TARGET, AsyncMock(return_value=None)):
            stats = await researcher.get_cache_stats()

        assert stats["rate_limiter"]["max_requests"] == 5
        assert stats["rate_limiter"]["window_seconds"] == 60
        # Redis unavailable → fail-open remaining=max → current_requests=0.
        assert stats["rate_limiter"]["current_requests"] == 0

    @pytest.mark.asyncio
    async def test_current_requests_reflects_remaining(self) -> None:
        """current_requests = max_requests - remaining_in_window."""
        researcher = WebResearcher({"rate_limit_requests": 5, "rate_limit_window": 60})
        researcher.rate_limiter.get_remaining_in_window = AsyncMock(return_value=2)

        stats = await researcher.get_cache_stats()

        assert stats["rate_limiter"]["current_requests"] == 3


class TestAcquireBeforeResearch:
    @pytest.mark.asyncio
    async def test_conduct_research_acquires_with_configured_limit(self) -> None:
        """conduct_research must call acquire_window with this instance's
        rate_limit/window and wait=True (blocking, never rejects) before
        proceeding — matches the retired local RateLimiter's semantics."""
        researcher = WebResearcher({"enabled": True, "rate_limit_requests": 3, "rate_limit_window": 45})
        researcher.rate_limiter.acquire_window = AsyncMock(return_value=True)
        # #13284: acquire_window is the only thing under test, but
        # conduct_research goes on to `asyncio.create_task(self.search_web(...))`
        # and awaits it under `wait_for(timeout=self.timeout_seconds)`. Left
        # unmocked that is a real outbound web search, and this test measured
        # 29.74s on CI — a search timeout expiring, not verification. Stubbing
        # search_web keeps every assertion below intact (acquire_window must
        # still be called first, with these arguments) and removes the network.
        researcher.search_web = AsyncMock(return_value={"status": "success", "results": []})

        await researcher.conduct_research("test query")

        researcher.rate_limiter.acquire_window.assert_called_once_with(
            researcher._rl_key,
            max_requests=3,
            window_seconds=45,
            wait=True,
        )
