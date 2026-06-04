# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Type definitions for the Overseer Agent system.

Defines data structures for task decomposition, step execution,
and command explanations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


class TaskStatus(Enum):
    """Status of a task in the execution pipeline."""

    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    STREAMING = "streaming"  # For long-running commands with live output
    EXPLAINING = "explaining"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(Enum):
    """Status of an individual step."""

    PENDING = "pending"
    RUNNING = "running"
    STREAMING = "streaming"  # Output being streamed
    WAITING_EXPLANATION = "waiting_explanation"
    EXPLAINING = "explaining"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CommandBreakdownPart:
    """Individual part of a command breakdown explanation."""

    part: str  # The command part (e.g., "nmap", "-sn", "192.168.1.0/24")
    explanation: str  # What this part does


@dataclass
class CommandExplanation:
    """Part 1: Explanation of what the command does."""

    summary: str  # Brief description of what the command does
    breakdown: List[CommandBreakdownPart]  # Individual parts explained
    security_notes: str | None = None  # Any security implications


@dataclass
class OutputExplanation:
    """Part 2: Explanation of command output."""

    summary: str  # Brief description of what the output shows
    key_findings: List[str]  # Important discoveries from output
    details: str | None = None  # Detailed explanation if needed
    next_steps: List[str] | None = None  # Suggested follow-up actions


@dataclass
class AgentTask:
    """
    A single task to be executed by a StepExecutorAgent.

    Represents one atomic unit of work in the task sequence.
    """

    task_id: str
    step_number: int
    total_steps: int
    description: str  # What this step accomplishes
    command: str | None = None  # The command to execute (if applicable)
    expected_outcome: str | None = None
    dependencies: List[str] = field(default_factory=list)  # Task IDs this depends on
    status: StepStatus = StepStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "step_number": self.step_number,
            "total_steps": self.total_steps,
            "description": self.description,
            "command": self.command,
            "expected_outcome": self.expected_outcome,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "error": self.error,
        }


@dataclass
class TaskPlan:
    """
    Result of task decomposition by the OverseerAgent.

    Contains the analysis and planned steps for a user query.
    """

    plan_id: str
    original_query: str
    analysis: str  # How we're approaching this query
    steps: List[AgentTask]
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "plan_id": self.plan_id,
            "original_query": self.original_query,
            "analysis": self.analysis,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class StepResult:
    """
    Result of executing a single step.

    Contains command, output, and both parts of explanations.
    """

    task_id: str
    step_number: int
    total_steps: int
    status: StepStatus
    command: str | None = None
    command_explanation: CommandExplanation | None = None
    output: str | None = None
    output_explanation: OutputExplanation | None = None
    return_code: int | None = None
    execution_time: float = 0.0
    error: str | None = None
    is_streaming: bool = False
    stream_complete: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "step_number": self.step_number,
            "total_steps": self.total_steps,
            "status": self.status.value,
            "command": self.command,
            "command_explanation": (
                {
                    "summary": self.command_explanation.summary,
                    "breakdown": [
                        {"part": p.part, "explanation": p.explanation} for p in self.command_explanation.breakdown
                    ],
                    "security_notes": self.command_explanation.security_notes,
                }
                if self.command_explanation
                else None
            ),
            "output": self.output,
            "output_explanation": (
                {
                    "summary": self.output_explanation.summary,
                    "key_findings": self.output_explanation.key_findings,
                    "details": self.output_explanation.details,
                    "next_steps": self.output_explanation.next_steps,
                }
                if self.output_explanation
                else None
            ),
            "return_code": self.return_code,
            "execution_time": self.execution_time,
            "error": self.error,
            "is_streaming": self.is_streaming,
            "stream_complete": self.stream_complete,
        }


@dataclass
class StreamChunk:
    """
    A chunk of streaming output for long-running commands.

    Sent in real-time while command is executing.
    """

    task_id: str
    step_number: int
    chunk_type: str  # "stdout", "stderr", "status"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    is_final: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "step_number": self.step_number,
            "chunk_type": self.chunk_type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "is_final": self.is_final,
        }


@dataclass
class OverseerUpdate:
    """
    Update message sent from OverseerAgent to frontend.

    Used for real-time progress tracking.
    """

    update_type: str  # "plan", "step_start", "stream", "step_complete", "error"
    plan_id: str | None = None
    task_id: str | None = None
    step_number: int | None = None
    total_steps: int | None = None
    status: str | None = None
    content: Any | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "update_type": self.update_type,
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "step_number": self.step_number,
            "total_steps": self.total_steps,
            "status": self.status,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }
