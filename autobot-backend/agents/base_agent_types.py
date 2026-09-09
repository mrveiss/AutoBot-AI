# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The data types agents exchange, and the helpers that build and move them.

Extracted verbatim from ``base_agent.py`` (#15950). That module sat at its
grandfathered size ceiling, so nothing could be added to it until something came
out -- and this is what came out, because it is the one part of it with no
dependency on ``BaseAgent`` at all: a request, a response, a health report, and
the factory and serde over them.

``base_agent.py`` re-exports every name defined here, so the forty existing
``from agents.base_agent import ...`` sites keep working unchanged. New code
should import from this module directly.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.status_enums import AgentStatus  # #7504 consolidation


class DeploymentMode(Enum):
    """Agent deployment modes"""

    LOCAL = "local"
    CONTAINER = "container"
    REMOTE = "remote"


# Performance optimization: O(1) lookup for available agent statuses (Issue #326)
AVAILABLE_AGENT_STATUSES = {AgentStatus.HEALTHY, AgentStatus.DEGRADED}


@dataclass
class AgentRequest:
    """Standardized agent request format"""

    request_id: str
    agent_type: str
    action: str
    payload: Dict[str, Any]
    context: Dict[str, Any] | None = None
    priority: str = "normal"  # low, normal, high, urgent
    timeout: float = 30.0
    metadata: Dict[str, Any] | None = None


@dataclass
class AgentResponse:
    """Standardized agent response format"""

    request_id: str
    agent_type: str
    status: str  # success, error, partial
    result: Any
    error: str | None = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "request_id": self.request_id,
            "agent_type": self.agent_type,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
            "metadata": self.metadata or {},
        }


@dataclass
class AgentHealth:
    """Agent health information"""

    agent_type: str
    status: AgentStatus
    deployment_mode: DeploymentMode
    last_heartbeat: datetime
    response_time_ms: float
    success_rate: float
    error_count: int
    resource_usage: Dict[str, Any]
    capabilities: List[str]
    details: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "agent_type": self.agent_type,
            "status": self.status.value,
            "deployment_mode": self.deployment_mode.value,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "response_time_ms": self.response_time_ms,
            "success_rate": self.success_rate,
            "error_count": self.error_count,
            "resource_usage": self.resource_usage,
            "capabilities": self.capabilities,
            "details": self.details or {},
        }


# Utility functions for agent management


def create_agent_request(
    agent_type: str,
    action: str,
    payload: Dict[str, Any],
    context: Dict[str, Any] | None = None,
    priority: str = "normal",
    timeout: float = 30.0,
) -> AgentRequest:
    """Helper function to create standardized agent requests"""
    import uuid

    return AgentRequest(
        request_id=str(uuid.uuid4()),
        agent_type=agent_type,
        action=action,
        payload=payload,
        context=context or {},
        priority=priority,
        timeout=timeout,
        metadata={
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "source": "autobot_orchestrator",
        },
    )


def serialize_agent_request(request: AgentRequest) -> str:
    """Serialize agent request for transmission"""
    return json.dumps(
        {
            "request_id": request.request_id,
            "agent_type": request.agent_type,
            "action": request.action,
            "payload": request.payload,
            "context": request.context,
            "priority": request.priority,
            "timeout": request.timeout,
            "metadata": request.metadata,
        }
    )


def deserialize_agent_request(data: str) -> AgentRequest:
    """Deserialize agent request from transmission"""
    parsed = json.loads(data)
    return AgentRequest(**parsed)


def serialize_agent_response(response: AgentResponse) -> str:
    """Serialize agent response for transmission"""
    return json.dumps(response.to_dict())


def deserialize_agent_response(data: str) -> AgentResponse:
    """Deserialize agent response from transmission"""
    parsed = json.loads(data)
    return AgentResponse(**parsed)
