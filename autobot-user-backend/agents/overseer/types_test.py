# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for overseer agent type definitions (#690)."""

from datetime import datetime

from agents.overseer.types import (
    AgentTask,
    CommandBreakdownPart,
    CommandExplanation,
    OutputExplanation,
    OverseerUpdate,
    StepResult,
    StepStatus,
    StreamChunk,
    TaskPlan,
    TaskStatus,
)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_all_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.PLANNING.value == "planning"
        assert TaskStatus.EXECUTING.value == "executing"
        assert TaskStatus.STREAMING.value == "streaming"
        assert TaskStatus.EXPLAINING.value == "explaining"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_member_count(self):
        assert len(TaskStatus) == 8


class TestStepStatus:
    """Tests for StepStatus enum."""

    def test_all_values(self):
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.STREAMING.value == "streaming"
        assert StepStatus.WAITING_EXPLANATION.value == "waiting_explanation"
        assert StepStatus.EXPLAINING.value == "explaining"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"

    def test_member_count(self):
        assert len(StepStatus) == 7


class TestCommandBreakdownPart:
    """Tests for CommandBreakdownPart dataclass."""

    def test_creation(self):
        part = CommandBreakdownPart(part="ls", explanation="list files")
        assert part.part == "ls"
        assert part.explanation == "list files"


class TestCommandExplanation:
    """Tests for CommandExplanation dataclass."""

    def test_creation_minimal(self):
        exp = CommandExplanation(
            summary="Lists files",
            breakdown=[CommandBreakdownPart(part="ls", explanation="list")],
        )
        assert exp.summary == "Lists files"
        assert len(exp.breakdown) == 1
        assert exp.security_notes is None

    def test_creation_with_security_notes(self):
        exp = CommandExplanation(
            summary="Removes files",
            breakdown=[CommandBreakdownPart(part="rm", explanation="remove")],
            security_notes="Destructive operation",
        )
        assert exp.security_notes == "Destructive operation"


class TestOutputExplanation:
    """Tests for OutputExplanation dataclass."""

    def test_creation_minimal(self):
        exp = OutputExplanation(summary="Shows files", key_findings=["5 files found"])
        assert exp.summary == "Shows files"
        assert exp.key_findings == ["5 files found"]
        assert exp.details is None
        assert exp.next_steps is None

    def test_creation_with_optional_fields(self):
        exp = OutputExplanation(
            summary="Scan results",
            key_findings=["3 hosts up"],
            details="Detailed scan info",
            next_steps=["Run deeper scan"],
        )
        assert exp.details == "Detailed scan info"
        assert exp.next_steps == ["Run deeper scan"]


class TestAgentTask:
    """Tests for AgentTask dataclass."""

    def test_creation_with_defaults(self):
        task = AgentTask(
            task_id="task_1",
            step_number=1,
            total_steps=3,
            description="Test step",
        )
        assert task.task_id == "task_1"
        assert task.command is None
        assert task.dependencies == []
        assert task.status == StepStatus.PENDING
        assert isinstance(task.created_at, datetime)
        assert task.started_at is None

    def test_to_dict_serialization(self):
        task = AgentTask(
            task_id="task_abc",
            step_number=2,
            total_steps=5,
            description="Run scan",
            command="nmap -sn 10.0.0.0/24",
            status=StepStatus.RUNNING,
        )
        d = task.to_dict()
        assert d["task_id"] == "task_abc"
        assert d["step_number"] == 2
        assert d["total_steps"] == 5
        assert d["status"] == "running"
        assert d["command"] == "nmap -sn 10.0.0.0/24"
        assert isinstance(d["created_at"], str)  # isoformat
        assert d["started_at"] is None

    def test_dependencies_default_factory(self):
        t1 = AgentTask(task_id="a", step_number=1, total_steps=1, description="x")
        t2 = AgentTask(task_id="b", step_number=1, total_steps=1, description="y")
        t1.dependencies.append("dep1")
        assert "dep1" not in t2.dependencies


