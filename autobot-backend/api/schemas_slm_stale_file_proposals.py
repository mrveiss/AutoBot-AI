# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the stale code-sync file routes: propose and claim (#22033)."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from api.schemas_slm_credential_proposals import NODE_ID_PATTERN
from autobot_shared.slm_stale_file_actions import MAX_FILES_PER_PROPOSAL

_NODE_ID = Field(min_length=1, max_length=64, pattern=NODE_ID_PATTERN)
_BLOB = Field(pattern=r"^[0-9a-f]{40}$")
#: A path is one line of text in the approval and in the removal script: no control characters.
_MAX_PATH = 1024


def _is_clean_relative(path: str) -> bool:
    """False for an absolute path, a ``..`` segment, or any control character (newline, tab, NUL)."""
    if not path or len(path) > _MAX_PATH or path.startswith("/") or not path.isprintable():
        return False
    return ".." not in PurePosixPath(path).parts


class StaleFileEntry(BaseModel):
    """One file offered for removal: where, how big, how old, and the git blob it is byte-identical to."""

    path: str
    size_bytes: int = Field(ge=0)
    modified_at: datetime
    blob: str = _BLOB

    @field_validator("path")
    @classmethod
    def _path_is_contained(cls, value: str) -> str:
        if not _is_clean_relative(value):
            raise ValueError("path must be relative, without '..' or control characters")
        return value


class StaleFileProposal(BaseModel):
    """What the SLM proposes: the files of ONE old sync location on ONE node, never file contents."""

    node_id: str = _NODE_ID
    old_target: str = Field(min_length=1, max_length=512, pattern=r"^/[^\x00-\x1f]*$")
    commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    files: list[StaleFileEntry] = Field(min_length=1, max_length=MAX_FILES_PER_PROPOSAL)
    total_found: int = Field(ge=1)

    @field_validator("old_target")
    @classmethod
    def _target_has_no_dot_segments(cls, value: str) -> str:
        if any(part in ("..", ".") for part in value.split("/")):
            raise ValueError("old_target must not contain '.' or '..' segments")
        return value


class StaleFileProposalResponse(BaseModel):
    """The location's open approval, and whether this call created it."""

    approval_id: str
    status: str
    created: bool


class StaleFileClaim(BaseModel):
    """The SLM names the action and the node it is about to clean; the approval must name the same."""

    action: Literal["slm_node_stale_sync_files_cleanup"]
    node_id: str = _NODE_ID


class StaleFileClaimResponse(BaseModel):
    """The approval was a human's and is now spent: what it approved, to be re-checked by the SLM."""

    approval_id: str
    node_id: str
    old_target: str
    files: list[StaleFileEntry]
