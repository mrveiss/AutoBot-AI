# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for artifact capture in ParallelToolExecutor (Issue #4094, #4175)"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from events.types import ArtifactType
from tools.parallel.executor import (
    ParallelToolExecutor,
    _ArtifactCapture,
    _DEPLOYMENT_TOOLS,
    _FILE_MODIFYING_TOOLS,
    _TEST_RUNNER_TOOLS,
)
from tools.parallel.types import ToolCall


def _make_executor() -> ParallelToolExecutor:
    """Create a ParallelToolExecutor with a no-op dispatcher for unit tests."""
    return ParallelToolExecutor(tool_dispatcher=MagicMock())


class TestArtifactCapture:
    """Tests for _capture_pre_state method"""

    def test_non_file_tool_returns_empty_capture(self):
        """Non-file tools return empty capture"""
        executor = _make_executor()
        call = ToolCall(tool_name="read_file", arguments={})
        capture = executor._capture_pre_state(call)
        assert capture.filepath is None

    def test_file_modifying_tool_captures_file_path(self):
        """File-modifying tools capture filepath from file_path arg"""
        executor = _make_executor()
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})
        capture = executor._capture_pre_state(call)
        assert capture.filepath == "/tmp/test.py"

    def test_file_modifying_tool_captures_path_alias(self):
        """File-modifying tools also check 'path' argument key"""
        executor = _make_executor()
        call = ToolCall(tool_name="create_file", arguments={"path": "/tmp/new.txt"})
        capture = executor._capture_pre_state(call)
        assert capture.filepath == "/tmp/new.txt"


class TestBuildArtifacts:
    """Tests for _build_artifacts method"""

    def test_file_change_artifact_created(self):
        """File change artifacts are created for file-modifying tools"""
        executor = _make_executor()
        call = ToolCall(tool_name="edit_file", arguments={"file_path": "/tmp/test.py"})
        capture = _ArtifactCapture(filepath="/tmp/test.py")
        artifacts = executor._build_artifacts(call, capture, {})
        assert len(artifacts) >= 1
        assert artifacts[0].artifact_type == ArtifactType.FILE_CHANGE

    def test_code_diff_artifact_generated(self):
        """Code diff artifact generated when result has before/after content"""
        executor = _make_executor()
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
        executor = _make_executor()
        call = ToolCall(tool_name="pytest", arguments={})
        capture = _ArtifactCapture()
        result = {"output": "PASSED: 10 tests", "stdout": "All tests passed"}
        artifacts = executor._build_artifacts(call, capture, result)
        test_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.TEST_OUTPUT]
        assert len(test_artifacts) > 0

    def test_read_only_tool_no_artifacts(self):
        """Read-only tools produce no artifacts"""
        executor = _make_executor()
        call = ToolCall(tool_name="read_file", arguments={})
        capture = _ArtifactCapture()
        artifacts = executor._build_artifacts(call, capture, {"content": "file content"})
        assert len(artifacts) == 0

    # --- deployment output tests (Issue #4175) ---

    def test_ansible_playbook_output_captured(self):
        """Ansible playbook output captured as DEPLOYMENT_LOG artifact"""
        executor = _make_executor()
        call = ToolCall(tool_name="ansible_playbook", arguments={})
        capture = _ArtifactCapture()
        result = {"output": "PLAY [all] *****\nTASK [Gathering Facts]\nok: [host]\nPLAY RECAP: host ok=1"}
        artifacts = executor._build_artifacts(call, capture, result)
        deployment_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.DEPLOYMENT_LOG]
        assert len(deployment_artifacts) == 1
        assert "PLAY RECAP" in deployment_artifacts[0].content
        assert deployment_artifacts[0].label == "Deployment Output"

    def test_terraform_apply_stdout_captured(self):
        """Terraform apply stdout captured as DEPLOYMENT_LOG artifact"""
        executor = _make_executor()
        call = ToolCall(tool_name="terraform_apply", arguments={})
        capture = _ArtifactCapture()
        result = {"stdout": "Apply complete! Resources: 3 added, 0 changed, 0 destroyed."}
        artifacts = executor._build_artifacts(call, capture, result)
        deployment_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.DEPLOYMENT_LOG]
        assert len(deployment_artifacts) == 1
        assert "Apply complete" in deployment_artifacts[0].content

    def test_shell_string_result_captured(self):
        """Shell tool with string result captured as DEPLOYMENT_LOG artifact"""
        executor = _make_executor()
        call = ToolCall(tool_name="bash", arguments={})
        capture = _ArtifactCapture()
        result = "Command succeeded\nExit code: 0"
        artifacts = executor._build_artifacts(call, capture, result)
        deployment_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.DEPLOYMENT_LOG]
        assert len(deployment_artifacts) == 1
        assert "Exit code: 0" in deployment_artifacts[0].content

    def test_deployment_tool_empty_output_no_artifact(self):
        """Deployment tools with empty output produce no DEPLOYMENT_LOG artifact"""
        executor = _make_executor()
        call = ToolCall(tool_name="ansible", arguments={})
        capture = _ArtifactCapture()
        artifacts = executor._build_artifacts(call, capture, {})
        deployment_artifacts = [a for a in artifacts if a.artifact_type == ArtifactType.DEPLOYMENT_LOG]
        assert len(deployment_artifacts) == 0

    def test_deployment_tools_set_contains_expected_tools(self):
        """_DEPLOYMENT_TOOLS contains Ansible, Terraform, shell, and bash tools"""
        assert "ansible_playbook" in _DEPLOYMENT_TOOLS
        assert "terraform_apply" in _DEPLOYMENT_TOOLS
        assert "terraform_plan" in _DEPLOYMENT_TOOLS
        assert "shell" in _DEPLOYMENT_TOOLS
        assert "bash" in _DEPLOYMENT_TOOLS


class TestPublishObservationWithArtifacts:
    """Integration tests for artifact publishing"""

    @pytest.mark.asyncio
    async def test_artifacts_passed_to_observation_event(self):
        """Artifacts are passed to observation event creation"""
        executor = _make_executor()
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
