# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request schemas for the Microsoft 365 integration router (Issue #13710)."""

from typing import List

from pydantic import BaseModel, Field


class SendEmailRequest(BaseModel):
    """Request model for sending an Outlook message."""

    to: List[str] = Field(..., min_length=1, description="Recipient addresses")
    subject: str = Field(..., min_length=1, description="Message subject")
    body: str = Field(..., description="Message body")
    cc: List[str] | None = Field(None, description="Carbon-copy addresses")
    body_type: str = Field("HTML", pattern="^(HTML|Text)$", description="Body content type")
