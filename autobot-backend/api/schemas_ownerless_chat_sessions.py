# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the ownerless chat session admin routes (#20030)."""

from typing import List

from pydantic import BaseModel, Field


class OwnerlessChatSessionsReport(BaseModel):
    """Sessions with no recorded owner, and those whose owner could not be read."""

    count: int
    session_ids: List[str]
    unreadable: List[str]


class OwnerlessChatSessionRequest(BaseModel):
    """The session and the owner a human has picked for it."""

    session_id: str = Field(min_length=1, max_length=255)
    owner: str = Field(min_length=1, max_length=255)


class OwnerlessChatSessionRequestResponse(BaseModel):
    """The approval a proposal created."""

    approval_id: str
    status: str
    action: str
