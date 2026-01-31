# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Orchestration API Routes

API endpoints for portable AutoBot service orchestration across machines.
Enables starting/stopping/migrating services on any enrolled node.

Related to Issue #728 - Service portability across machines.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from services.auth import get_current_user
from services.database import get_db
from services.service_orchestrator import service_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orchestration", tags=["orchestration"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ServiceActionRequest(BaseModel):
    """Request for a service action."""

    node_id: Optional[str] = Field(
        None,
        description="Target node ID. If not specified, uses default host from SSOT config.",
    )
    force: bool = Field(
        False,
        description="Force the action even if service appears to be in desired state.",
    )


class ServiceMigrateRequest(BaseModel):
    """Request to migrate a service between nodes."""

    source_node_id: str = Field(..., description="Node currently running the service")
    target_node_id: str = Field(..., description="Node to migrate the service to")


class ServiceActionResponse(BaseModel):
    """Response for a service action."""

    service_name: str
    action: str
    success: bool
    message: str
    node_id: Optional[str] = None
    host: Optional[str] = None


class ServiceDefinitionResponse(BaseModel):
    """Service definition response."""

    name: str
    service_type: str
    default_host: str
    default_port: int
    systemd_service: Optional[str]
    description: str
    health_check_type: str


class FleetStatusResponse(BaseModel):
    """Fleet-wide service status response."""

    timestamp: str
    services: dict
    healthy_count: int
    unhealthy_count: int


class BulkActionRequest(BaseModel):
    """Request for bulk service actions."""

    exclude: List[str] = Field(
        default_factory=list,
        description="List of service names to exclude from the action.",
    )


class BulkActionResponse(BaseModel):
    """Response for bulk service actions."""

    action: str
    results: dict
    success_count: int
    failure_count: int


# =============================================================================
# Service Registry Endpoints
# =============================================================================


@router.get("/services", response_model=List[ServiceDefinitionResponse])
async def list_registered_services(
    _: Annotated[dict, Depends(get_current_user)],
) -> List[ServiceDefinitionResponse]:
    """
    List all registered AutoBot services.

    Returns the service registry with default hosts/ports from SSOT configuration.
    """
    services = service_orchestrator.registry.list_services()
    return [
        ServiceDefinitionResponse(
            name=svc.name,
            service_type=svc.service_type.value,
            default_host=service_orchestrator.registry.get_service_host(svc.name),
            default_port=service_orchestrator.registry.get_service_port(svc.name),
            systemd_service=svc.systemd_service,
            description=svc.description,
            health_check_type=svc.health_check_type,
        )
        for svc in services
    ]


@router.get("/services/{service_name}", response_model=ServiceDefinitionResponse)
async def get_service_definition(
    service_name: str,
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceDefinitionResponse:
    """
    Get definition for a specific AutoBot service.
    """
    svc = service_orchestrator.registry.get_service(service_name)
    if not svc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service not found: {service_name}",
        )

    return ServiceDefinitionResponse(
        name=svc.name,
        service_type=svc.service_type.value,
        default_host=service_orchestrator.registry.get_service_host(svc.name),
        default_port=service_orchestrator.registry.get_service_port(svc.name),
        systemd_service=svc.systemd_service,
        description=svc.description,
        health_check_type=svc.health_check_type,
    )


# =============================================================================
# Fleet Status Endpoints
# =============================================================================


@router.get("/status", response_model=FleetStatusResponse)
async def get_fleet_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetStatusResponse:
    """
    Get health status of all AutoBot services across the fleet.

    This checks all registered services and reports their current health.
    """
    status_data = await service_orchestrator.get_fleet_status(db)
    return FleetStatusResponse(**status_data)


# =============================================================================
# Individual Service Control Endpoints
# =============================================================================


@router.post("/services/{service_name}/start", response_model=ServiceActionResponse)
async def start_service(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    request: Optional[ServiceActionRequest] = None,
) -> ServiceActionResponse:
    """
    Start an AutoBot service.

    If node_id is not specified, starts on the default host from SSOT configuration.
    Services can be started on any enrolled node for portability.
    """
    request = request or ServiceActionRequest()

    success, message = await service_orchestrator.start_service(
        db=db,
        service_name=service_name,
        node_id=request.node_id,
        force=request.force,
    )

    return ServiceActionResponse(
        service_name=service_name,
        action="start",
        success=success,
        message=message,
        node_id=request.node_id,
        host=service_orchestrator.registry.get_service_host(service_name),
    )


@router.post("/services/{service_name}/stop", response_model=ServiceActionResponse)
async def stop_service(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    request: Optional[ServiceActionRequest] = None,
) -> ServiceActionResponse:
    """
    Stop an AutoBot service.

    If node_id is not specified, stops on the default host from SSOT configuration.
    """
    request = request or ServiceActionRequest()

    success, message = await service_orchestrator.stop_service(
        db=db,
        service_name=service_name,
        node_id=request.node_id,
    )

    return ServiceActionResponse(
        service_name=service_name,
        action="stop",
        success=success,
        message=message,
        node_id=request.node_id,
        host=service_orchestrator.registry.get_service_host(service_name),
    )


