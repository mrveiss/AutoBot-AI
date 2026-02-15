# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
File Tracking Integration Tests

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from integrations.file_tracking import (
    track_file_download,
    track_file_operation,
    track_file_upload,
)


@pytest.mark.asyncio
class TestFileTracking:
    """Test file activity tracking integration."""

    @patch("integrations.file_tracking.track_file_activity")
    async def test_track_file_operation_create(self, mock_track_file):
        """Should track file creation."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_file.return_value = activity_id

        result = await track_file_operation(
            db=mock_db,
            user_id=user_id,
            operation="create",
            path="/home/user/document.txt",
            size_bytes=1024,
        )

        assert result == activity_id
        mock_track_file.assert_awaited_once()

        # Verify file type extracted from extension
        call_kwargs = mock_track_file.call_args.kwargs
        assert call_kwargs["file_type"] == "txt"

    @patch("integrations.file_tracking.track_file_activity")
    async def test_track_file_operation_rename(self, mock_track_file):
        """Should track file rename with new path."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_file.return_value = activity_id

        result = await track_file_operation(
            db=mock_db,
            user_id=user_id,
            operation="rename",
            path="/home/user/old.txt",
            new_path="/home/user/new.txt",
        )

        assert result == activity_id

        call_kwargs = mock_track_file.call_args.kwargs
        assert call_kwargs["new_path"] == "/home/user/new.txt"

    @patch("integrations.file_tracking.track_file_activity")
    async def test_track_file_upload(self, mock_track_file):
        """Should track file upload."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_file.return_value = activity_id

        result = await track_file_upload(
            db=mock_db,
            user_id=user_id,
            path="/uploads/image.png",
            size_bytes=2048,
            mime_type="image/png",
        )

        assert result == activity_id

        # Verify upload metadata
        call_kwargs = mock_track_file.call_args.kwargs
        assert call_kwargs["operation"] == "create"
        assert call_kwargs["metadata"]["upload"] is True
        assert call_kwargs["metadata"]["mime_type"] == "image/png"

    @patch("integrations.file_tracking.track_file_activity")
    async def test_track_file_download(self, mock_track_file):
        """Should track file download."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_file.return_value = activity_id

        result = await track_file_download(
            db=mock_db,
            user_id=user_id,
            path="/downloads/data.csv",
        )

        assert result == activity_id

        # Verify download metadata
        call_kwargs = mock_track_file.call_args.kwargs
        assert call_kwargs["operation"] == "read"
        assert call_kwargs["metadata"]["download"] is True

    @patch("integrations.file_tracking.track_file_activity")
    async def test_track_file_with_session_id(self, mock_track_file):
        """Should track file operation with session context."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        session_id = "chat_abc123"
        activity_id = uuid.uuid4()
        mock_track_file.return_value = activity_id

        result = await track_file_operation(
            db=mock_db,
            user_id=user_id,
            operation="read",
            path="/home/user/config.yaml",
            session_id=session_id,
        )

        assert result == activity_id

        call_kwargs = mock_track_file.call_args.kwargs
        assert call_kwargs["session_id"] == session_id
