# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Retention Policy Schemas (MVA-3145, GH#8995)

Pydantic models for retention policy API requests and responses.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PolicyType = Literal["chat", "file", "audit", "kb"]


class RetentionPolicyBase(BaseModel):
    """Base schema for retention policy fields."""

    policy_type: PolicyType = Field(
        ...,
        description="Type of data: chat, file, audit, or kb",
    )
    retention_days: int = Field(
        ...,
        gt=0,
        le=3650,  # Max 10 years
        description="Number of days to retain data",
    )
    anonymize_instead_of_delete: bool = Field(
        default=False,
        description="Anonymize data instead of deletion (GDPR compliance)",
    )


class RetentionPolicyCreate(RetentionPolicyBase):
    """Request schema for creating/updating a retention policy."""

    user_id: uuid.UUID | None = Field(
        None,
        description="User ID for user-specific override (NULL = global policy)",
    )


class RetentionPolicyUpdate(BaseModel):
    """Request schema for updating a retention policy."""

    retention_days: int | None = Field(
        None,
        gt=0,
        le=3650,
        description="Number of days to retain data",
    )
    anonymize_instead_of_delete: bool | None = Field(
        None,
        description="Anonymize data instead of deletion",
    )


class RetentionPolicyResponse(RetentionPolicyBase):
    """Response schema for retention policy."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class RetentionPolicyListResponse(BaseModel):
    """Response schema for listing retention policies."""

    count: int
    policies: list[RetentionPolicyResponse]
