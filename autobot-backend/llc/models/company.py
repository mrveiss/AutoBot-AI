# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC Company Pydantic schemas (GH#8211).

These schemas expose the Organization model via the LLC API.  The underlying
storage is the ``organizations`` table; the LLC layer adds company-lifecycle
semantics on top (sub-company hierarchy, budget, issue prefix, status).
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from llc.models.enums import LLCCompanyStatus


class CompanyBase(BaseModel):
    """Shared fields for company create/update/read."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    issue_prefix: Optional[str] = Field(
        None,
        min_length=1,
        max_length=10,
        pattern=r"^[A-Z0-9]+$",
        description="Uppercase alphanumeric prefix for issue identifiers (e.g. MVA)",
    )
    budget_monthly_cents: int = Field(0, ge=0)
    brand_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    require_approval_for_hires: bool = False
    parent_org_id: Optional[uuid.UUID] = None

    model_config = {"from_attributes": True}


class CompanyCreate(CompanyBase):
    """Request body for POST /companies."""

    llc_status: LLCCompanyStatus = LLCCompanyStatus.ONBOARDING

    @field_validator("issue_prefix")
    @classmethod
    def issue_prefix_uppercase(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return v.upper()
        return v


class CompanyUpdate(BaseModel):
    """Request body for PATCH /companies/{id}.  All fields optional.

    ``llc_status`` is intentionally excluded — use the dedicated
    ``suspend()`` / ``archive()`` service methods so transition guards and
    audit trail are always applied.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    issue_prefix: Optional[str] = Field(None, min_length=1, max_length=10, pattern=r"^[A-Z0-9]+$")
    budget_monthly_cents: Optional[int] = Field(None, ge=0)
    brand_color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    require_approval_for_hires: Optional[bool] = None
    pause_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class CompanyRead(CompanyBase):
    """Response schema for a single company."""

    id: uuid.UUID
    llc_status: LLCCompanyStatus
    issue_counter: int
    spent_monthly_cents: int
    pause_reason: Optional[str] = None
    paused_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyTreeNode(BaseModel):
    """Recursive node for GET /companies/{id}/tree."""

    id: uuid.UUID
    name: str
    slug: str
    llc_status: LLCCompanyStatus
    children: List["CompanyTreeNode"] = []

    model_config = {"from_attributes": True}


CompanyTreeNode.model_rebuild()


class CompanyAncestor(BaseModel):
    """Single entry in the ancestry chain for GET /companies/{id}/ancestry."""

    id: uuid.UUID
    name: str
    slug: str
    llc_status: LLCCompanyStatus

    model_config = {"from_attributes": True}


__all__ = [
    "CompanyBase",
    "CompanyCreate",
    "CompanyUpdate",
    "CompanyRead",
    "CompanyTreeNode",
    "CompanyAncestor",
]
