# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response shapes of the agent-ledger read APIs (#18391).

One set for both surfaces -- the Company OS view in the user backend and the
admin view in the SLM backend -- so a row means the same thing in each and the
generated TypeScript types do not drift between them.

Every list endpoint answers with a body whose emptiness is a fact: ``[]`` means
the ledger was read and holds nothing. A ledger that could not be read is
``LedgerUnavailable`` under HTTP 503, never an empty list.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LedgerUnavailable(BaseModel):
    """The typed 503 body: the source could not be read, which is not 'nothing there'."""

    error: Literal["ledger_unavailable"] = "ledger_unavailable"
    source: str = Field(description="Which store could not be read (claims, waitlists, dev_loop, events)")
    detail: str


class ClaimRow(BaseModel):
    scope: str
    kind: str
    agent_id: str
    task_id: str
    mode: str
    intent: str
    acquired_at: str
    expires_at: str
    renewals: int = Field(0, description="Explicit renewals since the claim was acquired")
    company_id: str | None = Field(default=None, description="Stamped at write time; null = install-wide or legacy")


class WaiterRow(BaseModel):
    scope: str
    position: int = Field(description="1-based position in the scope's queue")
    agent_id: str
    task_id: str
    mode: str
    intent: str
    priority: int
    joined_at: str
    expires_at: str
    company_id: str | None = Field(default=None, description="Stamped at write time; null = install-wide or legacy")


class ClaimsResponse(BaseModel):
    claims: list[ClaimRow]
    count: int


class WaitlistsResponse(BaseModel):
    waiters: list[WaiterRow]
    count: int


class ContentionRow(BaseModel):
    scope: str
    kind: str = Field(description="provider, cpu or queue")
    holders: list[ClaimRow]
    waiters: list[WaiterRow]
    contended: bool = Field(description="True when anyone is queued behind this resource")


class ContentionResponse(BaseModel):
    resources: list[ContentionRow]
    count: int


class ActivityRow(BaseModel):
    at: str
    type: str
    scope: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    detail: str = ""


class ActivityResponse(BaseModel):
    activity: list[ActivityRow]
    count: int


class ConflictRow(BaseModel):
    at: str
    kind: Literal["release_refused", "claim_expired", "yield_unanswered", "claim_lapsed_during_action"]
    scope: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    other_agent_id: str | None = Field(default=None, description="The holder, for a refused release")
    detail: str = ""


class ConflictsResponse(BaseModel):
    conflicts: list[ConflictRow]
    count: int


class PresenceRow(BaseModel):
    kind: str
    tenant_id: str | None
    name: str
    busy: bool
    detail: str | None = None
    last_seen: float


class PresenceResponse(BaseModel):
    agents: list[PresenceRow]
    count: int


class PeerMessageRow(BaseModel):
    """Pending peer messages for one recipient. Metadata only -- never the content."""

    recipient_kind: str
    recipient_name: str
    pending: int
    senders: list[str]
    oldest_at: float


class PeerMessagesResponse(BaseModel):
    recipients: list[PeerMessageRow]
    count: int


class IdleSubscriberRow(BaseModel):
    subscriber: str
    target_kind: str
    target_name: str
    since: float
    expires_at: float


class IdleSubscribersResponse(BaseModel):
    subscribers: list[IdleSubscriberRow]
    count: int


class DevLoopActionRow(BaseModel):
    issue: int
    intent: str
    outcome: str
    estimated_tokens: int
    reason: str
    at: str


class DevLoopHistoryResponse(BaseModel):
    issue: int
    actions: list[DevLoopActionRow]
    count: int


class DevLoopIssuesResponse(BaseModel):
    issues: list[int]
    count: int


class LedgerSourceStatus(BaseModel):
    """What the SLM can and cannot read, so a screen never shows a gap as 'none'."""

    source: str
    reachable: bool
    reason: str = ""


class LedgerSourcesResponse(BaseModel):
    sources: list[LedgerSourceStatus]
