# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Distributed Tracing — trace context propagation.

Issue #968: Addresses the observability blind spot identified in the A2A
security research: without trace IDs across agent calls, auditing who
initiated what is a manual, fragmented task.

Each A2A task is assigned a trace_id on receipt.  The trace_id is:
  - Returned in the task response (X-A2A-Trace-Id header + body field)
  - Stored on the Task object
  - Passed to the AgentOrchestrator as context['a2a_trace_id']
  - Included in every audit log entry for the task

Trace ID format: 32 hex chars (UUID4 without dashes) — compatible with
OpenTelemetry W3C Trace Context trace-id format.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TraceEvent:
    """A single timestamped event in a task trace."""

    event: str
    timestamp: float = field(default_factory=time.time)
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "event": self.event,
            "timestamp": self.timestamp,
        }
        if self.data:
            d["data"] = self.data
        return d


@dataclass
class TraceContext:
    """
    Trace context attached to an A2A task.

    Carries trace_id, caller_id, and an ordered list of events that record
    every state transition and significant operation during task execution.
    """

    trace_id: str
    caller_id: str
    events: List[TraceEvent] = field(default_factory=list)

    def record(self, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Append a timestamped event to the trace."""
        self.events.append(TraceEvent(event=event, data=data))
        logger.debug("A2A trace %s: %s", self.trace_id[:8], event)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "caller_id": self.caller_id,
            "events": [e.to_dict() for e in self.events],
        }


def new_trace_id() -> str:
    """Generate a W3C-compatible 32-hex-char trace ID."""
    return uuid.uuid4().hex


def extract_caller_id(
    a2a_agent_id: Optional[str],
    jwt_subject: Optional[str],
    remote_addr: Optional[str],
) -> str:
    """
    Determine the caller identity from available request signals.

    Priority:
      1. A2A-Agent-Id header (explicit agent identification per spec)
      2. JWT sub claim (authenticated user)
      3. remote_addr fallback (IP-based, least trustworthy)
      4. 'anonymous' if nothing is available

    Args:
        a2a_agent_id: Value of the X-A2A-Agent-Id request header, if present.
        jwt_subject:  Subject from a validated JWT token, if present.
        remote_addr:  Client IP address from the request.

    Returns:
        A non-empty string identifying the caller.
    """
    if a2a_agent_id:
        return f"agent:{a2a_agent_id}"
    if jwt_subject:
        return f"user:{jwt_subject}"
    if remote_addr:
        return f"ip:{remote_addr}"
    return "anonymous"
