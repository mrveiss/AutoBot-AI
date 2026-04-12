# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for artifact capture in ParallelToolExecutor (Issue #4094)"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from events.types import ArtifactType
from tools.parallel.executor import (
    ParallelToolExecutor,
    _ArtifactCapture,
    _CODE_DIFF_MAX_BYTES,
    _FILE_MODIFYING_TOOLS,
    _TEST_OUTPUT_MAX_BYTES,
    _TEST_RUNNER_TOOLS,
    _TRUNCATION_MARKER,
)
from tools.parallel.types import ToolCall


class TestArtifactCapture:
    """Tests for _capture_pre_state method"""

    def test_non_file_tool_returns_empty_capture(self):
        """Non-file tools return empty capture"""
        executor = ParallelToolExecutor(config=MagicMock())
        call = ToolCall(tool_name="read_file", arguments={})
        capture = executor._capture_pre_state(call)
        assert capture.filepath is None

    def test_file_modifying_tool_captures_file_path(self):
        """File-modifying tools capture filepath from file_path arg"""
        executor = ParallelToolExecutor(config=MagicMock())
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})
        capture = executor._capture_pre_state(call)
        assert capture.filepath == "/tmp/test.py"

    def test_file_modifying_tool_captures_path_alias(self):
        """File-modifying tools also check 'path' argument key"""
        executor = ParallelToolExecutor(config=MagicMock())
        call = ToolCall(tool_name="create_file", arguments={"path": "/tmp/new.txt"})
        capture = executor._capture_pre_state(call)
        assert capture.filepath == "/tmp/new.txt"


class TestBuildArtifacts:
    """Tests for _build_artifacts method"""

    def test_file_change_artifact_created(self):
        """File change artifacts are created for file-modifying tools"""
        executor = ParallelToolExecutor(config=MagicMock())
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})
        capture = _ArtifactCapture(filepath="/tmp/test.py")
        artifacts = executor._build_artifacts(call, capture, {})
        assert len(artifacts) >= 1
        assert artifacts[0].artifact_type == ArtifactType.FILE_CHANGE

    def test_code_diff_artifact_generated(self):
        """Code diff artifact generated when result has before/after content"""
        executor = ParallelToolExecutor(config=MagicMock())
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})
        capture = _ArtifactCapture(filepath="/tmp/test.py")
        result = {"original": "line 1\n", "content": "line 1 modified\n"}
        artifacts = executor._build_artifacts(call, capture, result)
        # Should have FILE_CHANGE + CODE_DIFF
        assert len(artifacts) >= 2
        diff_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.CODE_DIFF]
        assert len(diff_artifacts) > 0
        assert "@@" in diff_artifacts[0].content  # Unified diff format

    def test_test_output_artifact_extracted(self):
        """Test output artifacts extracted from test runner results"""
        executor = ParallelToolExecutor(config=MagicMock())
        call = ToolCall(tool_name="pytest", arguments={})
        capture = _ArtifactCapture()
        result = {"output": "PASSED: 10 tests", "stdout": "All tests passed"}
        artifacts = executor._build_artifacts(call, capture, result)
        test_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.TEST_OUTPUT]
        assert len(test_artifacts) > 0

    def test_read_only_tool_no_artifacts(self):
        """Read-only tools produce no artifacts"""
        executor = ParallelToolExecutor(config=MagicMock())
        call = ToolCall(tool_name="read_file", arguments={})
        capture = _ArtifactCapture()
        artifacts = executor._build_artifacts(call, capture, {"content": "file content"})
        assert len(artifacts) == 0


class TestTruncateArtifact:
    """Tests for _truncate_artifact static method (Issue #4173)"""

    def test_content_within_limit_unchanged(self):
        """Content below max_bytes returns unmodified string and False flag."""
        content = "x" * 100
        result, was_truncated = ParallelToolExecutor._truncate_artifact(content, 200, "test")
        assert result == content
        assert was_truncated is False

    def test_content_at_exact_limit_unchanged(self):
        """Content exactly at max_bytes returns unmodified and False."""
        content = "a" * _CODE_DIFF_MAX_BYTES
        result, was_truncated = ParallelToolExecutor._truncate_artifact(
            content, _CODE_DIFF_MAX_BYTES, "diff"
        )
        assert result == content
        assert was_truncated is False

    def test_oversized_content_truncated_with_marker(self):
        """Content exceeding max_bytes is truncated, marker appended, flag True."""
        oversized = "b" * (_TEST_OUTPUT_MAX_BYTES + 1000)
        result, was_truncated = ParallelToolExecutor._truncate_artifact(
            oversized, _TEST_OUTPUT_MAX_BYTES, "Test Output"
        )
        assert was_truncated is True
        assert result.endswith(_TRUNCATION_MARKER)
        assert len(result.encode("utf-8")) <= _TEST_OUTPUT_MAX_BYTES + len(
            _TRUNCATION_MARKER.encode("utf-8")
        )

    def test_truncation_logs_warning(self, caplog):
        """Warning is logged when truncation occurs."""
        import logging

        oversized = "c" * (_CODE_DIFF_MAX_BYTES + 500)
        with caplog.at_level(logging.WARNING, logger="tools.parallel.executor"):
            ParallelToolExecutor._truncate_artifact(
                oversized, _CODE_DIFF_MAX_BYTES, "Code Diff: /tmp/big.py"
            )
        assert any("truncated" in r.message for r in caplog.records)


class TestBuildArtifactsSizeLimits:
    """Tests that _build_artifacts enforces size limits (Issue #4173)"""

    def test_oversized_test_output_is_truncated(self):
        """Test output exceeding 100 KB sets artifact.truncated = True."""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="pytest", arguments={})
        capture = _ArtifactCapture()
        big_output = "line\n" * 25000  # well over 100 KB
        result = {"output": big_output}
        artifacts = executor._build_artifacts(call, capture, result)
        test_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.TEST_OUTPUT]
        assert len(test_artifacts) == 1
        assert test_artifacts[0].truncated is True

    def test_oversized_code_diff_is_truncated(self):
        """Code diff exceeding 50 KB sets artifact.truncated = True."""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/big.py"})
        capture = _ArtifactCapture(filepath="/tmp/big.py")
        big_content = "x" * 20000
        result = {"original": big_content, "content": big_content + "y"}

        with patch(
            "tools.parallel.executor.DiffGenerator.generate_diff",
            return_value="+" + "z" * (_CODE_DIFF_MAX_BYTES + 1000),
        ):
            artifacts = executor._build_artifacts(call, capture, result)

        diff_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.CODE_DIFF]
        assert len(diff_artifacts) == 1
        assert diff_artifacts[0].truncated is True

    def test_small_test_output_not_truncated(self):
        """Test output within limit leaves artifact.truncated = False."""
        executor = ParallelToolExecutor(tool_dispatcher=AsyncMock(), config=MagicMock())
        call = ToolCall(tool_name="pytest", arguments={})
        capture = _ArtifactCapture()
        result = {"output": "PASSED: 3 tests"}
        artifacts = executor._build_artifacts(call, capture, result)
        test_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.TEST_OUTPUT]
        assert len(test_artifacts) == 1
        assert test_artifacts[0].truncated is False


class TestPublishObservationWithArtifacts:
    """Integration tests for artifact publishing"""

    @pytest.mark.asyncio
    async def test_artifacts_passed_to_observation_event(self):
        """Artifacts are passed to observation event creation"""
        config = MagicMock()
        executor = ParallelToolExecutor(config=config)
        executor.event_stream = AsyncMock()

        action_event = MagicMock(event_id="action-123")
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})
        artifacts = [MagicMock()]

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
