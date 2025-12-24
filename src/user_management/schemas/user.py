# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Schemas

Pydantic models for user-related API requests and responses.
"""

import re
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class RoleResponse(BaseModel):
    """Role information in responses."""

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    is_system: bool = False

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """Request model for creating a user."""

    email: EmailStr = Field(..., description="User email address")
    username: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Username (3-100 characters, alphanumeric and underscores)",
    )
    password: Optional[str] = Field(
        None,
        min_length=8,
        max_length=128,
        description="Password (8-128 characters, optional for SSO users)",
    )
    display_name: Optional[str] = Field(
        None, max_length=255, description="Display name"
    )
    org_id: Optional[uuid.UUID] = Field(
        None, description="Organization ID (uses current context if not provided)"
    )
    role_ids: Optional[List[uuid.UUID]] = Field(
        None, description="List of role IDs to assign"
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(
                "Username must contain only letters, numbers, and underscores"
            )
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password strength."""
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserUpdate(BaseModel):
    """Request model for updating a user."""

    email: Optional[EmailStr] = Field(None, description="New email address")
    username: Optional[str] = Field(
        None, min_length=3, max_length=100, description="New username"
    )
    display_name: Optional[str] = Field(None, max_length=255, description="Display name")
    bio: Optional[str] = Field(None, max_length=500, description="User bio")
    avatar_url: Optional[str] = Field(None, max_length=500, description="Avatar URL")
    preferences: Optional[dict] = Field(None, description="User preferences")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        """Validate username format if provided."""
        if v is None:
            return v
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(
                "Username must contain only letters, numbers, and underscores"
            )
        return v.lower()


class UserResponse(BaseModel):
    """Response model for a single user."""

    id: uuid.UUID
    email: str
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    org_id: Optional[uuid.UUID] = None
    is_active: bool = True
    is_verified: bool = False
    mfa_enabled: bool = False
    is_platform_admin: bool = False
    preferences: dict = Field(default_factory=dict)
    roles: List[RoleResponse] = Field(default_factory=list)
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """Response model for paginated user list."""

    users: List[UserResponse]
    total: int
    limit: int
    offset: int


class UserLogin(BaseModel):
    """Request model for user login."""

    username_or_email: str = Field(
        ..., min_length=3, description="Username or email address"
    )
    password: str = Field(..., min_length=1, description="Password")


class PasswordChange(BaseModel):
    """Request model for changing password."""

    current_password: Optional[str] = Field(
        None, description="Current password (required unless admin reset)"
    )
    new_password: str = Field(
        ..., min_length=8, max_length=128, description="New password"
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v
