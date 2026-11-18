# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the org tier column admin routes (#19997)."""

from pydantic import BaseModel


class OrgTierColumnStatus(BaseModel):
    """Whether the column is still in this database."""

    present: bool


class OrgTierColumnRequestResponse(BaseModel):
    """The approval a proposal created."""

    approval_id: str
    status: str
    action: str
