# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A (Agent2Agent) Protocol Module

Issue #961: Phase 1 POC implementing the Agent2Agent protocol for
cross-agent communication. A2A is the emerging industry standard
(Google → Linux Foundation, v0.3, 150+ org backing) for inter-agent
communication, complementing MCP (agent-to-tool).

Issue #968: Security cards (HMAC identity), distributed tracing,
capability verification, rate limiting, audit log.

Ref: https://a2a-protocol.org/latest/
"""

from .agent_card import build_agent_card
from .capability_verifier import CapabilityReport, verify_local_card, verify_remote_card
from .security import SecurityCardSigner
from .task_manager import TaskManager, get_task_manager
from .tracing import TraceContext, extract_caller_id, new_trace_id
from .types import AgentCard, AgentSkill, Task, TaskArtifact, TaskState, TaskStatus

__all__ = [
    "AgentCard",
    "AgentSkill",
    "Task",
    "TaskArtifact",
    "TaskState",
    "TaskStatus",
    "TaskManager",
    "get_task_manager",
    "build_agent_card",
    "SecurityCardSigner",
    "TraceContext",
    "extract_caller_id",
    "new_trace_id",
    "CapabilityReport",
    "verify_local_card",
    "verify_remote_card",
]
