# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Phases API endpoints

Provides the /api/phases/* endpoints consumed by PhaseProgressionIndicator
and related frontend components.

Issue #3331: The existing api/phase_management.py depended on
scripts.phase_validation_system which does not exist, causing an ImportError
at startup and returning 404 for all /api/phases/* paths. This module
provides the required endpoints backed by the project_state_manager which
is already in use throughout the backend.
"""

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from project_state_manager import get_project_state_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PhaseEntry(BaseModel):
    id: str
    name: str
    completion: float
    is_active: bool
    is_completed: bool


class PhasesStatusResponse(BaseModel):
    status: str
    service: str
    phases: List[PhaseEntry]
    timestamp: str


class ValidationRunResponse(BaseModel):
    status: str
    message: str
    timestamp: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=PhasesStatusResponse)
async def get_phases_status() -> PhasesStatusResponse:
    """Return phase completion status for all development phases."""
    try:
        manager = get_project_state_manager()
        raw = manager.get_project_status(use_cache=True)

        phases: List[PhaseEntry] = []
        for phase_id, phase_data in raw.get("phases", {}).items():
            phases.append(
                PhaseEntry(
                    id=phase_id,
                    name=phase_data.get("name", phase_id),
                    completion=phase_data.get("completion", 0.0),
                    is_active=phase_data.get("is_active", False),
                    is_completed=phase_data.get("is_completed", False),
                )
            )

        return PhasesStatusResponse(
            status="ok",
            service="phase_management",
            phases=phases,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )
    except Exception as exc:
        logger.error("Error getting phases status: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve phases status")


@router.post("/validation/run", response_model=ValidationRunResponse)
async def run_phases_validation() -> ValidationRunResponse:
    """Queue a phase validation run.

    Triggers a full project phase validation pass via the project state
    manager and returns immediately with an acknowledgement.
    """
    try:
        manager = get_project_state_manager()
        manager.validate_all_phases()
        return ValidationRunResponse(
            status="ok",
            message="Validation queued",
            timestamp=datetime.utcnow().isoformat() + "Z",
        )
    except Exception as exc:
        logger.error("Error queuing phase validation: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to queue phase validation")
