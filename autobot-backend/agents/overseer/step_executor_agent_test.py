# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for StepExecutorAgent (#690)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents.overseer.step_executor_agent import (
    StepExecutorAgent,
    _build_blocked_command_result,
    _build_execution_error_result,
    _build_no_command_result,
    _parse_pty_exit_code,
)
from agents.overseer.types import (
    AgentTask,
    CommandBreakdownPart,
    CommandExplanation,
    OutputExplanation,
    StepResult,
    StepStatus,
    StreamChunk,
)


@pytest.fixture()
def mock_explanation_service():
    """Create a mock explanation service."""
    svc = MagicMock()
    svc.explain_command = AsyncMock(
        return_value=CommandExplanation(
            summary="Test command",
            breakdown=[CommandBreakdownPart(part="ls", explanation="list")],
        )
    )
    svc.explain_output = AsyncMock(
        return_value=OutputExplanation(
            summary="Test output", key_findings=["finding 1"]
        )
    )
    return svc


@pytest.fixture()
def executor(mock_explanation_service):
    """Create a StepExecutorAgent with mocked service."""
    return StepExecutorAgent(
        session_id="test-session",
        explanation_service=mock_explanation_service,
    )


@pytest.fixture()
def sample_task():
    """Create a sample AgentTask."""
    return AgentTask(
        task_id="t1",
        step_number=1,
        total_steps=2,
        description="List files",
        command="ls -la",
    )


class TestBuildNoCommandResult:
    """Tests for _build_no_command_result."""

    def test_returns_completed(self):
        task = AgentTask(
            task_id="t1", step_number=1, total_steps=1, description="No-op step"
        )
        result = _build_no_command_result(task, 0.1)
        assert result.status == StepStatus.COMPLETED
        assert result.command is None
        assert "No command" in result.output

    def test_includes_description_in_findings(self):
        task = AgentTask(
            task_id="t1", step_number=1, total_steps=1, description="Check network"
        )
        result = _build_no_command_result(task, 0.1)
        assert "Check network" in result.output_explanation.key_findings


class TestBuildBlockedCommandResult:
    """Tests for _build_blocked_command_result."""

    def test_returns_failed(self):
        task = AgentTask(
            task_id="t1",
            step_number=1,
            total_steps=1,
            description="Bad command",
            command="rm -rf /",
        )
        result = _build_blocked_command_result(task, "Dangerous operation", 0.05)
        assert result.status == StepStatus.FAILED
        assert result.return_code == -1
        assert "Dangerous operation" in result.error

    def test_includes_safety_reason_in_output(self):
        task = AgentTask(
            task_id="t1",
            step_number=1,
            total_steps=1,
            description="test",
            command="dd if=/dev/zero",
        )
        result = _build_blocked_command_result(task, "Disk wipe detected", 0.01)
        assert "Disk wipe detected" in result.output


class TestBuildExecutionErrorResult:
    """Tests for _build_execution_error_result."""

    def test_returns_failed(self):
        task = AgentTask(
            task_id="t1",
            step_number=1,
            total_steps=1,
            description="test",
            command="broken",
        )
        error = RuntimeError("command not found")
        result = _build_execution_error_result(task, error, 0.5)
        assert result.status == StepStatus.FAILED
        assert result.error == "command not found"
        assert result.return_code == -1


class TestStepExecutorInit:
    """Tests for StepExecutorAgent initialization."""

    def test_defaults(self):
        executor = StepExecutorAgent(session_id="s1")
        assert executor.session_id == "s1"
        assert executor.pty_session_id == "s1"

    def test_custom_pty_session(self):
        executor = StepExecutorAgent(session_id="s1", pty_session_id="pty1")
        assert executor.pty_session_id == "pty1"

    def test_custom_explanation_service(self, mock_explanation_service):
        executor = StepExecutorAgent(
            session_id="s1", explanation_service=mock_explanation_service
        )
        assert executor.explanation_service is mock_explanation_service


