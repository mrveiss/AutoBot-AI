# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Event Stream Type Definitions

Typed events for the agent event stream, inspired by Manus architecture.
Each event type has a specific purpose and content schema.

Event Types:
- MESSAGE: User inputs and agent responses
- ACTION: Tool calls / function calling
- OBSERVATION: Execution results from tools
- PLAN: Task step planning from Planner module
- KNOWLEDGE: Task-relevant knowledge from Knowledge module
- DATASOURCE: API documentation and data sources
- SYSTEM: System events (startup, shutdown, errors)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional
import uuid
import json


class EventType(Enum):
    """Typed events for the agent event stream (Manus-inspired)"""

    MESSAGE = auto()  # User inputs and agent responses
    ACTION = auto()  # Tool calls / function calling
    OBSERVATION = auto()  # Execution results from tools
    PLAN = auto()  # Task step planning from Planner module
    KNOWLEDGE = auto()  # Task-relevant knowledge from Knowledge module
    DATASOURCE = auto()  # API documentation and data sources
    SYSTEM = auto()  # System events (startup, shutdown, errors)


@dataclass
class AgentEvent:
    """Standard event structure for the event stream"""

    # Identity
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.MESSAGE

    # Timing
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Content
    content: dict = field(default_factory=dict)

    # Source tracking
    source: str = "user"  # user, agent, planner, knowledge_module, tool, system
    agent_id: Optional[str] = None

    # Correlation for multi-turn conversations
    correlation_id: Optional[str] = None  # Links related events
    parent_event_id: Optional[str] = None  # For nested events (action → observation)

    # Task context
    task_id: Optional[str] = None  # Current task being executed
    step_number: Optional[int] = None  # Current step in plan

    # Metadata
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for Redis storage"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.name,
            "timestamp": self.timestamp.isoformat(),
            "content": self.content,
            "source": self.source,
            "agent_id": self.agent_id,
            "correlation_id": self.correlation_id,
            "parent_event_id": self.parent_event_id,
            "task_id": self.task_id,
            "step_number": self.step_number,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentEvent":
        """Deserialize from Redis storage"""
        return cls(
            event_id=data["event_id"],
            event_type=EventType[data["event_type"]],
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if isinstance(data["timestamp"], str)
                else data["timestamp"]
            ),
            content=data.get("content", {}),
            source=data.get("source", "unknown"),
            agent_id=data.get("agent_id"),
            correlation_id=data.get("correlation_id"),
            parent_event_id=data.get("parent_event_id"),
            task_id=data.get("task_id"),
            step_number=data.get("step_number"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "AgentEvent":
        """Deserialize from JSON string"""
        return cls.from_dict(json.loads(json_str))

    def __repr__(self) -> str:
        return (
            f"AgentEvent(id={self.event_id[:8]}..., "
            f"type={self.event_type.name}, "
            f"source={self.source}, "
            f"task={self.task_id})"
        )


# =============================================================================
# Content Schemas for Each Event Type
# =============================================================================


@dataclass
class MessageContent:
    """Content schema for MESSAGE events"""

    role: str  # "user" or "assistant"
    text: str
    attachments: list[dict] = field(default_factory=list)

    # For assistant messages
    tool_calls_made: list[str] = field(default_factory=list)
    confidence: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "text": self.text,
            "attachments": self.attachments,
            "tool_calls_made": self.tool_calls_made,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MessageContent":
        return cls(
            role=data.get("role", "user"),
            text=data.get("text", ""),
            attachments=data.get("attachments", []),
            tool_calls_made=data.get("tool_calls_made", []),
            confidence=data.get("confidence"),
        )


@dataclass
class ActionContent:
    """Content schema for ACTION events (tool calls)"""

    tool_name: str
    arguments: dict
    tool_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Execution context
    is_parallel: bool = False
    parallel_group_id: Optional[str] = None  # Groups parallel actions
    depends_on: list[str] = field(default_factory=list)  # Action IDs this depends on

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "tool_id": self.tool_id,
            "is_parallel": self.is_parallel,
            "parallel_group_id": self.parallel_group_id,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActionContent":
        return cls(
            tool_name=data.get("tool_name", ""),
            arguments=data.get("arguments", {}),
            tool_id=data.get("tool_id", str(uuid.uuid4())),
            is_parallel=data.get("is_parallel", False),
            parallel_group_id=data.get("parallel_group_id"),
            depends_on=data.get("depends_on", []),
        )


@dataclass
class ObservationContent:
    """Content schema for OBSERVATION events (tool results)"""

    action_id: str  # Links to parent ACTION event
    tool_name: str

    # Result
    success: bool
    result: Any = None
    error: Optional[str] = None

    # Performance
    execution_time_ms: float = 0.0
    device_used: Optional[str] = None  # For NPU/GPU operations

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "tool_name": self.tool_name,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "device_used": self.device_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ObservationContent":
        return cls(
            action_id=data.get("action_id", ""),
            tool_name=data.get("tool_name", ""),
            success=data.get("success", False),
            result=data.get("result"),
            error=data.get("error"),
            execution_time_ms=data.get("execution_time_ms", 0.0),
            device_used=data.get("device_used"),
        )


@dataclass
class PlanContent:
    """Content schema for PLAN events (from Planner module)"""

    task_description: str
    steps: list[dict]  # [{step_num, description, status, dependencies}]
    current_step: int
    total_steps: int

    # Status tracking
    status: str = "planning"  # planning, in_progress, completed, blocked, failed
    reflection: Optional[str] = None  # Current state assessment

    # Updates
    is_update: bool = False  # True if updating existing plan
    changes_made: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_description": self.task_description,
            "steps": self.steps,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "status": self.status,
            "reflection": self.reflection,
            "is_update": self.is_update,
            "changes_made": self.changes_made,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanContent":
        return cls(
            task_description=data.get("task_description", ""),
            steps=data.get("steps", []),
            current_step=data.get("current_step", 0),
            total_steps=data.get("total_steps", 0),
            status=data.get("status", "planning"),
            reflection=data.get("reflection"),
            is_update=data.get("is_update", False),
            changes_made=data.get("changes_made", []),
        )


@dataclass
class KnowledgeContent:
    """Content schema for KNOWLEDGE events (from Knowledge module)"""

    knowledge_items: list[dict]  # Retrieved knowledge
    query: str  # What triggered the retrieval

    # Relevance scoring
    scope: str = "general"  # python, frontend, database, general
    relevance_score: float = 0.0

    # Source tracking
    source_type: str = "chromadb"  # chromadb, memory_mcp, file_system
    document_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "knowledge_items": self.knowledge_items,
            "query": self.query,
            "scope": self.scope,
            "relevance_score": self.relevance_score,
            "source_type": self.source_type,
            "document_ids": self.document_ids,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeContent":
        return cls(
            knowledge_items=data.get("knowledge_items", []),
            query=data.get("query", ""),
            scope=data.get("scope", "general"),
            relevance_score=data.get("relevance_score", 0.0),
            source_type=data.get("source_type", "chromadb"),
            document_ids=data.get("document_ids", []),
        )


# =============================================================================
# Helper Functions
# =============================================================================


def create_message_event(
    role: str,
    text: str,
    task_id: Optional[str] = None,
    source: str = "user",
    **kwargs,
) -> AgentEvent:
    """Helper to create a MESSAGE event"""
    content = MessageContent(role=role, text=text, **kwargs)
    return AgentEvent(
        event_type=EventType.MESSAGE,
        content=content.to_dict(),
        source=source,
        task_id=task_id,
    )


def create_action_event(
    tool_name: str,
    arguments: dict,
    task_id: Optional[str] = None,
    is_parallel: bool = False,
    parallel_group_id: Optional[str] = None,
    depends_on: Optional[list[str]] = None,
) -> AgentEvent:
    """Helper to create an ACTION event"""
    content = ActionContent(
        tool_name=tool_name,
        arguments=arguments,
        is_parallel=is_parallel,
        parallel_group_id=parallel_group_id,
        depends_on=depends_on or [],
    )
    return AgentEvent(
        event_type=EventType.ACTION,
        content=content.to_dict(),
        source="agent",
        task_id=task_id,
    )


def create_observation_event(
    action_id: str,
    tool_name: str,
    success: bool,
    result: Any = None,
    error: Optional[str] = None,
    execution_time_ms: float = 0.0,
    task_id: Optional[str] = None,
    device_used: Optional[str] = None,
) -> AgentEvent:
    """Helper to create an OBSERVATION event"""
    content = ObservationContent(
        action_id=action_id,
        tool_name=tool_name,
        success=success,
        result=result,
        error=error,
        execution_time_ms=execution_time_ms,
        device_used=device_used,
    )
    return AgentEvent(
        event_type=EventType.OBSERVATION,
        content=content.to_dict(),
        source="tool",
        task_id=task_id,
        parent_event_id=action_id,
    )


def create_plan_event(
    task_description: str,
    steps: list[dict],
    current_step: int,
    total_steps: int,
    status: str = "planning",
    task_id: Optional[str] = None,
    is_update: bool = False,
    changes_made: Optional[list[str]] = None,
    reflection: Optional[str] = None,
) -> AgentEvent:
    """Helper to create a PLAN event"""
    content = PlanContent(
        task_description=task_description,
        steps=steps,
        current_step=current_step,
        total_steps=total_steps,
        status=status,
        is_update=is_update,
        changes_made=changes_made or [],
        reflection=reflection,
    )
    return AgentEvent(
        event_type=EventType.PLAN,
        content=content.to_dict(),
        source="planner",
        task_id=task_id,
        step_number=current_step,
    )


def create_knowledge_event(
    knowledge_items: list[dict],
    query: str,
    scope: str = "general",
    relevance_score: float = 0.0,
    source_type: str = "chromadb",
    task_id: Optional[str] = None,
    document_ids: Optional[list[str]] = None,
) -> AgentEvent:
    """Helper to create a KNOWLEDGE event"""
    content = KnowledgeContent(
        knowledge_items=knowledge_items,
        query=query,
        scope=scope,
        relevance_score=relevance_score,
        source_type=source_type,
        document_ids=document_ids or [],
    )
    return AgentEvent(
        event_type=EventType.KNOWLEDGE,
        content=content.to_dict(),
        source="knowledge_module",
        task_id=task_id,
    )


def create_system_event(
    event_name: str,
    details: dict,
    level: str = "info",  # info, warning, error
) -> AgentEvent:
    """Helper to create a SYSTEM event"""
    return AgentEvent(
        event_type=EventType.SYSTEM,
        content={
            "event_name": event_name,
            "details": details,
            "level": level,
        },
        source="system",
    )
