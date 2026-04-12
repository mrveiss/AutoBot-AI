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
    _FILE_MODIFYING_TOOLS,
    _TEST_RUNNER_TOOLS,
    _normalize_result,
)
from tools.parallel.types import ToolCall


class TestNormalizeResult:
    """Tests for _normalize_result (Issue #4174) — canonical key standardization."""

    # --- None / non-dict inputs ---

    def test_none_returns_empty_dict(self):
        assert _normalize_result("edit_file", None) == {}

    def test_non_dict_non_str_returns_empty_dict(self):
        assert _normalize_result("edit_file", 42) == {}

    # --- File-mutation tools: original/before -> canonical "original" ---

    def test_before_alias_maps_to_original(self):
        norm = _normalize_result("edit_file", {"before": "old", "after": "new"})
        assert norm["original"] == "old"

    def test_after_alias_maps_to_modified(self):
        norm = _normalize_result("edit_file", {"before": "old", "after": "new"})
        assert norm["modified"] == "new"

    def test_content_alias_maps_to_modified(self):
        norm = _normalize_result("write_file", {"original": "x", "content": "y"})
        assert norm["modified"] == "y"

    def test_canonical_original_not_overwritten(self):
        """When canonical key is already present it must not be replaced."""
        norm = _normalize_result("edit_file", {"original": "keep", "before": "drop"})
        assert norm["original"] == "keep"

    def test_canonical_modified_not_overwritten(self):
        norm = _normalize_result("edit_file", {"modified": "keep", "content": "drop"})
        assert norm["modified"] == "keep"

    def test_unknown_keys_preserved(self):
        norm = _normalize_result("edit_file", {"original": "a", "modified": "b", "extra": 1})
        assert norm["extra"] == 1

    # --- File-mutation aliases NOT applied to non-file-modifying tools ---

    def test_file_aliases_not_applied_to_read_tool(self):
        norm = _normalize_result("read_file", {"before": "x", "after": "y"})
        assert "original" not in norm
        assert "modified" not in norm

    # --- Test-runner tools: output -> canonical "stdout" ---

    def test_output_alias_maps_to_stdout(self):
        norm = _normalize_result("pytest", {"output": "PASSED", "returncode": 0})
        assert norm["stdout"] == "PASSED"

    def test_returncode_alias_maps_to_exit_code(self):
        norm = _normalize_result("run_tests", {"stdout": "ok", "returncode": 0})
        assert norm["exit_code"] == 0

    def test_return_code_alias_maps_to_exit_code(self):
        norm = _normalize_result("pytest", {"stdout": "ok", "return_code": 1})
        assert norm["exit_code"] == 1

    def test_canonical_stdout_not_overwritten_by_output(self):
        norm = _normalize_result("pytest", {"stdout": "keep", "output": "drop"})
        assert norm["stdout"] == "keep"

    # --- Test-runner: str result promoted to stdout ---

    def test_string_result_for_test_tool_becomes_stdout(self):
        norm = _normalize_result("pytest", "PASSED: 5 tests")
        assert norm == {"stdout": "PASSED: 5 tests"}

    def test_string_result_for_non_test_tool_returns_empty(self):
        norm = _normalize_result("edit_file", "some string")
        assert norm == {}

    # --- Test aliases NOT applied to file-modifying tools ---

    def test_test_aliases_not_applied_to_file_tool(self):
        norm = _normalize_result("edit_file", {"output": "log line"})
        assert "stdout" not in norm


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

    def test_before_after_aliases_produce_diff(self):
        """before/after aliases are normalized and produce a CODE_DIFF artifact."""
        executor = ParallelToolExecutor(config=MagicMock())
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})
        capture = _ArtifactCapture(filepath="/tmp/test.py")
        result = {"before": "line 1\n", "after": "line 1 modified\n"}
        artifacts = executor._build_artifacts(call, capture, result)
        diff_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.CODE_DIFF]
        assert len(diff_artifacts) == 1
        assert "@@" in diff_artifacts[0].content

    def test_output_alias_produces_test_artifact(self):
        """'output' alias is normalized to stdout and produces a TEST_OUTPUT artifact."""
        executor = ParallelToolExecutor(config=MagicMock())
        call = ToolCall(tool_name="pytest", arguments={})
        capture = _ArtifactCapture()
        result = {"output": "1 passed in 0.01s"}
        artifacts = executor._build_artifacts(call, capture, result)
        test_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.TEST_OUTPUT]
        assert len(test_artifacts) == 1
        assert test_artifacts[0].content == "1 passed in 0.01s"

    def test_string_result_produces_test_artifact(self):
        """Plain string result from test runner is normalized to stdout."""
        executor = ParallelToolExecutor(config=MagicMock())
        call = ToolCall(tool_name="run_tests", arguments={})
        capture = _ArtifactCapture()
        artifacts = executor._build_artifacts(call, capture, "All 3 passed")
        test_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.TEST_OUTPUT]
        assert len(test_artifacts) == 1
        assert test_artifacts[0].content == "All 3 passed"


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
