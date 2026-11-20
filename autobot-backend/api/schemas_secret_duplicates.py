# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the secret-duplicate admin routes (#17850). Ids and counts only -- never a name or a value."""

from pydantic import BaseModel


class DuplicateGroupStatus(BaseModel):
    """One duplicated ``(owner_vault, name)``: the vault reference and the ids of its copies."""

    owner_vault: str
    secret_ids: list[str]


class DuplicateStatus(BaseModel):
    """Every duplicated group. Empty means the unique-constraint migration can apply."""

    groups: list[DuplicateGroupStatus]


class DuplicateProposal(BaseModel):
    """What one group produced: the approval raised, or why none was (a proposal already stands)."""

    approval_id: str | None
    reason: str
    copies: int
    skipped: bool


class DuplicateRequestResponse(BaseModel):
    """The proposals one request raised."""

    proposals: list[DuplicateProposal]
