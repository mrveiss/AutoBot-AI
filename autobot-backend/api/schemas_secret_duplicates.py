# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the secret-duplicate admin routes (#17850): counts, vaults, approval ids; no secret id or name."""

from pydantic import BaseModel


class DuplicateGroupStatus(BaseModel):
    """One duplicated ``(owner_vault, name)``: the vault, how many copies, and its open proposal if any.

    No secret id and no name leaves here (#17865): a person acts on a group from its approval, in the Approvals
    inbox, not from this view.
    """

    owner_vault: str
    copy_count: int
    approval_id: str | None = None


class DuplicateStatus(BaseModel):
    """Every duplicated group, in counts. ``group_count == 0`` means the unique-constraint migration can apply."""

    group_count: int
    copy_count: int
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
    remaining: int = 0  # duplicated groups left for another call (the per-request cap)
