# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Error Resilience API Endpoints

Issue #4342: Expose error health status, circuit breaker status, error budgets.
Allows monitoring of system resilience and graceful degradation state.
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from api.schemas_workflows import (
    CircuitBreakerResetResponse,
    CircuitBreakerStatusResponse,
    ErrorBudgetResetResponse,
    ErrorBudgetStatusResponse,
)
from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.resilience.circuit_breaker_manager import (
    get_circuit_breaker_manager,
)
from services.resilience.error_budget import get_error_budget_tracker
from services.resilience.fallback_manager import get_fallback_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/api/resilience", tags=["resilience"])


@register_health_probe(KnownProbes.ERROR_RESILIENCE)
async def probe_error_resilience(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333 / #6907: probe reflects actual breaker + budget state.

    Singleton resolution alone hid the failure mode the file was designed
    to surface (Issue #4342). Reports ``degraded`` when any circuit
    breaker is open or any error budget is exhausted, and passes the
    affected names through ``data`` for diagnostic dashboards.
    """
    try:
        cb_status = get_circuit_breaker_manager().get_status()
        budget_status = get_error_budget_tracker().get_status()
        get_fallback_manager()  # liveness only — no rich state to inspect
        open_breakers = [name for name, cb in cb_status.items() if cb.get("state") == "open"]
        exhausted_budgets = [name for name, budget in budget_status.items() if budget.get("has_budget") is False]
        if open_breakers or exhausted_budgets:
            return ComponentHealth(
                name="error_resilience",
                status="degraded",
                detail=(f"{len(open_breakers)} breaker(s) open, " f"{len(exhausted_budgets)} budget(s) exhausted"),
                data={
                    "open_breakers": open_breakers,
                    "exhausted_budgets": exhausted_budgets,
                    "total_breakers": len(cb_status),
                    "total_budgets": len(budget_status),
                },
            )
        return ComponentHealth(
            name="error_resilience",
            status="ok",
            data={
                "total_breakers": len(cb_status),
                "total_budgets": len(budget_status),
            },
        )
    except Exception as exc:
        return ComponentHealth(
            name="error_resilience",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


@router.get("/circuit-breakers", response_model=CircuitBreakerStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_circuit_breaker_status",
    error_code_prefix="ERROR_RESILIENCE",
)
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
        raise HTTPException(status_code=500, detail="Failed to get circuit breaker status")


@router.get("/error-budgets", response_model=ErrorBudgetStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_error_budget_status",
    error_code_prefix="ERROR_RESILIENCE",
)
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
        raise HTTPException(status_code=500, detail="Failed to get error budget status")


@router.post("/circuit-breakers/{service_name}/reset", response_model=CircuitBreakerResetResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_circuit_breaker",
    error_code_prefix="ERROR_RESILIENCE",
)
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
        raise HTTPException(status_code=500, detail="Failed to reset circuit breaker")


@router.post("/error-budgets/{component}/reset", response_model=ErrorBudgetResetResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_error_budget",
    error_code_prefix="ERROR_RESILIENCE",
)
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
        raise HTTPException(status_code=500, detail="Failed to reset error budget")
