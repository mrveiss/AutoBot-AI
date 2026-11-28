# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request schemas for the filesystem MCP ``edit_file`` tool (#19463)."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, StrictInt
from typing_extensions import TypedDict


class EditSpec(TypedDict, total=False):
    """One exact find-and-replace; ``oldText``/``newText`` are the MCP-spec spellings."""

    old_text: str
    new_text: str
    oldText: str
    newText: str
    expected_replacements: StrictInt


class EditFileRequest(BaseModel):
    """Request model for editing files."""

    path: str = Field(..., description="Absolute path to file")
    edits: List[EditSpec] = Field(..., description="List of {old_text, new_text, expected_replacements?} edits")
    dry_run: bool | None = Field(False, description="Preview changes without applying")
