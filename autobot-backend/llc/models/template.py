# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pydantic models for LLC template library (GH#8260).

TemplateCategory enum, request/response models for publish, list,
fetch, import, and search endpoints.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TemplateCategory(str, Enum):
    """Category of an LLC template (GH#8260)."""

    COMPANY = "company"
    PROJECT = "project"
    AGENT_ROLE = "agent_role"
    WORKFLOW = "workflow"


class TemplatePublishRequest(BaseModel):
    """Request body for POST /llc/templates/ (GH#8260)."""

    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    category: TemplateCategory
    template_json: Dict[str, Any] = Field(..., description="Scrubbed company export JSON")
    tags: List[str] = Field(default_factory=list, max_length=20)
    is_public: bool = False


class TemplateRead(BaseModel):
    """Response model for a single template (GH#8260)."""

    id: uuid.UUID
    name: str
    description: Optional[str]
    category: TemplateCategory
    created_by_company_id: Optional[uuid.UUID]
    is_public: bool
    usage_count: int
    tags: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TemplateDetail(TemplateRead):
    """Full template response including template_json (GH#8260)."""

    template_json: Dict[str, Any]


class TemplateListParams(BaseModel):
    """Query parameters for GET /llc/templates/ (GH#8260)."""

    category: Optional[TemplateCategory] = None
    tag: Optional[str] = None
    q: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class TemplateImportRequest(BaseModel):
    """Request body for POST /llc/templates/{id}/import (GH#8260).

    ``secrets`` resolves ``{{SECRET_NAME}}`` placeholders in template_json.
    A 422 is returned if any placeholder remains unresolved.
    """

    target_company_id: uuid.UUID
    secrets: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of SECRET_NAME -> resolved value",
    )


class TemplateImportResult(BaseModel):
    """Result of a template import operation (GH#8260)."""

    template_id: uuid.UUID
    target_company_id: uuid.UUID
    activity_log_id: uuid.UUID
    entities_created: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts of each entity type created",
    )


class TemplateSearchResult(BaseModel):
    """Single result from semantic template search (GH#8260)."""

    template_id: str
    name: str
    description: Optional[str]
    category: str
    score: float


class TemplateSearchResponse(BaseModel):
    """Response for GET /llc/templates/search (GH#8260)."""

    query: str
    results: List[TemplateSearchResult]
    total: int
