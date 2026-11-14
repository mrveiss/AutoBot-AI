# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request/response schemas for the task-workspace REST and WebSocket endpoints.

Moved out of ``api/task_workspace_ws.py`` (#6056 keeps request models in
``schemas_*.py``). ``CheckpointRestoreRequest`` was ``RestoreRequest`` there; it is
renamed so it no longer shares a name with the knowledge-base ``RestoreRequest`` (#17312).
"""

from pydantic import BaseModel


class ExecRequest(BaseModel):
    command: list[str] | str


class SnapshotRequest(BaseModel):
    checkpoint_name: str


class CheckpointRestoreRequest(BaseModel):
    checkpoint_name: str


class WorkspaceInfoResponse(BaseModel):
    task_id: str
    container_id: str
    volume_name: str
    image: str
    created_at: float
    last_active: float
    checkpoint_tags: list[str]


class ExecResponse(BaseModel):
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    task_id: str
    security_blocked: bool


class SnapshotResponse(BaseModel):
    task_id: str
    checkpoint_name: str
    image_tag: str
    created_at: float
