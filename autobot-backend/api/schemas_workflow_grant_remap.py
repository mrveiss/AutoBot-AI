# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the workflow grant subject remap proposal (#22180)."""

from typing import List

from pydantic import BaseModel


class UnmappedGrant(BaseModel):
    """A grant row whose subject names no active user; left untouched."""

    workflow_id: str
    subject: str


class GrantRemapProposalResponse(BaseModel):
    """The approval a proposal created, and what it leaves out."""

    approval_id: str
    status: str
    action: str
    mapped: int
    unmapped: List[UnmappedGrant]
