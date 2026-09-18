# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request/response models for the orphan-repair admin routes (``api/admin_orphan_repair.py``, #15779, #16927).

A companion ``schemas_<domain>_<topic>.py``: the no-local-schemas hook (#6056)
rejects a router that defines its own ``BaseModel``, and the domain schemas modules
are frozen at their size ceilings (#16178).
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class OrphanRepairRequest(BaseModel):
    """Make *new_owner_id* the owner of a resource no live principal can reach.

    ``resource_type`` is a plain string, not an enum, on purpose: an unknown type is
    refused by the service **and audited**, where a validation error would leave no trace.
    """

    resource_type: str = Field(..., min_length=1, max_length=32)
    resource_id: str = Field(..., min_length=1, max_length=255)
    new_owner_id: str = Field(..., min_length=1, max_length=255, description="A live user to own the resource")


class OrphanRepairResponse(BaseModel):
    """What was repaired, and the conditions that justified the break-glass. Never secret material."""

    resource_type: str
    resource_id: str
    new_owner_id: str
    conditions: Dict[str, Any]
    before: Dict[str, Any]
    after: Dict[str, Any]


class OrphanListResponse(BaseModel):
    """Orphans of one type, each with the conditions that make it one (#15779 AC4)."""

    resource_type: str
    orphans: List[Dict[str, Any]]
