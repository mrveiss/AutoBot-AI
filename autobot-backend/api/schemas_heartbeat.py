# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request and response models for the heartbeat config and agent-control routes (GH#6476, MVA-1411)."""

from typing import Any, Dict

from pydantic import BaseModel, Field


class HeartbeatConfigRequest(BaseModel):
    """Request body to configure heartbeat for an agent."""

    heartbeat_enabled: bool = False
    heartbeat_interval_seconds: int = Field(default=300, ge=10)
    max_run_duration_seconds: int = Field(default=600, ge=10)


class HeartbeatConfigResponse(BaseModel):
    """Response for agent heartbeat config / runtime state (GH#6476)."""

    agent_id: str
    heartbeat_enabled: bool
    status: str
    paused_reason: str | None = None
    paused_at: str | None = None
    paused_by: str | None = None
    paused_by_name: str | None = Field(
        default=None, description="Display name of the user in paused_by; null for system actors or unknown users."
    )
    error_detail: str | None = None
    error_at: str | None = None
    error_code: str | None = None
    heartbeat_interval_seconds: int
    max_run_duration_seconds: int
    current_task_id: str | None
    last_heartbeat_at: str | None
    session_params: Dict[str, Any] | None
    extra: Dict[str, Any] | None
    created_at: str | None
    updated_at: str | None


class AgentPauseRequest(BaseModel):
    """Request body for POST /heartbeat/{agent_id}/pause (GH#6476)."""

    reason: str | None = None
    paused_by: str | None = Field(default=None, description="Ignored; the actor is the verified caller.")


class AgentResumeRequest(BaseModel):
    """Request body for POST /heartbeat/{agent_id}/resume (GH#6476)."""


class AgentTerminateRequest(BaseModel):
    """Request body for POST /heartbeat/{agent_id}/terminate (GH#6476)."""

    reason: str | None = None


class AgentErrorRequest(BaseModel):
    """Request body for POST /heartbeat/{agent_id}/error (MVA-1411)."""

    error_detail: str | None = None
    error_code: str | None = None


class AgentRecoverRequest(BaseModel):
    """Request body for POST /heartbeat/{agent_id}/recover (MVA-1411)."""
