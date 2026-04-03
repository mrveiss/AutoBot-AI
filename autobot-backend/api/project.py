# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

import logging
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from project_state_manager import get_project_state_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PhaseStatusItem(BaseModel):
    name: str
    completion: float
    is_active: bool
    is_completed: bool
    capabilities: int
    implemented_capabilities: int


class ProjectStatusResponse(BaseModel):
    current_phase: str
    total_phases: int
    completed_phases: int
    active_phases: int
    overall_completion: float
    next_suggested_phase: Optional[str]
    phases: Dict[str, PhaseStatusItem]


class ProjectReportResponse(BaseModel):
    status: str
    overall_completion: float
    current_phase: str
    total_phases: int
    completed_phases: int
    generated_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=ProjectStatusResponse)
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
            generated_at=datetime.utcnow().isoformat() + "Z",
        )
    except Exception as exc:
        logger.error("Error generating project report: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate project report")
