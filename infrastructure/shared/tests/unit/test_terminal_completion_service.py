# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for terminal completion service."""

from unittest.mock import AsyncMock, patch

import pytest
from src.services.terminal_completion_service import TerminalCompletionService


class TestTerminalCompletionService:
    """Tests for TerminalCompletionService."""

    @pytest.fixture
    def service(self):
        """Create completion service instance."""
        return TerminalCompletionService()

    def test_extract_current_word_simple(self, service):
        """Extract word at cursor position."""
        result = service._extract_current_word("cd /home/user/Doc", 17)
        assert result == "Doc"

    def test_extract_current_word_empty(self, service):
        """Empty word at start."""
        result = service._extract_current_word("", 0)
        assert result == ""

    def test_is_first_word_true(self, service):
        """First word detection - command position."""
        assert service._is_first_word("ls", 2) is True
        assert service._is_first_word("git", 3) is True

    def test_is_first_word_false(self, service):
        """First word detection - argument position."""
        assert service._is_first_word("cd /home", 8) is False
        assert service._is_first_word("ls -la", 5) is False

    def test_find_common_prefix_single(self, service):
        """Common prefix with single completion."""
        result = service._find_common_prefix(["Desktop"])
        assert result == "Desktop"

    def test_find_common_prefix_multiple(self, service):
        """Common prefix with multiple completions."""
        result = service._find_common_prefix(["Desktop", "Documents", "Downloads"])
        assert result == "D"

    def test_find_common_prefix_empty(self, service):
        """Common prefix with no completions."""
        result = service._find_common_prefix([])
        assert result == ""

    @pytest.mark.asyncio
    async def test_complete_paths_mock(self, service):
        """Test path completion with mocked compgen."""
        with patch.object(service, "_run_compgen", new_callable=AsyncMock) as mock:
            mock.return_value = ["Desktop", "Documents"]
            with patch("os.path.isdir", return_value=True):
                result = await service._complete_paths("D", "/home/user")
                assert "Desktop/" in result
                assert "Documents/" in result
