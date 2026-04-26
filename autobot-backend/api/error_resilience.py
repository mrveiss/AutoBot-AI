# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Error Resilience API Endpoints

Issue #4342: Expose error health status, circuit breaker status, error budgets.
Allows monitoring of system resilience and graceful degradation state.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from services.resilience.circuit_breaker_manager import (
    get_circuit_breaker_manager,
)
from services.resilience.error_budget import get_error_budget_tracker
from services.resilience.fallback_manager import get_fallback_manager
from api.schemas_common import DataResponse
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resilience", tags=["resilience"])


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_resilience_health",
    error_code_prefix="ERROR_RESILIENCE",
)
@router.get("/health", response_model=None)
async def get_resilience_health() -> Dict[str, Any]:
    """
    Get overall system resilience health.

    Returns:
        Dictionary with circuit breaker status, error budgets, fallback chains
    """
    try:
        cb_manager = get_circuit_breaker_manager()
        budget_tracker = get_error_budget_tracker()
        fallback_manager = get_fallback_manager()

        return {
            "status": "operational",
            "circuit_breakers": cb_manager.get_status(),
            "error_budgets": budget_tracker.get_status(),
            "fallback_chains": fallback_manager.get_status(),
        }
    except Exception as e:
        logger.error("Error fetching resilience health: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Failed to get resilience health")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_circuit_breaker_status",
    error_code_prefix="ERROR_RESILIENCE",
)
@router.get("/circuit-breakers", response_model=None)
async def get_circuit_breaker_status() -> Dict[str, Any]:
    """
    Get status of all circuit breakers.

    Returns:
        Dictionary with circuit breaker states and statistics
    """
    try:
        manager = get_circuit_breaker_manager()
        return manager.get_status()
    except Exception as e:
        logger.error("Error fetching circuit breaker status: %s", type(e).__name__)
        raise HTTPException(
            status_code=500, detail="Failed to get circuit breaker status"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_error_budget_status",
    error_code_prefix="ERROR_RESILIENCE",
)
@router.get("/error-budgets", response_model=None)
async def get_error_budget_status() -> Dict[str, Any]:
    """
    Get status of all error budgets.

    Returns:
        Dictionary with error budget states and success rates
    """
    try:
        tracker = get_error_budget_tracker()
        return tracker.get_status()
    except Exception as e:
        logger.error("Error fetching error budget status: %s", type(e).__name__)
        raise HTTPException(
            status_code=500, detail="Failed to get error budget status"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_circuit_breaker",
    error_code_prefix="ERROR_RESILIENCE",
)
@router.post("/circuit-breakers/{service_name}/reset", response_model=None)
async def reset_circuit_breaker(service_name: str) -> Dict[str, str]:
    """
    Manually reset circuit breaker for service.

    Args:
        service_name: Name of service to reset

    Returns:
        Confirmation message
    """
    try:
        manager = get_circuit_breaker_manager()
        manager.reset_breaker(service_name)
        return {"message": f"Circuit breaker for {service_name} reset"}
    except Exception as e:
        logger.error("Error resetting circuit breaker: %s", type(e).__name__)
        raise HTTPException(
            status_code=500, detail="Failed to reset circuit breaker"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_error_budget",
    error_code_prefix="ERROR_RESILIENCE",
)
@router.post("/error-budgets/{component}/reset", response_model=None)
async def reset_error_budget(component: str) -> Dict[str, str]:
    """
    Manually reset error budget for component.

    Args:
        component: Component name to reset

    Returns:
        Confirmation message
    """
    try:
        tracker = get_error_budget_tracker()
        tracker.reset_budget(component)
        return {"message": f"Error budget for {component} reset"}
    except Exception as e:
        logger.error("Error resetting error budget: %s", type(e).__name__)
        raise HTTPException(
            status_code=500, detail="Failed to reset error budget"
        )
