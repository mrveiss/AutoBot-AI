# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response shapes of the stale code-sync file cleanup routes (#22033)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StaleFileOut(BaseModel):
    """A file offered for removal: byte-identical to a version git tracked at that path."""

    old_target: str
    role: str
    path: str
    size_bytes: int
    modified_at: datetime
    blob: str


class KeptFileOut(BaseModel):
    """A file under an old target that is NOT offered, and why."""

    old_target: str
    path: str
    reason: str


class StaleFilesListing(BaseModel):
    """The read-only listing for one node; ``error`` set means it could not be trusted and nothing is offered."""

    node_id: str
    commit: str | None
    stale: list[StaleFileOut]
    kept: list[KeptFileOut]
    total_stale: int
    error: str | None = None


class StaleFilesProposed(BaseModel):
    """One proposal per old sync location: the backend's approval, and how many of the found files it lists."""

    old_target: str
    approval_id: str
    status: str
    created: bool
    proposed: int
    total_found: int


class StaleFilesProposalResponse(BaseModel):
    """What the admin trigger did for a node; an empty list means nothing stale was found."""

    node_id: str
    proposals: list[StaleFilesProposed]


class StaleFileResult(BaseModel):
    """What happened to one approved file."""

    old_target: str
    path: str
    result: str


class StaleFilesRemovalResponse(BaseModel):
    """The report of an approved removal."""

    node_id: str
    approval_id: str
    removed: int
    results: list[StaleFileResult]
