# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VM Services API Endpoints

Issue #432: Provides API endpoints for monitoring VM service status,
managing service state, and retrieving infrastructure health information.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional, Any

from backend.services.vm_service_registry import (
    get_vm_service_registry,
    VMServiceType,
)

router = APIRouter(prefix="/api/vm-services", tags=["vm-services"])


class ServiceStatusResponse(BaseModel):
    """Response model for individual service status."""

    name: str
    status: str
    host: str
    port: int
    is_critical: bool
    is_optional: bool
    description: str
    circuit_breaker_state: str
    consecutive_failures: int
    last_check: Optional[str]
    last_success: Optional[str]
    last_error: Optional[str]


class VMServicesStatusResponse(BaseModel):
    """Response model for all VM services status."""

    timestamp: str
    summary: Dict[str, Any]
    services: Dict[str, ServiceStatusResponse]


class MarkOfflineRequest(BaseModel):
    """Request model for marking a service offline."""

    reason: str = "User disabled"


@router.get("/status", response_model=VMServicesStatusResponse)
async def get_vm_services_status():
    """
    Get current status of all VM services.

    Returns comprehensive status information including:
    - Per-service health status
    - Circuit breaker states
    - Last check/success timestamps
    - Summary statistics

    Issue #432: Main endpoint for VM infrastructure monitoring.
    """
    registry = await get_vm_service_registry()
    return registry.get_status_summary()


@router.get("/status/{service_type}")
async def get_service_status(service_type: str):
    """
    Get status of a specific VM service.

    Args:
        service_type: The service type (frontend, npu_worker, redis, ai_stack, browser, ollama)

    Returns:
        Service status details
    """
    # Validate service type
    try:
        VMServiceType(service_type)
    except ValueError:
        valid_types = [t.value for t in VMServiceType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service type. Valid types: {valid_types}",
        )

    registry = await get_vm_service_registry()
    status_summary = registry.get_status_summary()

    if service_type not in status_summary["services"]:
        raise HTTPException(status_code=404, detail="Service not found")

    return {
        "service": service_type,
        **status_summary["services"][service_type],
    }


@router.post("/check/{service_type}")
async def check_service_health(service_type: str):
    """
    Trigger an immediate health check for a specific service.

    Args:
        service_type: The service type to check

    Returns:
        Updated service status after health check
    """
    try:
        svc_type = VMServiceType(service_type)
    except ValueError:
        valid_types = [t.value for t in VMServiceType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service type. Valid types: {valid_types}",
        )

    registry = await get_vm_service_registry()
    status = await registry.check_service_health(svc_type)

    return {
        "service": service_type,
        "status": status.value,
        "message": f"Health check completed for {service_type}",
    }


@router.post("/check-all")
async def check_all_services():
    """
    Trigger immediate health checks for all VM services.

    Returns:
        Status of all services after health checks
    """
    registry = await get_vm_service_registry()
    results = await registry.check_all_services()

    return {
        "message": "Health checks completed for all services",
        "results": {stype.value: status.value for stype, status in results.items()},
    }


@router.post("/mark-offline/{service_type}")
async def mark_service_offline(service_type: str, request: MarkOfflineRequest):
    """
    Mark a service as intentionally offline.

    This prevents error logging for services that are known to be stopped.
    Use this when intentionally shutting down a VM service.

    Args:
        service_type: The service type to mark offline
        request: Request body with reason for marking offline

    Returns:
        Confirmation message
    """
    try:
        svc_type = VMServiceType(service_type)
    except ValueError:
        valid_types = [t.value for t in VMServiceType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid service type. Valid types: {valid_types}",
        )

    registry = await get_vm_service_registry()
    registry.mark_service_intentionally_offline(svc_type, request.reason)

    return {
        "message": f"Service {service_type} marked as intentionally offline",
        "reason": request.reason,
    }


@router.get("/available")
async def get_available_services():
    """
    Get list of available (online) VM services.

    Returns:
        List of service types that are currently online
    """
    registry = await get_vm_service_registry()
    status_summary = registry.get_status_summary()

    available = [
        name
        for name, svc in status_summary["services"].items()
        if svc["status"] == "online"
    ]

    return {
        "available_services": available,
        "count": len(available),
    }


@router.get("/critical")
async def get_critical_services_status():
    """
    Get status of critical VM services only.

    Returns:
        Status of critical services and overall health
    """
    registry = await get_vm_service_registry()
    status_summary = registry.get_status_summary()

    critical = {
        name: svc
        for name, svc in status_summary["services"].items()
        if svc["is_critical"]
    }

    critical_online = sum(1 for s in critical.values() if s["status"] == "online")
    critical_total = len(critical)

    return {
        "critical_services": critical,
        "summary": {
            "total": critical_total,
            "online": critical_online,
            "offline": critical_total - critical_online,
            "all_healthy": critical_online == critical_total,
        },
    }
