# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response models for the recorded post-sync runs (#17455).

Pydantic only, no ORM import: `conftest.py` loads this file by path (the way it
loads `gpu_schemas`), because FastAPI validates `response_model` against a real
type at decoration time and a stub would not be one.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict


class PostSyncActionRunResponse(BaseModel):
    """One recorded post-sync action. `success` is None when the action was only issued."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str
    node_id: str
    role_name: str
    category: str
    label: str
    command: str | None = None
    units: str | None = None
    started_at: datetime
    finished_at: datetime
    exit_code: int | None = None
    success: bool | None = None
    output_tail: str = ""
    error: str | None = None


class PostSyncRunResponse(BaseModel):
    """Every recorded action of one run, in execution order."""

    run_id: str
    actions: List[PostSyncActionRunResponse]


class NodeRoleSyncResult(BaseModel):
    """File-sync outcome for one role on the node."""

    role_name: str
    success: bool
    message: str


class NodePostSyncResponse(BaseModel):
    """Result of syncing every ACTIVE role on a node as one ordered plan."""

    success: bool
    message: str
    node_id: str
    commit: str | None = None
    run_id: str
    aborted: bool = False
    skipped: List[str] = []
    roles: List[NodeRoleSyncResult] = []
    actions: List[PostSyncActionRunResponse] = []