class TestTaskPlan:
    """Tests for TaskPlan dataclass."""

    def test_creation(self):
        step = AgentTask(
            task_id="t1", step_number=1, total_steps=1, description="step 1"
        )
        plan = TaskPlan(
            plan_id="plan_abc",
            original_query="show disk usage",
            analysis="Running df command",
            steps=[step],
        )
        assert plan.plan_id == "plan_abc"
        assert len(plan.steps) == 1
        assert plan.metadata == {}

    def test_to_dict_serialization(self):
        step = AgentTask(
            task_id="t1",
            step_number=1,
            total_steps=1,
            description="step 1",
            command="df -h",
        )
        plan = TaskPlan(
            plan_id="plan_1",
            original_query="disk usage",
            analysis="Checking disk",
            steps=[step],
        )
        d = plan.to_dict()
        assert d["plan_id"] == "plan_1"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["command"] == "df -h"
        assert isinstance(d["created_at"], str)


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_creation_minimal(self):
        result = StepResult(
            task_id="t1",
            step_number=1,
            total_steps=2,
            status=StepStatus.COMPLETED,
        )
        assert result.command is None
        assert result.command_explanation is None
        assert result.output is None
        assert result.execution_time == 0.0

    def test_to_dict_with_explanations(self):
        result = StepResult(
            task_id="t1",
            step_number=1,
            total_steps=1,
            status=StepStatus.COMPLETED,
            command="ls -la",
            command_explanation=CommandExplanation(
                summary="Lists files",
                breakdown=[CommandBreakdownPart(part="ls", explanation="list")],
                security_notes=None,
            ),
            output="total 42\n",
            output_explanation=OutputExplanation(
                summary="Directory listing",
                key_findings=["42 blocks"],
                details=None,
                next_steps=None,
            ),
            return_code=0,
        )
        d = result.to_dict()
        assert d["status"] == "completed"
        assert d["command_explanation"]["summary"] == "Lists files"
        assert len(d["command_explanation"]["breakdown"]) == 1
        assert d["output_explanation"]["key_findings"] == ["42 blocks"]

    def test_to_dict_without_explanations(self):
        result = StepResult(
            task_id="t1",
            step_number=1,
            total_steps=1,
            status=StepStatus.FAILED,
            error="timeout",
        )
        d = result.to_dict()
        assert d["command_explanation"] is None
        assert d["output_explanation"] is None
        assert d["error"] == "timeout"


class TestStreamChunk:
    """Tests for StreamChunk dataclass."""

    def test_creation(self):
        chunk = StreamChunk(
            task_id="t1",
            step_number=1,
            chunk_type="stdout",
            content="hello\n",
        )
        assert chunk.is_final is False
        assert isinstance(chunk.timestamp, datetime)

    def test_to_dict(self):
        chunk = StreamChunk(
            task_id="t1",
            step_number=2,
            chunk_type="return_code",
            content="0",
            is_final=True,
        )
        d = chunk.to_dict()
        assert d["task_id"] == "t1"
        assert d["chunk_type"] == "return_code"
        assert d["is_final"] is True
        assert isinstance(d["timestamp"], str)


class TestOverseerUpdate:
    """Tests for OverseerUpdate dataclass."""

    def test_creation_plan_update(self):
        update = OverseerUpdate(
            update_type="plan",
            plan_id="plan_1",
            total_steps=3,
            content={"analysis": "test"},
        )
        assert update.update_type == "plan"
        assert update.task_id is None
        assert update.step_number is None

    def test_creation_step_update(self):
        update = OverseerUpdate(
            update_type="step_complete",
            plan_id="plan_1",
            task_id="t1",
            step_number=1,
            total_steps=2,
            status="completed",
            content={"output": "done"},
        )
        assert update.status == "completed"

    def test_to_dict(self):
        update = OverseerUpdate(
            update_type="error",
            plan_id="plan_1",
            task_id="t1",
            step_number=1,
            total_steps=1,
            status="failed",
            content={"error": "timeout"},
        )
        d = update.to_dict()
        assert d["update_type"] == "error"
        assert d["content"]["error"] == "timeout"
        assert isinstance(d["timestamp"], str)
