# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Code Source API (Issue #865).
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# Mock Node model for testing
class MockNode:
    """Mock Node model for testing."""

    def __init__(self):
        self.node_id = "test-node"
        self.hostname = "test-host"
        self.ip_address = "172.16.168.20"
        self.ssh_user = "autobot"


# Import the functions directly without triggering full module init
code_source_path = Path(__file__).parent / "code_source.py"
spec = __import__("importlib.util").util.spec_from_file_location(
    "code_source_module", code_source_path
)
code_source_module = __import__("importlib.util").util.module_from_spec(spec)

# Mock dependencies before loading the module
sys.modules["services.auth"] = MagicMock()
sys.modules["services.database"] = MagicMock()
sys.modules["models.database"] = MagicMock()

spec.loader.exec_module(code_source_module)

_find_similar_paths = code_source_module._find_similar_paths
_validate_repo_path = code_source_module._validate_repo_path


class TestCodeSourceValidation:
    """Tests for code source path validation."""

    @pytest.fixture
    def mock_node(self):
        """Create a mock node for testing."""
        return MockNode()

    @pytest.mark.asyncio
    async def test_validate_repo_path_success(self, mock_node):
        """Test successful path validation when directory exists."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"exists\n", b""))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            # Should not raise exception
            await _validate_repo_path(mock_node, "/opt/autobot")

            # Verify SSH command was constructed correctly
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args[0]
            assert call_args[0] == "ssh"
            assert "autobot@172.16.168.20" in call_args
            assert "test -d /opt/autobot && echo exists" in call_args

    @pytest.mark.asyncio
    async def test_validate_repo_path_not_exists(self, mock_node):
        """Test validation fails when directory doesn't exist."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # First call: test -d fails (path doesn't exist)
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 1
            mock_exec.return_value = mock_process

            # Second call: ls -1 finds no similar paths
            with patch("code_source_module._find_similar_paths", return_value=None):
                with pytest.raises(HTTPException) as exc_info:
                    await _validate_repo_path(mock_node, "/wrong/path")

                assert exc_info.value.status_code == 400
                assert "does not exist" in exc_info.value.detail
                assert "/wrong/path" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_validate_repo_path_case_mismatch_suggestion(self, mock_node):
        """Test validation suggests correct path when case mismatch detected."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # First call: test -d fails
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 1
            mock_exec.return_value = mock_process

            # Mock finding similar path
            with patch(
                "code_source_module._find_similar_paths",
                return_value="/home/kali/Desktop/AutoBot",
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await _validate_repo_path(mock_node, "/home/kali/Desktop/Autobot")

                assert exc_info.value.status_code == 400
                assert "does not exist" in exc_info.value.detail
                assert (
                    "Did you mean: /home/kali/Desktop/AutoBot?" in exc_info.value.detail
                )

    @pytest.mark.asyncio
    async def test_validate_repo_path_timeout(self, mock_node):
        """Test validation handles SSH timeout gracefully."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_exec.return_value = mock_process

            with pytest.raises(HTTPException) as exc_info:
                await _validate_repo_path(mock_node, "/opt/autobot")

            assert exc_info.value.status_code == 504
            assert "Timeout" in exc_info.value.detail
            assert "test-host" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_validate_repo_path_ssh_failure(self, mock_node):
        """Test validation handles SSH connection failure."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = OSError("Connection refused")

            with pytest.raises(HTTPException) as exc_info:
                await _validate_repo_path(mock_node, "/opt/autobot")

            assert exc_info.value.status_code == 500
            assert "Failed to validate path" in exc_info.value.detail
            assert "test-host" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_find_similar_paths_case_mismatch(self, mock_node):
        """Test finding similar paths detects case differences."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock ls -1 output showing case mismatch
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(
                return_value=(b"AutoBot\nother-dir\n", b"")
            )
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            result = await _find_similar_paths(mock_node, "/home/kali/Desktop/autobot")

            assert result == "/home/kali/Desktop/AutoBot"

    @pytest.mark.asyncio
    async def test_find_similar_paths_no_match(self, mock_node):
        """Test finding similar paths returns None when no match."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock ls -1 output with no matching entries
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(
                return_value=(b"other-dir\nanother-dir\n", b"")
            )
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            result = await _find_similar_paths(mock_node, "/home/kali/Desktop/autobot")

            assert result is None

    @pytest.mark.asyncio
    async def test_find_similar_paths_exact_match(self, mock_node):
        """Test finding similar paths ignores exact matches."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Mock ls -1 output with exact match (same case)
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"AutoBot\n", b""))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            # Should return None because it's an exact match (not a case mismatch)
            result = await _find_similar_paths(mock_node, "/home/kali/Desktop/AutoBot")

            assert result is None

    @pytest.mark.asyncio
    async def test_find_similar_paths_ssh_failure(self, mock_node):
        """Test finding similar paths handles SSH failure gracefully."""
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = OSError("Connection refused")

            result = await _find_similar_paths(mock_node, "/home/kali/Desktop/autobot")

            # Should return None on failure, not raise exception
            assert result is None
