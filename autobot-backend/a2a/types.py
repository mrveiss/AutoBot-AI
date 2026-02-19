# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Protocol Type Definitions

Issue #961: Core data models aligned with the A2A spec v0.3.
Issue #968: Added TraceContext on Task for distributed tracing + audit.
Ref: https://a2a-protocol.org/latest/
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _utcnow() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class TaskState(str, Enum):
    """A2A task lifecycle states (spec §4.2)."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentSkill:
    """Describes a single skill an agent advertises in its Agent Card."""

    id: str
    name: str
    description: str
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "examples": self.examples,
        }


@dataclass
class AgentCapabilities:
    """Declares which A2A protocol features the agent supports."""

    streaming: bool = False
    push_notifications: bool = False
    state_transition_history: bool = True

    def to_dict(self) -> Dict[str, bool]:
        return {
            "streaming": self.streaming,
            "pushNotifications": self.push_notifications,
            "stateTransitionHistory": self.state_transition_history,
        }


@dataclass
class AgentCard:
    """
    A2A Agent Card (spec §3.1).

    Served at /.well-known/agent.json to advertise this agent's
    identity, capabilities, and skills to other agents.
    """

    name: str
    description: str
    url: str
    version: str
    skills: List[AgentSkill]
    capabilities: AgentCapabilities = field(default_factory=AgentCapabilities)
    provider: Optional[str] = None
    documentation_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "capabilities": self.capabilities.to_dict(),
            "skills": [s.to_dict() for s in self.skills],
        }
        if self.provider:
            d["provider"] = {"organization": self.provider}
        if self.documentation_url:
            d["documentationUrl"] = self.documentation_url
        return d


@dataclass
class TaskArtifact:
    """An output artifact produced by a task."""

    artifact_type: str  # "text", "json", "error"
    content: Any
    created_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.artifact_type,
            "content": self.content,
            "createdAt": self.created_at,
        }


@dataclass
class TaskStatus:
    """Represents the current status of a task."""

    state: TaskState
    message: Optional[str] = None
    timestamp: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "state": self.state.value,
            "timestamp": self.timestamp,
        }
        if self.message:
            d["message"] = self.message
        return d


@dataclass
class Task:
    """
    A2A Task (spec §4).

    Represents a unit of work submitted to this agent.
    trace_context carries the distributed trace for audit and observability.
    """

    id: str
    status: TaskStatus
    input: str
    context: Optional[Dict[str, Any]] = None
    artifacts: List[TaskArtifact] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    # Issue #968: distributed tracing — set on task creation
    trace_context: Optional["TraceContext"] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "status": self.status.to_dict(),
            "input": self.input,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.trace_context:
            d["trace"] = {
                "traceId": self.trace_context.trace_id,
                "callerId": self.trace_context.caller_id,
            }
        return d


# Re-export TraceContext so callers can import from a2a.types
from .tracing import TraceContext as TraceContext  # noqa: E402,F401
