# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response schema for the read-only chat session trace (#19963)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class TraceApproval(BaseModel):
    """The approval a held call points at, and its state as looked up now."""

    id: str
    kind: Literal["gate", "terminal"]
    state: str


class TraceToolCall(BaseModel):
    """One tool call a turn recorded."""

    id: Optional[str] = None
    timestamp: Optional[str] = None
    tool: str
    verdict: Literal["ran", "held", "refused", "unknown"]
    params: Dict[str, Any]
    output: str
    approval: Optional[TraceApproval] = None
    result_returned: Literal["no", "unknown"]


class TraceIteration(BaseModel):
    """One continuation iteration of a turn; ``iteration`` is None for untagged entries."""

    iteration: Optional[int] = None
    model: Optional[str] = None
    replied: bool
    tool_calls: List[TraceToolCall]


class TraceTurn(BaseModel):
    """One user message and what the assistant did in answer."""

    turn: int
    user_message_id: Optional[str] = None
    started_at: Optional[str] = None
    model: Optional[str] = None
    iterations: List[TraceIteration]


class SessionTraceData(BaseModel):
    """The trace of one session."""

    session_id: str
    turns: List[TraceTurn]
