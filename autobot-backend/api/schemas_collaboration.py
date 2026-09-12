# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Schemas for the collaboration event history and invitation list/respond
endpoints (#16460). Split from schemas_agent.py rather than added to it --
that file is grandfathered at a frozen line-count ceiling (#14236) and may
not grow.
"""

from typing import List

from pydantic import BaseModel


class CollabEventResponse(BaseModel):
    """One persisted collaboration event (#16460)."""

    id: str
    session_id: str
    kind: str
    user_id: str | None
    username: str | None
    payload: dict
    timestamp: str


class SessionEventsResponse(BaseModel):
    """List-recent response for GET /{session_id}/events (#16460)."""

    session_id: str
    events: List[CollabEventResponse]
    has_more: bool


class PendingInvitationResponse(BaseModel):
    """One pending invitation, as returned by GET /invitations/mine (#16460)."""

    session_id: str
    from_user_id: str
    permission: str
    invited_at: str
    expires_at: str | None = None


class MyInvitationsResponse(BaseModel):
    """Response for GET /invitations/mine (#16460)."""

    invitations: List[PendingInvitationResponse]


class InvitationRespondRequest(BaseModel):
    """Request body for POST /{session_id}/invitations/respond (#16460)."""

    accept: bool


class InvitationRespondResponse(BaseModel):
    """Response for POST /{session_id}/invitations/respond (#16460)."""

    success: bool
    session_id: str
    accepted: bool
    permission: str | None = None
