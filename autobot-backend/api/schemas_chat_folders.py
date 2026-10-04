# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat folder payload models (GH#8987), split out of ``schemas_chat.py`` (#16502).

Moved rather than copied: ``schemas_chat.py`` sat exactly at its 732-line
ceiling, and a ceiling is lowered to fit a change, never raised. These five
models are the most cohesive group in that file -- they serve
``api/chat_folders.py`` alone and nothing else imports them -- so moving them
costs one import line at the single call site.

Not re-exported from ``schemas_chat``. A re-export would leave two names for
one object, which is harmless for a class and fatal for anything a test
patches, and it would keep the lines it was the point of removing.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class FolderCreate(BaseModel):
    """Request body for POST /chat/folders."""

    name: str = Field(..., min_length=1, max_length=100, description="Folder display name")
    parent_id: str | None = Field(None, description="Parent folder ID for nesting (max 3 levels)")


class FolderUpdate(BaseModel):
    """Request body for PUT /chat/folders/{folder_id}."""

    name: str | None = Field(None, min_length=1, max_length=100, description="New folder name")
    parent_id: str | None = Field(None, description="New parent folder ID (None = root)")
    pinned: bool | None = Field(None, description="Pin folder to top of list")
    archived: bool | None = Field(None, description="Archive folder (hidden from main list, still searchable)")


class FolderData(BaseModel):
    """Single folder object returned by the API."""

    id: str
    name: str
    parent_id: str | None = None
    owner: str
    pinned: bool = False
    archived: bool = False
    created_at: str
    session_ids: List[str] = Field(default_factory=list)
    session_count: int = 0


class FolderListData(BaseModel):
    """data payload for GET /chat/folders."""

    folders: List[FolderData]
    count: int


class SessionFolderAssign(BaseModel):
    """Request body for PUT /chat/sessions/{session_id}/folder."""

    folder_id: str | None = Field(None, description="Folder ID to assign; None removes from folder")
