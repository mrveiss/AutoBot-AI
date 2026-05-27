# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for artifact capture in ParallelToolExecutor (Issue #4094)"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from events.types import ArtifactType, build_artifact
from tools.parallel.executor import (
    ParallelToolExecutor,
    _ArtifactCapture,
)
from tools.parallel.types import ToolCall


class TestArtifactCapture:
    """Tests for _capture_pre_state method"""

    def test_non_file_tool_returns_empty_capture(self):
        """Non-file tools return empty capture"""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="read_file", arguments={})
        capture = executor._capture_pre_state(call)
        assert capture.filepath is None

    def test_file_modifying_tool_captures_file_path(self):
        """File-modifying tools capture filepath from file_path arg"""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})  # nosec B108 - test/controlled code uses tmpdir intentionally
        capture = executor._capture_pre_state(call)
        assert capture.filepath == "/tmp/test.py"  # nosec B108 - test/controlled code uses tmpdir intentionally

    def test_file_modifying_tool_captures_path_alias(self):
        """File-modifying tools also check 'path' argument key"""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="create_file", arguments={"path": "/tmp/new.txt"})  # nosec B108 - test/controlled code uses tmpdir intentionally
        capture = executor._capture_pre_state(call)
        assert capture.filepath == "/tmp/new.txt"  # nosec B108 - test/controlled code uses tmpdir intentionally


class TestBuildArtifacts:
    """Tests for _build_artifacts method"""

    def test_file_change_artifact_created(self):
        """File change artifacts are created for file-modifying tools"""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})  # nosec B108 - test/controlled code uses tmpdir intentionally
        capture = _ArtifactCapture(filepath="/tmp/test.py")  # nosec B108 - test/controlled code uses tmpdir intentionally
        artifacts = executor._build_artifacts(call, capture, {})
        assert len(artifacts) >= 1
        assert artifacts[0].artifact_type == ArtifactType.FILE_CHANGE

    def test_code_diff_artifact_generated(self):
        """Code diff artifact generated when result has before/after content"""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})  # nosec B108 - test/controlled code uses tmpdir intentionally
        capture = _ArtifactCapture(filepath="/tmp/test.py")  # nosec B108 - test/controlled code uses tmpdir intentionally
        result = {"original": "line 1\n", "content": "line 1 modified\n"}
        artifacts = executor._build_artifacts(call, capture, result)
        # Should have FILE_CHANGE + CODE_DIFF
        assert len(artifacts) >= 2
        diff_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.CODE_DIFF]
        assert len(diff_artifacts) > 0
        assert "@@" in diff_artifacts[0].content  # Unified diff format

    def test_test_output_artifact_extracted(self):
        """Test output artifacts extracted from test runner results"""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="pytest", arguments={})
        capture = _ArtifactCapture()
        result = {"output": "PASSED: 10 tests", "stdout": "All tests passed"}
        artifacts = executor._build_artifacts(call, capture, result)
        test_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.TEST_OUTPUT]
        assert len(test_artifacts) > 0

    def test_read_only_tool_no_artifacts(self):
        """Read-only tools produce no artifacts"""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="read_file", arguments={})
        capture = _ArtifactCapture()
        artifacts = executor._build_artifacts(call, capture, {"content": "file content"})
        assert len(artifacts) == 0

    def test_diff_generation_failure_does_not_crash_artifact_capture(self):
        """If DiffGenerator.generate_diff raises, artifact capture continues and FILE_CHANGE is still produced"""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})  # nosec B108 - test/controlled code uses tmpdir intentionally
        capture = _ArtifactCapture(filepath="/tmp/test.py")  # nosec B108 - test/controlled code uses tmpdir intentionally
        result = {"original": "before\n", "content": "after\n"}

        with patch(
            "tools.parallel.executor.DiffGenerator.generate_diff",
            side_effect=RuntimeError("diff engine failure"),
        ):
            artifacts = executor._build_artifacts(call, capture, result)

        # FILE_CHANGE artifact must still be present
        file_change_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.FILE_CHANGE]
        assert len(file_change_artifacts) == 1
        # CODE_DIFF artifact must NOT be present (diff failed)
        diff_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.CODE_DIFF]
        assert len(diff_artifacts) == 0


class TestPublishObservationWithArtifacts:
    """Integration tests for artifact publishing"""

    @pytest.mark.asyncio
    async def test_artifacts_passed_to_observation_event(self):
        """Artifacts are passed to observation event creation"""
        config = MagicMock()
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=config)
        executor.event_stream = AsyncMock()

        action_event = MagicMock(event_id="action-123")
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})  # nosec B108 - test/controlled code uses tmpdir intentionally
        # Create a valid artifact using build_artifact to ensure JSON serializability
        artifacts = [
            build_artifact(
                artifact_type=ArtifactType.FILE_CHANGE, content="test change", label="test.py", file_path="/tmp/test.py"  # nosec B108 - test/controlled code uses tmpdir intentionally
            )
        ]

        await executor._publish_observation_event(
            action_event=action_event,
            call=call,
            success=True,
            result={"content": "test"},
            error=None,
            execution_time=100.0,
            task_id="task-123",
            artifacts=artifacts,
        )

        # Verify event_stream.publish was called
        assert executor.event_stream.publish.called
