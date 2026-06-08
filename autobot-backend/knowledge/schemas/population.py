# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for knowledge population endpoints (Issue #5317 batch 3b)."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class PopulateSystemCommandsResponse(BaseModel):
    """Response for POST /populate_system_commands."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    items_added: int = 0
    total_commands: int | None = None


class PopulateManPagesResponse(BaseModel):
    """Response for POST /populate_man_pages."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    items_added: int = 0
    background: bool | None = None


class RefreshSystemKnowledgeResponse(BaseModel):
    """Response for POST /refresh_system_knowledge."""

    model_config = ConfigDict(extra="allow")

    task_id: str
    status: str
    message: str
    poll_url: str


class JobStatusResponse(BaseModel):
    """Response for GET /job_status/{task_id}."""

    model_config = ConfigDict(extra="allow")

    task_id: str
    status: str
    message: str | None = None
    result: Any | None = None
    error: str | None = None
    meta: Dict[str, Any] | None = None


class TaskQueuedResponse(BaseModel):
    """Response for endpoints that queue a background task and return immediately.

    Used by POST /populate_autobot_docs and POST /index/code.
    """

    model_config = ConfigDict(extra="allow")

    status: str
    task_id: str
    message: str
    status_url: str


class TaskStatusResponse(BaseModel):
    """Response for task status poll endpoints.

    Used by GET /populate_autobot_docs/status/{task_id} and
    GET /index/code/status/{task_id}.
    """

    model_config = ConfigDict(extra="allow")

    task_id: str
    status: str
    message: str | None = None
    progress_percent: float | None = None
    items_processed: int | None = None
    items_total: int | None = None
    error: str | None = None
    elapsed_seconds: float | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ScanManPagesResponse(BaseModel):
    """Response for POST /scan_man_pages.

    When run_background=True the body is a lightweight acknowledgement;
    when run synchronously it carries full counts.
    """

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    background: bool | None = None
    machine_id: str | None = None
    limit: int | None = None
    sections: Any | None = None
    items_added: int | None = None
    items_failed: int | None = None
    total_scanned: int | None = None


class ScanManPagesChangesResponse(BaseModel):
    """Response for POST /scan_man_pages_changes."""

    model_config = ConfigDict(extra="allow")

    status: str
    machine_id: str
    scan_duration_seconds: float = 0.0
    summary: Dict[str, Any] | None = None
    items_stored: int = 0
    parsed_count: int = 0