@router.post("/services/{service_name}/restart", response_model=ServiceActionResponse)
async def restart_service(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    request: Optional[ServiceActionRequest] = None,
) -> ServiceActionResponse:
    """
    Restart an AutoBot service.

    If node_id is not specified, restarts on the default host from SSOT configuration.
    """
    request = request or ServiceActionRequest()

    success, message = await service_orchestrator.restart_service(
        db=db,
        service_name=service_name,
        node_id=request.node_id,
    )

    return ServiceActionResponse(
        service_name=service_name,
        action="restart",
        success=success,
        message=message,
        node_id=request.node_id,
        host=service_orchestrator.registry.get_service_host(service_name),
    )


# =============================================================================
# Service Migration Endpoints
# =============================================================================


@router.post("/services/{service_name}/migrate", response_model=ServiceActionResponse)
async def migrate_service(
    service_name: str,
    request: ServiceMigrateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceActionResponse:
    """
    Migrate an AutoBot service from one node to another.

    This stops the service on the source node and starts it on the target node.
    Useful for failover, load balancing, or maintenance scenarios.
    """
    success, message = await service_orchestrator.migrate_service(
        db=db,
        service_name=service_name,
        source_node_id=request.source_node_id,
        target_node_id=request.target_node_id,
    )

    return ServiceActionResponse(
        service_name=service_name,
        action="migrate",
        success=success,
        message=message,
        node_id=request.target_node_id,
    )


# =============================================================================
# Bulk Service Control Endpoints
# =============================================================================


@router.post("/start-all", response_model=BulkActionResponse)
async def start_all_services(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    request: Optional[BulkActionRequest] = None,
) -> BulkActionResponse:
    """
    Start all AutoBot services in dependency order.

    Starts services in the correct order to ensure dependencies are satisfied:
    1. Redis (data layer)
    2. Backend (API server)
    3. Frontend (web UI)
    4. AI Stack (LLM server)
    5. NPU Worker (hardware acceleration)
    6. Browser (automation service)

    Use the 'exclude' parameter to skip specific services.
    """
    request = request or BulkActionRequest()

    results = await service_orchestrator.start_all_services(
        db=db,
        exclude=request.exclude,
    )

    success_count = sum(1 for success, _ in results.values() if success)
    failure_count = len(results) - success_count

    return BulkActionResponse(
        action="start-all",
        results={
            name: {"success": success, "message": msg}
            for name, (success, msg) in results.items()
        },
        success_count=success_count,
        failure_count=failure_count,
    )


@router.post("/stop-all", response_model=BulkActionResponse)
async def stop_all_services(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    request: Optional[BulkActionRequest] = None,
) -> BulkActionResponse:
    """
    Stop all AutoBot services in reverse dependency order.

    Stops services in reverse order to ensure clean shutdown:
    1. Browser (automation service)
    2. NPU Worker (hardware acceleration)
    3. AI Stack (LLM server)
    4. Frontend (web UI)
    5. Backend (API server)
    6. Redis (data layer) - last to preserve data

    Use the 'exclude' parameter to skip specific services.
    """
    request = request or BulkActionRequest()

    results = await service_orchestrator.stop_all_services(
        db=db,
        exclude=request.exclude,
    )

    success_count = sum(1 for success, _ in results.values() if success)
    failure_count = len(results) - success_count

    return BulkActionResponse(
        action="stop-all",
        results={
            name: {"success": success, "message": msg}
            for name, (success, msg) in results.items()
        },
        success_count=success_count,
        failure_count=failure_count,
    )


@router.post("/restart-all", response_model=BulkActionResponse)
async def restart_all_services(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    request: Optional[BulkActionRequest] = None,
) -> BulkActionResponse:
    """
    Restart all AutoBot services.

    Performs a stop-all followed by start-all in the correct dependency order.
    This is equivalent to the smart restart in run_autobot.sh.

    Use the 'exclude' parameter to skip specific services.
    """
    request = request or BulkActionRequest()

    # Stop all first
    stop_results = await service_orchestrator.stop_all_services(
        db=db,
        exclude=request.exclude,
    )

    # Then start all
    start_results = await service_orchestrator.start_all_services(
        db=db,
        exclude=request.exclude,
    )

    # Combine results
    combined_results = {}
    for name in set(stop_results.keys()) | set(start_results.keys()):
        stop_success, stop_msg = stop_results.get(name, (True, "Not stopped"))
        start_success, start_msg = start_results.get(name, (True, "Not started"))

        combined_results[name] = {
            "stop_success": stop_success,
            "stop_message": stop_msg,
            "start_success": start_success,
            "start_message": start_msg,
            "success": start_success,  # Overall success based on final state
        }

    success_count = sum(1 for r in combined_results.values() if r["success"])
    failure_count = len(combined_results) - success_count

    return BulkActionResponse(
        action="restart-all",
        results=combined_results,
        success_count=success_count,
        failure_count=failure_count,
    )