class TestValidateCommand:
    """Tests for command validation."""

    @patch(
        "agents.overseer.step_executor_agent.check_dangerous_patterns", return_value=[]
    )
    @patch("agents.overseer.step_executor_agent.is_safe_command", return_value=True)
    def test_valid_command(self, mock_safe, mock_dangerous, executor):
        is_safe, reason = executor._validate_command("ls -la")
        assert is_safe is True
        assert reason is None

    def test_empty_command_rejected(self, executor):
        is_safe, reason = executor._validate_command("")
        assert is_safe is False
        assert "Empty" in reason

    def test_whitespace_rejected(self, executor):
        is_safe, reason = executor._validate_command("   ")
        assert is_safe is False

    @patch("agents.overseer.step_executor_agent.is_safe_command", return_value=True)
    @patch(
        "agents.overseer.step_executor_agent.check_dangerous_patterns",
        return_value=[("Destructive operation", "rm -rf")],
    )
    def test_dangerous_command_blocked(self, mock_dangerous, mock_safe, executor):
        is_safe, reason = executor._validate_command("rm -rf /")
        assert is_safe is False
        assert "Blocked" in reason


class TestExtractReturnCode:
    """Tests for return code extraction from chunks."""

    def test_extracts_from_final_chunk(self, executor):
        chunk = StreamChunk(
            task_id="t1",
            step_number=1,
            chunk_type="return_code",
            content="42",
            is_final=True,
        )
        assert executor._extract_return_code_from_chunk(chunk, 0) == 42

    def test_ignores_non_final(self, executor):
        chunk = StreamChunk(
            task_id="t1",
            step_number=1,
            chunk_type="return_code",
            content="42",
            is_final=False,
        )
        assert executor._extract_return_code_from_chunk(chunk, 0) == 0

    def test_handles_invalid_content(self, executor):
        chunk = StreamChunk(
            task_id="t1",
            step_number=1,
            chunk_type="return_code",
            content="not_a_number",
            is_final=True,
        )
        assert executor._extract_return_code_from_chunk(chunk, 99) == 99


class TestExecuteStep:
    """Tests for step execution flow."""

    @pytest.mark.asyncio
    async def test_no_command_yields_completed(self, executor):
        task = AgentTask(
            task_id="t1",
            step_number=1,
            total_steps=1,
            description="Info step",
            command=None,
        )
        results = []
        async for update in executor.execute_step(task):
            results.append(update)

        assert len(results) == 1
        assert isinstance(results[0], StepResult)
        assert results[0].status == StepStatus.COMPLETED

    @pytest.mark.asyncio
    @patch(
        "agents.overseer.step_executor_agent.check_dangerous_patterns",
        return_value=[("danger", "pat")],
    )
    @patch("agents.overseer.step_executor_agent.is_safe_command", return_value=True)
    async def test_blocked_command_yields_failed(
        self, mock_safe, mock_dangerous, executor
    ):
        task = AgentTask(
            task_id="t1",
            step_number=1,
            total_steps=1,
            description="Bad step",
            command="rm -rf /",
        )
        results = []
        async for update in executor.execute_step(task):
            results.append(update)

        assert any(
            isinstance(r, StepResult) and r.status == StepStatus.FAILED for r in results
        )

    @pytest.mark.asyncio
    @patch(
        "agents.overseer.step_executor_agent.check_dangerous_patterns", return_value=[]
    )
    @patch("agents.overseer.step_executor_agent.is_safe_command", return_value=True)
    async def test_successful_execution(
        self, mock_safe, mock_dangerous, executor, sample_task
    ):
        async def mock_stream(task):
            yield StreamChunk(
                task_id=task.task_id,
                step_number=task.step_number,
                chunk_type="stdout",
                content="file1.txt\n",
                is_final=False,
            )
            yield StreamChunk(
                task_id=task.task_id,
                step_number=task.step_number,
                chunk_type="return_code",
                content="0",
                is_final=True,
            )

        executor._execute_and_stream_command = mock_stream

        results = []
        async for update in executor.execute_step(sample_task):
            results.append(update)

        step_results = [r for r in results if isinstance(r, StepResult)]
        assert len(step_results) == 1
        assert step_results[0].status == StepStatus.COMPLETED
        assert step_results[0].command_explanation is not None
        assert step_results[0].output_explanation is not None


