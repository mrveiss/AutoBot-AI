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

from typing import List

from fastapi import APIRouter, HTTPException

from api.schemas_system import (
    PhaseEntry,
    PhasesStatusResponse,
    ValidationRunResponse,
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


@router.get("/status", response_model=PhasesStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_phases_status",
    error_code_prefix="PHASES",
)
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
            timestamp=utc_timestamp(),
        )
    except Exception as exc:
        logger.error("Error getting phases status: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to retrieve phases status")


@router.post("/validation/run", response_model=ValidationRunResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_phases_validation",
    error_code_prefix="PHASES",
)
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
            timestamp=utc_timestamp(),
        )
    except Exception as exc:
        logger.error("Error queuing phase validation: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to queue phase validation")
