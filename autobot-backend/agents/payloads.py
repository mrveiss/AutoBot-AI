# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Typed agent payload models (#6703).

Before this module, every _build_*_response / _build_*_payload helper
invented its own ad-hoc Dict[str, Any] shape with hardcoded "status":
"success" / "error" strings.  This file provides:

  AgentStatus  — canonical enum replacing those string literals
  BaseAgentPayload — Pydantic base with the fields every payload shares
  Domain payloads — one per agent family, extending the base

Usage pattern (callers keep returning Dict so the public API is unchanged):

    from agents.payloads import AgentStatus, ChatPayload

    def _build_chat_payload(self, response_text: str, response: Any) -> dict:
        return ChatPayload(
            status=AgentStatus.SUCCESS,
            agent_type="chat",
            model_used=self.model_name,
            response=response_text,
            response_text=response_text,
            token_usage=getattr(response, "usage", {}),
        ).model_dump()

The dict returned by .model_dump() has the same keys as the old hand-built
dicts, so the API contract is preserved while callers and IDEs benefit from
typed construction — shape errors surface at edit time not at runtime.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class AgentStatus(str, Enum):
    """Canonical status values for all agent payloads.

    Replaces hardcoded "status": "success" / "error" / "warning" literals
    scattered across 25+ _build_*_response helpers.
    """

    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    DISABLED = "disabled"


class BaseAgentPayload(BaseModel):
    """Fields shared by every agent payload dict.

    All domain-specific payloads extend this model.  Callers are expected
    to call .model_dump() before returning to preserve the existing
    Dict[str, Any] API contract.
    """

    model_config = ConfigDict(extra="allow")

    status: AgentStatus
    agent_type: str
    model_used: str | None = None
    metadata: dict[str, Any] | None = None


class ChatPayload(BaseAgentPayload):
    """Payload shape for ChatAgent._build_chat_payload."""

    response: str = ""
    response_text: str = ""
    token_usage: dict[str, Any] | None = None


class KnowledgeQueryPayload(BaseAgentPayload):
    """Payload shape for KnowledgeRetrievalAgent._build_query_payload."""

    query: str = ""
    documents_found: int = 0
    documents: list[dict[str, Any]] = []
    summary: str = ""
    processing_time: float = 0.0
    is_question: bool = False
    similarity_threshold: float = 0.0


class CommandPayload(BaseAgentPayload):
    """Payload shape for EnhancedSystemCommandsAgent._build_command_payload."""

    command: str = ""
    explanation: str = ""
    is_safe: bool = False
    security_concerns: list[str] = []
    suggested_alternatives: list[str] = []


class RAGPayload(BaseAgentPayload):
    """Payload shape for RAGAgent._build_rag_success_response."""

    synthesized_response: str = ""
    confidence_score: float = 0.8
    document_analysis: dict[str, Any] | None = None
    sources_used: list[str] = []
