# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for terminal history service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTerminalHistoryService:
    """Tests for TerminalHistoryService."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock = MagicMock()
        mock.zadd = AsyncMock()
        mock.zcard = AsyncMock(return_value=5)
        mock.zrevrange = AsyncMock(return_value=["ls -la", "cd ..", "git status"])
        mock.zremrangebyrank = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def service(self, mock_redis):
        """Create history service with mocked Redis."""
        with patch(
            "src.services.terminal_history_service.get_redis_client",
            return_value=mock_redis,
        ):
            from services.terminal_history_service import TerminalHistoryService

            svc = TerminalHistoryService()
            svc.redis = mock_redis
            return svc

    @pytest.mark.asyncio
    async def test_add_command(self, service, mock_redis):
        """Add command to history."""
        await service.add_command("user1", "ls -la")
        mock_redis.zadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_command_empty_ignored(self, service, mock_redis):
        """Empty commands should be ignored."""
        await service.add_command("user1", "   ")
        mock_redis.zadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_history(self, service, mock_redis):
        """Get recent history."""
        result = await service.get_history("user1", limit=10)
        assert result == ["ls -la", "cd ..", "git status"]
        mock_redis.zrevrange.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_history(self, service, mock_redis):
        """Search history by query."""
        mock_redis.zrevrange.return_value = ["git status", "git commit", "ls -la"]
        result = await service.search_history("user1", "git")
        assert "git status" in result
        assert "git commit" in result
        assert "ls -la" not in result

    @pytest.mark.asyncio
    async def test_clear_history(self, service, mock_redis):
        """Clear all history."""
        await service.clear_history("user1")
        mock_redis.delete.assert_called_once()
