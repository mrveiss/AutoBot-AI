# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pydantic models for the code source registry (#1133).
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Type of code source."""

    GITHUB = "github"
    LOCAL = "local"


class SourceStatus(str, Enum):
    """Sync/ready status of a code source."""

    CONFIGURED = "configured"
    SYNCING = "syncing"
    READY = "ready"
    ERROR = "error"


class SourceAccess(str, Enum):
    """Access control level for a code source."""

    PRIVATE = "private"
    SHARED = "shared"
    PUBLIC = "public"


class CodeSource(BaseModel):
    """A registered code source (GitHub repo or local path)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    source_type: SourceType = SourceType.LOCAL
    repo: Optional[str] = None  # "owner/repo" for GitHub mode
    branch: str = "main"
    credential_id: Optional[str] = None  # References secrets store entry ID
    clone_path: Optional[str] = None  # /opt/autobot/data/code-sources/<id>/
    last_synced: Optional[str] = None
    status: SourceStatus = SourceStatus.CONFIGURED
    error_message: Optional[str] = None
    owner_id: Optional[str] = None
    access: SourceAccess = SourceAccess.PRIVATE
    shared_with: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class CodeSourceCreateRequest(BaseModel):
    """Request to register a new code source."""

    name: str
    source_type: SourceType = SourceType.LOCAL
    repo: Optional[str] = None
    branch: str = "main"
    credential_id: Optional[str] = None
    access: SourceAccess = SourceAccess.PRIVATE


class CodeSourceUpdateRequest(BaseModel):
    """Request to update an existing code source."""

    name: Optional[str] = None
    branch: Optional[str] = None
    credential_id: Optional[str] = None
    access: Optional[SourceAccess] = None


class SourceShareRequest(BaseModel):
    """Request to update sharing settings for a code source."""

    user_ids: List[str]
    access: SourceAccess


class SourceSyncResponse(BaseModel):
    """Response from triggering a source sync."""

    source_id: str
    task_id: str
    status: str
    message: str
