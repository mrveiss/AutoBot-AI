# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Phase Management API for AutoBot
Provides endpoints for phase progression, validation, and system state management
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from scripts.phase_validation_system import PhaseValidator
from phase_progression_manager import get_progression_manager
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for allowed configuration keys
_ALLOWED_CONFIG_KEYS = frozenset(
    {
        "auto_progression_enabled",
        "minimum_phase_duration",
        "validation_threshold",
        "rollback_threshold",
        "max_concurrent_phases",
        "progression_cooldown",
    }
)


class PhaseProgressionRequest(BaseModel):
    phase_name: str
    trigger: str = "user_request"
    user_id: str = "system"
    force: bool = False


class ValidationRequest(BaseModel):
    phases: Optional[list] = None
    include_details: bool = True


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_phase_management_status",
    error_code_prefix="PHASE",
)
@router.get("/status")
async def get_phase_management_status():
    """Get overall phase management system status"""
    try:
        progression_manager = get_progression_manager()
        capabilities = progression_manager.get_current_system_capabilities()

        return {
            "status": "healthy",
            "service": "phase_management",
            "timestamp": datetime.now().isoformat(),
            "capabilities": capabilities,
            "auto_progression_enabled": capabilities["auto_progression_enabled"],
            "system_maturity": capabilities["system_maturity"],
        }
    except Exception as e:
        logger.error("Error getting phase management status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_full_phase_validation",
    error_code_prefix="PHASE",
)
@router.get("/validation/full")
async def run_full_phase_validation():
    """Run comprehensive phase validation across all phases"""
    try:
        validator = PhaseValidator()
        validation_results = await validator.validate_all_phases()

        return {
            "status": "success",
            "validation_results": validation_results,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error running phase validation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_custom_phase_validation",
    error_code_prefix="PHASE",
)
@router.post("/validation/run")
async def run_custom_phase_validation(request: ValidationRequest):
    """Run phase validation for specific phases"""
    try:
        validator = PhaseValidator()

        if request.phases:
            # Validate specific phases (would need to implement in PhaseValidator)
            results = {"message": "Custom phase validation not yet implemented"}
        else:
            # Run full validation
            results = await validator.validate_all_phases()

        return {
            "status": "success",
            "validation_results": results,
            "phases_requested": request.phases,
            "include_details": request.include_details,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error running custom validation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_progression_eligibility",
    error_code_prefix="PHASE",
)
@router.get("/progression/eligibility")
async def check_progression_eligibility():
    """Check which phases are eligible for progression"""
    try:
        progression_manager = get_progression_manager()
        eligibility = await progression_manager.check_progression_eligibility()

        return {
            "status": "success",
            "eligibility": eligibility,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error checking progression eligibility: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_automated_progression",
    error_code_prefix="PHASE",
)
@router.post("/progression/auto")
async def execute_automated_progression(background_tasks: BackgroundTasks):
    """Execute automated phase progression"""
    try:
        progression_manager = get_progression_manager()

        # Run progression in background to avoid timeout
        def run_progression():
            """Execute phase progression in a new event loop."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    progression_manager.execute_automated_progression()
                )
            finally:
                loop.close()

        background_tasks.add_task(run_progression)

        return {
            "status": "success",
            "message": "Automated progression started in background",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error executing automated progression: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="trigger_manual_progression",
    error_code_prefix="PHASE",
)
@router.post("/progression/manual")
async def trigger_manual_progression(request: PhaseProgressionRequest):
    """Manually trigger progression to a specific phase"""
    try:
        progression_manager = get_progression_manager()

        result = await progression_manager.trigger_manual_progression(
            phase_name=request.phase_name, user_id=request.user_id
        )

        if result["status"] == "success":
            return {
                "status": "success",
                "message": f"Successfully progressed to {request.phase_name}",
                "progression_result": result,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "failed",
                    "message": result["message"],
                    "phase_name": request.phase_name,
                    "timestamp": datetime.now().isoformat(),
                },
            )
    except Exception as e:
        logger.error("Error triggering manual progression: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_phases",
    error_code_prefix="PHASE",
)
@router.get("/phases/available")
async def get_available_phases():
    """Get list of all available phases and their status"""
    try:
        progression_manager = get_progression_manager()
        validator = PhaseValidator()

        # Get current validation results
        validation_results = await validator.validate_all_phases()

        # Get progression rules
        progression_rules = progression_manager.progression_rules

        phases_info = []
        for phase_name, rules in progression_rules.items():
            phase_data = validation_results["phases"].get(phase_name, {})

            phases_info.append(
                {
                    "name": phase_name,
                    "completion_percentage": phase_data.get("completion_percentage", 0),
                    "status": phase_data.get("status", "unknown"),
                    "prerequisites": rules.get("prerequisites", []),
                    "auto_progression": rules.get("auto_progression", False),
                    "capabilities_unlocked": rules.get("capabilities_unlocked", []),
                    "next_phases": rules.get("next_phases", []),
                }
            )

        return {
            "status": "success",
            "phases": phases_info,
            "total_phases": len(phases_info),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error getting available phases: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_current_capabilities",
    error_code_prefix="PHASE",
)
@router.get("/capabilities/current")
async def get_current_capabilities():
    """Get current system capabilities and progression history"""
    try:
        progression_manager = get_progression_manager()
        capabilities = progression_manager.get_current_system_capabilities()

        return {
            "status": "success",
            "capabilities": capabilities,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error getting capabilities: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_progression_history",
    error_code_prefix="PHASE",
)
@router.get("/history/progressions")
async def get_progression_history(limit: int = Query(10, ge=1, le=100)):
    """Get phase progression history"""
    try:
        progression_manager = get_progression_manager()
        history = (
            progression_manager.progression_history[-limit:]
            if progression_manager.progression_history
            else []
        )

        return {
            "status": "success",
            "history": history,
            "total_progressions": len(progression_manager.progression_history),
            "showing": len(history),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error getting progression history: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="phase_management_health",
    error_code_prefix="PHASE",
)
@router.get("/health")
async def phase_management_health():
    """Health check for phase management system"""
    try:
        progression_manager = get_progression_manager()

        # Quick health checks - validator can be instantiated on demand
        # Full validation is expensive, so just check progression_manager here
        health_status = {
            "progression_manager": "healthy",
            "validator_available": True,
            "auto_progression": progression_manager.config.get(
                "auto_progression_enabled", False
            ),
            "last_check": (
                progression_manager.last_progression_check.isoformat()
                if progression_manager.last_progression_check
                else None
            ),
        }

        return {
            "status": "healthy",
            "service": "phase_management",
            "components": health_status,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Phase management health check failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_progression_config",
    error_code_prefix="PHASE",
)
@router.post("/config/update")
async def update_progression_config(config_update: dict):
    """Update phase progression configuration"""
    try:
        progression_manager = get_progression_manager()

        # Update allowed configuration keys (Issue #380: use module-level constant)
        updated_keys = []
        for key, value in config_update.items():
            if key in _ALLOWED_CONFIG_KEYS:
                progression_manager.config[key] = value
                updated_keys.append(key)

        return {
            "status": "success",
            "message": "Configuration updated successfully",
            "updated_keys": updated_keys,
            "current_config": {k: progression_manager.config[k] for k in updated_keys},
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error updating progression config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_progression_summary_report",
    error_code_prefix="PHASE",
)
@router.get("/reports/summary")
async def get_progression_summary_report():
    """Generate comprehensive phase progression summary report"""
    try:
        progression_manager = get_progression_manager()
        validator = PhaseValidator()

        # Get comprehensive data
        validation_results = await validator.validate_all_phases()
        eligibility = await progression_manager.check_progression_eligibility()
        capabilities = progression_manager.get_current_system_capabilities()

        summary_report = {
            "overall_assessment": validation_results["overall_assessment"],
            "phase_completion": {
                name: data["completion_percentage"]
                for name, data in validation_results["phases"].items()
            },
            "eligible_for_progression": [
                phase["phase"] for phase in eligibility["eligible_phases"]
            ],
            "blocked_phases": [
                phase["phase"] for phase in eligibility["blocked_phases"]
            ],
            "active_capabilities": capabilities["active_capabilities"],
            "recent_progressions": capabilities["progression_history"],
            "system_maturity": capabilities["system_maturity"],
            "recommendations": validation_results.get("recommendations", []),
        }

        return {
            "status": "success",
            "summary_report": summary_report,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("Error generating summary report: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
