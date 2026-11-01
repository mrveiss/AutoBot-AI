# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the install cleanup proposal admin routes (#20567)."""

from pydantic import BaseModel


class CleanupStatus(BaseModel):
    """What one cleanup would remove on this node. Counts and names only, never a file's contents."""

    count: int
    detail: str
    refused: str | None = None


class CleanupRequestResponse(BaseModel):
    """The approval a proposal created."""

    approval_id: str
    status: str
    action: str
