# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response models for the workflow-automation routes (#12363).

Each model describes what the handler returns today, field for field, so the generated
OpenAPI contract (and the frontend types derived from it) carry the real shape instead of
``unknown``. ``WorkflowStepStatusPayload`` and ``WorkflowStatusPayload`` mirror
``WorkflowStep.to_status_dict`` and ``ActiveWorkflow.to_status_dict`` in ``models.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel


class WorkflowStepStatusPayload(BaseModel):
    """One step as ``WorkflowStep.to_status_dict`` reports it."""

    step_id: str
    command: str
    description: str
    status: str
    requires_confirmation: bool
    risk_level: str
    risk_tier: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class WorkflowStatusPayload(BaseModel):
    """A workflow as ``ActiveWorkflow.to_status_dict`` reports it."""

    workflow_id: str
    name: str
    description: str
    session_id: str
    current_step: int
    total_steps: int
    is_paused: bool
    is_cancelled: bool
    automation_mode: str
    phase: str | None = None
    active_service: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    steps: List[WorkflowStepStatusPayload]
    user_interventions: List[Dict[str, Any]]
    notification_config: Dict[str, Any] | None = None
    trigger_payload: Dict[str, Any] | None = None


class WorkflowCreatedResponse(BaseModel):
    """``POST /create_workflow``."""

    success: bool
    workflow_id: str
    message: str


class WorkflowActionResponse(BaseModel):
    """``POST /start_workflow/{id}`` and ``POST /control_workflow``."""

    success: bool
    message: str


class AutomationWorkflowStatusResponse(BaseModel):
    """``GET /workflow_status/{id}``."""

    success: bool
    workflow: WorkflowStatusPayload


class AutomationWorkflowListResponse(BaseModel):
    """``GET /active_workflows`` and ``GET /completed_workflows``."""

    success: bool
    workflows: List[WorkflowStatusPayload]
    count: int


class WorkflowErrorResponse(BaseModel):
    """The ``HTTPException`` body the routes raise for 403, 404, 409 and 500."""

    detail: str


def _errors(*codes: int) -> Dict[int | str, Dict[str, Any]]:
    return {code: {"model": WorkflowErrorResponse} for code in codes}


# Per route, what its handler and its auth dependency raise (all bodies are ``{"detail": str}``).
# 401/403: ``get_current_user`` (403 also for a run-scoped token); 403 also from the command-permission
# gate (create) and the owner-or-admin check; 404: workflow not found; 409: ``StepNotAwaitingApproval``.
CREATE_ERRORS = _errors(401, 403, 500)
START_ERRORS = _errors(401, 403, 404, 500)
CONTROL_ERRORS = _errors(401, 403, 404, 409, 500)
STATUS_ERRORS = _errors(401, 403, 404, 500)
LIST_ERRORS = _errors(401, 403, 500)
