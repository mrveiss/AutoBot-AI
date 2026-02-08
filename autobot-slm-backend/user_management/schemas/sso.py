# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSO Schemas

Pydantic models for SSO-related API requests and responses.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SSOProviderCreate(BaseModel):
    """Request model for creating an SSO provider."""

    provider_type: str = Field(..., description="SSO provider type")
    name: str = Field(..., min_length=1, max_length=255, description="Provider name")
    config: dict[str, Any] = Field(..., description="Provider configuration")
    org_id: Optional[uuid.UUID] = Field(
        None, description="Organization ID (null for global)"
    )
    is_active: bool = Field(True, description="Whether provider is active")
    is_social: bool = Field(
        False, description="Whether this is a social login provider"
    )
    allow_user_creation: bool = Field(True, description="Allow JIT user provisioning")
    default_role: str = Field("user", description="Default role for new users")
    group_mapping: dict[str, str] = Field(
        default_factory=dict, description="Group to role mapping"
    )


class SSOProviderUpdate(BaseModel):
    """Request model for updating an SSO provider."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    config: Optional[dict[str, Any]] = None
    org_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None
    is_social: Optional[bool] = None
    allow_user_creation: Optional[bool] = None
    default_role: Optional[str] = None
    group_mapping: Optional[dict[str, str]] = None


class SSOProviderResponse(BaseModel):
    """Response model for an SSO provider (excludes sensitive config)."""

    id: uuid.UUID
    org_id: Optional[uuid.UUID]
    provider_type: str
    name: str
    is_active: bool
    is_social: bool
    allow_user_creation: bool
    default_role: Optional[str]
    group_mapping: dict[str, str]
    last_sync_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SSOProviderListResponse(BaseModel):
    """Response model for paginated SSO provider list."""

    providers: list[SSOProviderResponse]
    total: int


class SSOLoginInitResponse(BaseModel):
    """Response model for initiating SSO login."""

    provider_id: uuid.UUID
    provider_type: str
    provider_name: str
    redirect_url: str
    state: Optional[str] = None


class LDAPLoginRequest(BaseModel):
    """Request model for LDAP login."""

    username: str = Field(..., min_length=1, description="LDAP username")
    password: str = Field(..., min_length=1, description="LDAP password")
    provider_id: uuid.UUID = Field(..., description="LDAP provider ID")


class SSOTestResponse(BaseModel):
    """Response model for SSO provider connection test."""

    success: bool
    message: str
    details: Optional[dict[str, Any]] = None
