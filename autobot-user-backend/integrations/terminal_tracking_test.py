# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal Tracking Integration Tests

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.integrations.terminal_tracking import (
    track_command_execution,
    track_pty_session_creation,
)


@pytest.mark.asyncio
class TestTerminalTracking:
    """Test terminal activity tracking integration."""

    @patch("integrations.terminal_tracking.track_terminal_activity")
    async def test_track_command_execution_success(self, mock_track_terminal):
        """Should track command execution successfully."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_terminal.return_value = activity_id

        result = await track_command_execution(
            db=mock_db,
            user_id=user_id,
            command="ls -la",
            working_directory="/home/user",
            exit_code=0,
            output="file1.txt\nfile2.txt",
            shell_type="bash",
        )

        assert result == activity_id
        mock_track_terminal.assert_awaited_once()

        # Verify metadata includes shell type
        call_kwargs = mock_track_terminal.call_args.kwargs
        assert call_kwargs["metadata"]["shell"] == "bash"

    @patch("integrations.terminal_tracking.track_terminal_activity")
    async def test_track_command_with_session_id(self, mock_track_terminal):
        """Should track command with session context."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        session_id = "chat_abc123"
        activity_id = uuid.uuid4()
        mock_track_terminal.return_value = activity_id

        result = await track_command_execution(
            db=mock_db,
            user_id=user_id,
            command="git status",
            session_id=session_id,
        )

        assert result == activity_id

        call_kwargs = mock_track_terminal.call_args.kwargs
        assert call_kwargs["session_id"] == session_id

    @patch("integrations.terminal_tracking.track_terminal_activity")
    async def test_track_pty_session_creation(self, mock_track_terminal):
        """Should track PTY session creation."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        pty_id = "pty_xyz789"
        activity_id = uuid.uuid4()
        mock_track_terminal.return_value = activity_id

        result = await track_pty_session_creation(
            db=mock_db,
            user_id=user_id,
            pty_id=pty_id,
            shell_type="zsh",
        )

        assert result == activity_id

        # Verify PTY metadata
        call_kwargs = mock_track_terminal.call_args.kwargs
        assert call_kwargs["metadata"]["pty_id"] == pty_id
        assert call_kwargs["metadata"]["shell"] == "zsh"
        assert call_kwargs["metadata"]["event"] == "session_created"

    @patch("integrations.terminal_tracking.track_terminal_activity")
    async def test_track_command_execution_error(self, mock_track_terminal):
        """Should raise exception on tracking failure."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        mock_track_terminal.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            await track_command_execution(
                db=mock_db,
                user_id=user_id,
                command="ls",
            )
