# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for AutoBotClaudeAPIAdapter AsyncInitializable migration (#3390).

Verifies lazy-init, idempotency, and that the module-level singleton is NOT
created eagerly at import time.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


class TestAutoBotClaudeAPIAdapterLazyInit:
    """AutoBotClaudeAPIAdapter should initialise lazily, not at import time."""

    def setup_method(self):
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        AutoBotClaudeAPIAdapter.reset_instance()

    def teardown_method(self):
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        AutoBotClaudeAPIAdapter.reset_instance()

    def test_module_level_adapter_is_none_at_import(self):
        """Module-level autobot_claude_adapter must be None — no eager init."""
        import utils.claude_api_integration as mod

        assert mod.autobot_claude_adapter is None

    @pytest.mark.asyncio
    async def test_adapter_not_initialized_before_first_call(self):
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        adapter = AutoBotClaudeAPIAdapter()
        assert not adapter.is_initialized

    @pytest.mark.asyncio
    async def test_get_adapter_initializes_lazily(self):
        mock_manager = MagicMock()

        async def _fake_create(cfg):
            return mock_manager

        with patch(
            "utils.claude_api_integration.create_claude_api_manager",
            side_effect=_fake_create,
        ):
            from utils.claude_api_integration import get_autobot_claude_adapter

            adapter = await get_autobot_claude_adapter()

        assert adapter.is_initialized
        assert adapter.manager is mock_manager

    @pytest.mark.asyncio
    async def test_get_adapter_idempotent(self):
        mock_manager = MagicMock()
        call_count = 0

        async def _fake_create(cfg):
            nonlocal call_count
            call_count += 1
            return mock_manager

        with patch(
            "utils.claude_api_integration.create_claude_api_manager",
            side_effect=_fake_create,
        ):
            from utils.claude_api_integration import get_autobot_claude_adapter

            a1 = await get_autobot_claude_adapter()
            a2 = await get_autobot_claude_adapter()
            a3 = await get_autobot_claude_adapter()

        assert a1 is a2 is a3
        assert call_count == 1  # _initialize_impl called exactly once

    @pytest.mark.asyncio
    async def test_concurrent_get_adapter_safe(self):
        mock_manager = MagicMock()
        call_count = 0

        async def _fake_create(cfg):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return mock_manager

        with patch(
            "utils.claude_api_integration.create_claude_api_manager",
            side_effect=_fake_create,
        ):
            from utils.claude_api_integration import get_autobot_claude_adapter

            adapters = await asyncio.gather(*[get_autobot_claude_adapter() for _ in range(5)])

        assert all(a is adapters[0] for a in adapters)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_reset_clears_singleton(self):
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        AutoBotClaudeAPIAdapter.reset_instance()
        assert AutoBotClaudeAPIAdapter._instance is None
