# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MFA Schemas

Pydantic schemas for Multi-Factor Authentication endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MFASetupResponse(BaseModel):
    """Response for MFA setup."""

    secret: str
    otpauth_uri: str
    backup_codes: List[str]


class MFAVerifyRequest(BaseModel):
    """Request to verify MFA code."""

    code: str = Field(..., min_length=6, max_length=8)


class MFADisableRequest(BaseModel):
    """Request to disable MFA (requires password)."""

    password: str


class MFAStatusResponse(BaseModel):
    """MFA status for a user."""

    enabled: bool
    method: str = "totp"
    backup_codes_remaining: int = 0
    last_verified_at: Optional[datetime] = None


class BackupCodesResponse(BaseModel):
    """Response containing backup codes."""

    backup_codes: List[str]
