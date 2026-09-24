# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request/response models for the orphan-storage admin routes (``api/admin_orphan_storage.py``, #17038, #17039).

A companion ``schemas_<domain>_<topic>.py``: the no-local-schemas hook (#6056)
rejects a router that defines its own ``BaseModel``.
"""

from pydantic import BaseModel


class OrphanStorageCandidateResponse(BaseModel):
    """One orphan-storage candidate. ``location`` is logical -- no host path."""

    provider: str
    id: str
    location: str
    size_bytes: int
    modified_at: str
    reason: str
    deletable: bool


class OrphanStorageProviderStatusResponse(BaseModel):
    """Whether one detector's listing actually ran (#17039 review).

    ``available=False`` means this provider's candidates could not be
    determined -- never read the response as "this provider has none".
    """

    provider: str
    available: bool
    error: str | None = None


class OrphanStorageListResponse(BaseModel):
    """Every candidate across every registered detector, plus totals.

    ``provider_statuses`` names every detector that ran and whether it
    could actually check -- an outage shows up here, never as an empty
    ``candidates`` list that reads as "nothing found".
    """

    candidates: list[OrphanStorageCandidateResponse]
    total_count: int
    total_size_bytes: int
    provider_statuses: list[OrphanStorageProviderStatusResponse]


class OrphanStorageDeletionRequest(BaseModel):
    """Propose deleting one candidate. Names the candidate, never a host path."""

    provider: str
    candidate_id: str
    reason: str | None = None


class OrphanStorageDeletionRequestResponse(BaseModel):
    """The PENDING approval a proposal created -- nothing was deleted (#17315).

    ``status`` is the approval's own status, so a caller reading this response
    can never mistake "queued for a human" for "done": the deletion happens
    only if someone approves it, and only then does the registered executor
    run.
    """

    approval_id: str
    status: str
    action: str
    provider: str
    candidate_id: str
