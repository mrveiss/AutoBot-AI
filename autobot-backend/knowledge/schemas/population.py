# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for knowledge population endpoints (Issue #5317 batch 3b)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class PopulateSystemCommandsResponse(BaseModel):
    """Response for POST /populate_system_commands."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    items_added: int = 0
    total_commands: Optional[int] = None


class PopulateManPagesResponse(BaseModel):
    """Response for POST /populate_man_pages."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    items_added: int = 0
    background: Optional[bool] = None


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
    message: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


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
    message: Optional[str] = None
    progress_percent: Optional[float] = None
    items_processed: Optional[int] = None
    items_total: Optional[int] = None
    error: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ScanManPagesResponse(BaseModel):
    """Response for POST /scan_man_pages.

    When run_background=True the body is a lightweight acknowledgement;
    when run synchronously it carries full counts.
    """

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    background: Optional[bool] = None
    machine_id: Optional[str] = None
    limit: Optional[int] = None
    sections: Optional[Any] = None
    items_added: Optional[int] = None
    items_failed: Optional[int] = None
    total_scanned: Optional[int] = None


class ScanManPagesChangesResponse(BaseModel):
    """Response for POST /scan_man_pages_changes."""

    model_config = ConfigDict(extra="allow")

    status: str
    machine_id: str
    scan_duration_seconds: float = 0.0
    summary: Optional[Dict[str, Any]] = None
    items_stored: int = 0
    parsed_count: int = 0
