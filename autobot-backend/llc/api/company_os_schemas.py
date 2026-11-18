# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request/response models for the Company OS model API (#18390)."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from llc.models.company_os_enums import WorkflowKind
from llc.services.company_os.graph_types import GraphSpec


class ProcessCreate(BaseModel):
    process_key: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    owner_role_id: uuid.UUID
    description: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list, max_length=100)


class ProcessUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    owner_role_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    required_skills: Optional[List[str]] = Field(None, max_length=100)


class ProcessResponse(BaseModel):
    process_key: str
    name: str
    description: Optional[str]
    owner_role_id: uuid.UUID
    required_skills: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyWorkflowCreate(BaseModel):
    workflow_id: str = Field(..., min_length=1, max_length=255)
    kind: WorkflowKind = WorkflowKind.WORKFLOW
    name: Optional[str] = Field(None, max_length=255)
    owner_role_id: Optional[uuid.UUID] = None
    trigger_type: Optional[str] = Field(None, max_length=32)
    trigger_config: Dict[str, Any] = Field(default_factory=dict)


class CompanyWorkflowUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    owner_role_id: Optional[uuid.UUID] = None
    trigger_type: Optional[str] = Field(None, max_length=32)
    trigger_config: Optional[Dict[str, Any]] = None


class CompanyWorkflowResponse(BaseModel):
    workflow_id: str
    kind: str
    name: Optional[str]
    status: str
    owner_role_id: Optional[uuid.UUID]
    trigger_type: Optional[str]
    trigger_config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GraphValidation(BaseModel):
    errors: List[str]
    warnings: List[str]


class GraphResponse(BaseModel):
    graph: GraphSpec
    validation: GraphValidation


class RoleSkillGrant(BaseModel):
    """Exactly one of the two fields."""

    skill_name: Optional[str] = Field(None, min_length=1, max_length=255)
    meta_skill_id: Optional[str] = Field(None, min_length=1, max_length=255)


class GrantResponse(BaseModel):
    id: uuid.UUID
    skill_name: Optional[str]
    meta_skill_id: Optional[str]


class SkillSourceResponse(BaseModel):
    kind: str
    meta_skill_id: Optional[str] = None
    meta_skill_name: Optional[str] = None
    via: List[str] = Field(default_factory=list)


class HeldSkillResponse(BaseModel):
    skill: str
    sources: List[SkillSourceResponse]


class RoleSkillsResponse(BaseModel):
    role_id: uuid.UUID
    skills: List[HeldSkillResponse]
    grants: List[GrantResponse]
