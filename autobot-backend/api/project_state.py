#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project State API
Exposes project development phase information and validation status
"""

import logging
from typing import Dict, List, Optional

from backend.utils.advanced_cache_manager import smart_cache
from fastapi import APIRouter, HTTPException
from project_state_manager import DevelopmentPhase, get_project_state_manager
from pydantic import BaseModel

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/project", tags=["project_state"])


# Pydantic models for API responses
class PhaseStatus(BaseModel):
    name: str
    completion: float
    is_active: bool
    is_completed: bool
    capabilities: int
    implemented_capabilities: int


class ProjectStatus(BaseModel):
    current_phase: str
    total_phases: int
    completed_phases: int
    active_phases: int
    overall_completion: float
    next_suggested_phase: Optional[str]
    phases: Dict[str, PhaseStatus]


class ValidationResultModel(BaseModel):
    check_name: str
    status: str
    score: float
    details: str
    timestamp: str


class PhaseValidationModel(BaseModel):
    phase_name: str
    completion_percentage: float
    is_completed: bool
    capabilities: List[str]
    validation_results: List[ValidationResultModel]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_project_status",
    error_code_prefix="PROJECT_STATE",
)
@router.get("/status", response_model=ProjectStatus)
@smart_cache(
    data_type="project_status",
    key_func=lambda detailed=False: f"status:{'detailed' if detailed else 'fast'}",
)
async def get_project_status(detailed: bool = False):
    """Get overall project development status

    Args:
        detailed: If True, performs full validation checks (slower)
                 If False, uses cached data and estimates (default, faster)
    """
    try:
        manager = get_project_state_manager()

        if detailed:
            status = manager.get_project_status(use_cache=False)
        else:
            # Use cached data for fast response
            status = manager.get_project_status(use_cache=True)

        # Convert to Pydantic models
        phases = {}
        for phase_id, phase_data in status["phases"].items():
            phases[phase_id] = PhaseStatus(**phase_data)

        return ProjectStatus(
            current_phase=status["current_phase"],
            total_phases=status["total_phases"],
            completed_phases=status["completed_phases"],
            active_phases=status["active_phases"],
            overall_completion=status["overall_completion"],
            next_suggested_phase=(
                str(status["next_suggested_phase"])
                if status["next_suggested_phase"]
                else None
            ),
            phases=phases,
        )

    except Exception as e:
        logger.error("Error getting project status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_validation",
    error_code_prefix="PROJECT_STATE",
)
@router.post("/validate")
async def run_validation():
    """Run validation on all project phases"""
    try:
        manager = get_project_state_manager()
        validation_results = manager.validate_all_phases()

        # Convert results to API format
        results = {}
        for phase, validations in validation_results.items():
            phase_info = manager.phases[phase]

            results[phase.value] = PhaseValidationModel(
                phase_name=phase_info.name,
                completion_percentage=phase_info.completion_percentage,
                is_completed=phase_info.is_completed,
                capabilities=[cap.name for cap in phase_info.capabilities],
                validation_results=[
                    ValidationResultModel(
                        check_name=result.check_name,
                        status=result.status.value,
                        score=result.score,
                        details=result.details,
                        timestamp=result.timestamp.isoformat(),
                    )
                    for result in validations
                ],
            )

        return {"success": True, "message": "Validation completed", "results": results}

    except Exception as e:
        logger.error("Error running validation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_validation_report",
    error_code_prefix="PROJECT_STATE",
)
@router.get("/report")
async def get_validation_report():
    """Get detailed validation report in markdown format"""
    try:
        manager = get_project_state_manager()
        report = manager.generate_validation_report()

        return {
            "success": True,
            "report": report,
            "generated_at": (
                manager.phases[manager.current_phase].last_validated.isoformat()
                if manager.phases[manager.current_phase].last_validated
                else None
            ),
        }

    except Exception as e:
        logger.error("Error generating validation report: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_phases",
    error_code_prefix="PROJECT_STATE",
)
@router.get("/phases")
async def get_all_phases():
    """Get detailed information about all development phases"""
    try:
        manager = get_project_state_manager()

        phases_data = {}
        for phase, info in manager.phases.items():
            capabilities = []
            for cap in info.capabilities:
                capabilities.append(
                    {
                        "name": cap.name,
                        "description": cap.description,
                        "validation_method": cap.validation_method,
                        "validation_target": cap.validation_target,
                        "required": cap.required,
                        "implemented": cap.implemented,
                        "last_validated": (
                            cap.last_validated.isoformat()
                            if cap.last_validated
                            else None
                        ),
                        "validation_details": cap.validation_details,
                    }
                )

            phases_data[phase.value] = {
                "name": info.name,
                "description": info.description,
                "completion_percentage": info.completion_percentage,
                "is_active": info.is_active,
                "is_completed": info.is_completed,
                "last_validated": (
                    info.last_validated.isoformat() if info.last_validated else None
                ),
                "prerequisites": [p.value for p in info.prerequisites],
                "capabilities": capabilities,
            }

        return {
            "success": True,
            "current_phase": manager.current_phase.value,
            "phases": phases_data,
        }

    except Exception as e:
        logger.error("Error getting phases: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="activate_phase",
    error_code_prefix="PROJECT_STATE",
)
@router.post("/phase/{phase_id}/activate")
async def activate_phase(phase_id: str):
    """Activate a specific development phase"""
    try:
        manager = get_project_state_manager()

        # Validate phase exists
        try:
            phase = DevelopmentPhase(phase_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid phase: {phase_id}")

        if phase not in manager.phases:
            raise HTTPException(status_code=404, detail=f"Phase not found: {phase_id}")

        # Deactivate all other phases
        for p, info in manager.phases.items():
            info.is_active = p == phase

        # Update current phase
        manager.current_phase = phase
        manager.save_state()

        return {
            "success": True,
            "message": f"Phase {phase_id} activated",
            "current_phase": manager.current_phase.value,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error activating phase: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="auto_progress_phases",
    error_code_prefix="PROJECT_STATE",
)
@router.post("/auto-progress")
async def auto_progress_phases():
    """Run automated phase progression logic"""
    try:
        manager = get_project_state_manager()
        result = manager.auto_progress_phases()

        return {
            "success": True,
            "message": "Auto progression completed",
            "progression_result": result,
        }

    except Exception as e:
        logger.error("Error during auto progression: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="health_check",
    error_code_prefix="PROJECT_STATE",
)
@router.get("/health")
async def health_check():
    """Health check for project state API"""
    try:
        manager = get_project_state_manager()
        status = manager.get_project_status()

        return {
            "status": "healthy",
            "current_phase": status["current_phase"],
            "overall_completion": status["overall_completion"],
            "timestamp": (
                manager.phases[manager.current_phase].last_validated.isoformat()
                if manager.phases[manager.current_phase].last_validated
                else None
            ),
        }

    except Exception as e:
        logger.error("Health check failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
