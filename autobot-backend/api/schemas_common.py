# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared cross-domain Pydantic response schemas for AutoBot API endpoints.

These are truly generic types used across multiple unrelated domains.
Domain-specific schemas live in:
  schemas_terminal.py    - Terminal*, AgentTerminal*, SSH*, etc.
  schemas_analytics.py   - Analytics*, Cost*, Budget*, Usage*, Metrics*, etc.
  schemas_knowledge.py   - Knowledge* schemas
  schemas_agent.py       - Agent*, Memory*, LLM* schemas
  schemas_system.py      - System*, NPU*, WakeWord*, FeatureFlag*, etc.
  schemas_workflows.py   - Workflow*, Registry*, RUM*, Elevation*, AdvancedControl*, etc.
  schemas_code.py        - CodeReview*, Git*, Skills*, Database*, Template*, etc.
"""

from typing import Any, Dict, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Generic / reusable (used across multiple unrelated domains)
# ---------------------------------------------------------------------------


class SuccessMessageResponse(BaseModel):
    """Base for endpoints that always return success: bool + message: str."""

    success: bool
    message: str


class SuccessDataResponse(BaseModel):
    """Base for endpoints that return success, message, and an optional data dict."""

    success: bool
    message: str
    data: Dict[str, Any] | None = None

class SuccessResponse(BaseModel):
    """Minimal success/failure envelope used by several endpoints."""

    success: bool
    message: str | None = None


# ---------------------------------------------------------------------------
# Terminal session schemas  (terminal.py — session lifecycle)
# ---------------------------------------------------------------------------


class DataResponse(BaseModel, Generic[T]):
    """Generic envelope returned by create_success_response() helpers.

    Covers all endpoints that delegate to utils.response_helpers.create_success_response,
    which always produces {"success": True, "data": ..., "message": ..., "timestamp": ...}.

    Use DataResponse[ConcreteType] on endpoints where the data payload shape is known;
    bare DataResponse (equivalent to DataResponse[Any]) remains valid for opaque payloads.
    """

    # success defaults to True because every callsite of create_success_response
    # writes a success envelope by definition. Without the default, bare
    # DataResponse(data=...) callers (api/onboarding.py, api/playwright.py)
    # crashed at request time — see #6609.
    success: bool = True
    data: T | None = None
    message: str | None = None
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# agent.py — simple message / approval responses
# ---------------------------------------------------------------------------


class UsageRecordResponse(BaseModel):
    """Response for POST /usage/record."""

    recorded: bool
    cost_usd: float
    record_id: str | None = None


class AgentMessageResponse(BaseModel):
    """Response for /goal, /pause, /resume — plain {"message": str}.

    Moved from schemas_agent.py (#5935): used by both agent.py and logs.py,
    making it cross-domain.
    """

    message: str


# ---------------------------------------------------------------------------
# structured_thinking_mcp.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------
