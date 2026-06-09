# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Project API endpoints

Provides the /api/project/* endpoints consumed by PhaseProgressionIndicator
and related frontend components.

Issue #3331: These endpoints were missing, causing 404 errors in the UI.
The existing api/project_state.py router used an internal prefix of /project
combined with a registration prefix of /project-state, yielding incorrect
URLs. This module exposes the correct /api/project/* paths.
"""

from typing import Dict

from fastapi import APIRouter, HTTPException

from api.schemas_system import (
    PhaseStatusItem,
    ProjectReportResponse,
    ProjectStatusResponse,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from project_state_manager import get_project_state_manager

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=ProjectStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_project_status",
    error_code_prefix="PROJECT",
)
async def get_project_status(detailed: bool = False) -> ProjectStatusResponse:
    """Return current project development phase status.

    Args:
        detailed: When True, bypass cache and run full validation checks.
    """
    try:
        manager = get_project_state_manager()
        raw = manager.get_project_status(use_cache=not detailed)

        phases: Dict[str, PhaseStatusItem] = {}
        for phase_id, phase_data in raw.get("phases", {}).items():
            phases[phase_id] = PhaseStatusItem(**phase_data)

        next_phase = raw.get("next_suggested_phase")
        return ProjectStatusResponse(
            current_phase=raw.get("current_phase", "unknown"),
            total_phases=raw.get("total_phases", 0),
            completed_phases=raw.get("completed_phases", 0),
            active_phases=raw.get("active_phases", 0),
            overall_completion=raw.get("overall_completion", 0.0),
            next_suggested_phase=str(next_phase) if next_phase else None,
            phases=phases,
        )
    except Exception as exc:
        logger.error("Error getting project status: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve project status")


@router.get("/report", response_model=ProjectReportResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_project_report",
    error_code_prefix="PROJECT",
)
async def get_project_report() -> ProjectReportResponse:
    """Return a summary report of project completion and phase state."""
    try:
        manager = get_project_state_manager()
        raw = manager.get_project_status(use_cache=True)

        return ProjectReportResponse(
            status="ok",
            overall_completion=raw.get("overall_completion", 0.0),
            current_phase=raw.get("current_phase", "unknown"),
            total_phases=raw.get("total_phases", 0),
            completed_phases=raw.get("completed_phases", 0),
            generated_at=utc_timestamp(),
        )
    except Exception as exc:
        logger.error("Error generating project report: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate project report")
