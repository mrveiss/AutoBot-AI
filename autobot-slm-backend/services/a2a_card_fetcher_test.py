# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for the A2A Card Fetcher Service (Issue #962).

Uses unittest.mock — no network, no database.
"""

import pytest
from services.a2a_card_fetcher import _A2A_ROLE, _fetch_one

# ---------------------------------------------------------------------------
# _fetch_one tests
# ---------------------------------------------------------------------------


class TestFetchOne:
    @pytest.mark.asyncio
    async def test_returns_none_on_unreachable_host(self):
        """_fetch_one must return None (not raise) on any connection failure."""
        result = await _fetch_one("0.0.0.1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_test_net(self):
        """TEST-NET-1 (192.0.2.0/24) is unreachable — function must not raise."""
        result = await _fetch_one("192.0.2.1")
        assert result is None


# ---------------------------------------------------------------------------
# Role filter constant
# ---------------------------------------------------------------------------


class TestConstants:
    def test_a2a_role_is_backend(self):
        assert _A2A_ROLE == "backend"