class TestGenerateExplanations:
    """Tests for explanation generation methods."""

    @pytest.mark.asyncio
    async def test_command_explanation_success(self, executor):
        result = await executor._generate_command_explanation("ls -la")
        assert result.summary == "Test command"
        executor.explanation_service.explain_command.assert_called_once_with("ls -la")

    @pytest.mark.asyncio
    async def test_command_explanation_fallback(self, executor):
        executor.explanation_service.explain_command = AsyncMock(
            side_effect=Exception("fail")
        )
        result = await executor._generate_command_explanation("nmap -sn")
        assert "nmap" in result.summary.lower() or "Executing" in result.summary

    @pytest.mark.asyncio
    async def test_output_explanation_success(self, executor):
        result = await executor._generate_output_explanation("ls", "output", 0)
        assert result.summary == "Test output"

    @pytest.mark.asyncio
    async def test_output_explanation_fallback(self, executor):
        executor.explanation_service.explain_output = AsyncMock(
            side_effect=Exception("fail")
        )
        result = await executor._generate_output_explanation("ls", "out", 1)
        assert "1" in result.summary
        assert len(result.key_findings) >= 1


class TestParsePtyExitCode:
    """Tests for _parse_pty_exit_code (Issue #935)."""

    def test_extracts_exit_code_zero(self):
        raw = "file1\nfile2\n__AUTOBOT_EXIT__=0"
        clean, code = _parse_pty_exit_code(raw)
        assert code == 0
        assert "__AUTOBOT_EXIT__" not in clean
        assert "file1" in clean

    def test_extracts_nonzero_exit_code(self):
        raw = "error output\n__AUTOBOT_EXIT__=2"
        clean, code = _parse_pty_exit_code(raw)
        assert code == 2
        assert "__AUTOBOT_EXIT__" not in clean

    def test_no_marker_returns_zero(self):
        raw = "some output without marker"
        clean, code = _parse_pty_exit_code(raw)
        assert code == 0
        assert clean == raw

    def test_marker_only(self):
        raw = "__AUTOBOT_EXIT__=127"
        clean, code = _parse_pty_exit_code(raw)
        assert code == 127
        assert clean == ""

    def test_marker_with_surrounding_whitespace(self):
        raw = "output\n\n__AUTOBOT_EXIT__=1\n"
        clean, code = _parse_pty_exit_code(raw)
        assert code == 1
        assert "output" in clean
        assert "__AUTOBOT_EXIT__" not in clean


class TestExtractTerminalOutput:
    """Tests for _extract_terminal_output aggregation (Issue #935)."""

    def test_aggregates_multiple_terminal_messages(self, executor):
        messages = [
            {"sender": "terminal", "text": "line one"},
            {"sender": "assistant", "text": "ignored"},
            {"sender": "terminal", "text": "line two"},
        ]
        result = executor._extract_terminal_output(messages)
        assert "line one" in result
        assert "line two" in result

    def test_skips_command_prompts(self, executor):
        messages = [
            {"sender": "terminal", "text": "$ ls"},
            {"sender": "terminal", "text": "file.txt"},
        ]
        result = executor._extract_terminal_output(messages)
        assert "$ ls" not in result
        assert "file.txt" in result

    def test_empty_messages_returns_empty(self, executor):
        result = executor._extract_terminal_output([])
        assert result == ""

    def test_non_terminal_senders_ignored(self, executor):
        messages = [
            {"sender": "user", "text": "user message"},
            {"sender": "assistant", "text": "assistant reply"},
        ]
        result = executor._extract_terminal_output(messages)
        assert result == ""
