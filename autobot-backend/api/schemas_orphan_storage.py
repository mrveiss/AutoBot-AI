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


class OrphanStorageListResponse(BaseModel):
    """Every candidate across every registered detector, plus totals."""

    candidates: list[OrphanStorageCandidateResponse]
    total_count: int
    total_size_bytes: int
