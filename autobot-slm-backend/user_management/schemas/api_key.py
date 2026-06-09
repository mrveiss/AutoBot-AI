# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
API Key Schemas

Pydantic schemas for API Key management endpoints.
"""

import uuid
from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class APIKeyCreate(BaseModel):
    """Request to create a new API key."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=500)
    scopes: List[str]
    expires_days: int | None = Field(None, ge=1, le=365)


class APIKeyCreateResponse(BaseModel):
    """Response when creating an API key (includes plaintext key)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    key_prefix: str
    name: str
    scopes: List[str]
    expires_at: datetime | None = None
    created_at: datetime


class APIKeyResponse(BaseModel):
    """Response for API key information (no plaintext key)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key_prefix: str
    name: str
    description: str | None = None
    scopes: List[str]
    is_active: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    usage_count: int = 0
    created_at: datetime


class APIKeyListResponse(BaseModel):
    """Response containing list of API keys."""

    keys: List[APIKeyResponse]
    total: int


class APIKeyUpdate(BaseModel):
    """Request to update an API key."""

    name: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=500)


class APIScopesResponse(BaseModel):
    """Response containing available API scopes."""

    scopes: dict
