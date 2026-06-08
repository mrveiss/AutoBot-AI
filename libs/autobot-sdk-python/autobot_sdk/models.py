# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Typed Pydantic models matching the AutoBot REST API response shapes."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Generic envelope
# ---------------------------------------------------------------------------


class DataResponse(BaseModel, Generic[T]):
    """Mirrors the server-side DataResponse envelope from schemas_common.py."""

    success: bool = True
    data: T | None = None
    message: str | None = None
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: str | None = None


class Session(BaseModel):
    session_id: str
    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    message_count: int | None = None
    metadata: dict[str, Any] | None = None


class SessionList(BaseModel):
    sessions: list[Session] = []
    total: int | None = None


class SessionMessages(BaseModel):
    session_id: str
    messages: list[ChatMessage] = []
    total: int | None = None


class SessionCreate(BaseModel):
    session_id: str
    title: str | None = None


class SessionUpdate(BaseModel):
    session_id: str
    success: bool = True


class SessionDelete(BaseModel):
    session_id: str
    success: bool = True


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class AgentHealth(BaseModel):
    status: str
    version: str | None = None
    uptime: float | None = None
    components: dict[str, Any] | None = None


class AgentConfig(BaseModel):
    enabled: bool | None = None
    personality: str | None = None
    model: str | None = None
    settings: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Knowledge
# ---------------------------------------------------------------------------


class KnowledgeEntry(BaseModel):
    id: str | None = None
    content: str | None = None
    source: str | None = None
    category: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] | None = None


class KnowledgeStats(BaseModel):
    total_entries: int | None = None
    categories: dict[str, int] | None = None
    last_updated: str | None = None


class KnowledgeAddResult(BaseModel):
    success: bool = True
    id: str | None = None
    message: str | None = None


class KnowledgeSearchResult(BaseModel):
    results: list[KnowledgeEntry] = []
    total: int | None = None
    query: str | None = None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class AnalyticsUsage(BaseModel):
    total_requests: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    period: str | None = None


class AnalyticsPerformance(BaseModel):
    avg_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    error_rate: float | None = None
    period: str | None = None
