# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Orchestration API Routes

API endpoints for portable AutoBot service orchestration across machines.
Enables starting/stopping/migrating services on any enrolled node.

Related to Issue #728 - Service portability across machines.
Updated for Issue #850 - Complete orchestration consolidation.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from api.websocket import ws_manager
from fastapi import APIRouter, Depends, HTTPException, status
from models.database import Node, Service, ServiceStatus
from pydantic import BaseModel, Field
from services.auth import get_current_user
from services.database import get_db
from services.service_orchestrator import service_orchestrator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

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


class FleetServiceNodeStatus(BaseModel):
    """Per-node status for a fleet service."""

    node_id: str
    hostname: str
    status: str


class FleetServiceStatus(BaseModel):
    """Aggregated fleet service status."""

    service_name: str
    category: str
    nodes: List[FleetServiceNodeStatus]
    running_count: int
    stopped_count: int
    failed_count: int
    total_nodes: int


class FleetServicesResponse(BaseModel):
    """Response for fleet services listing."""

    services: List[FleetServiceStatus]
    total_services: int


class ServiceCategoryUpdate(BaseModel):
    """Request to update service category."""

    category: str = Field(..., pattern="^(autobot|system)$")


# =============================================================================
# Per-node systemd fallback helper (#1025)
# =============================================================================


async def _per_node_systemd_action(
    db: AsyncSession,
    service_name: str,
    action: str,
    node_id: Optional[str],
) -> ServiceActionResponse:
    """Run a systemctl action on a specific node for a raw systemd service.

    Used when the service name is not in the abstract registry (#1025).
    Requires node_id so we know which host to target.
    """
    if not node_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"node_id required for discovered service: {service_name}",
        )

    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node not found: {node_id}",
        )

    success, message = await _run_ssh_service_action(node, service_name, action)

    # Update DB record if action succeeded
    if success:
        svc_result = await db.execute(
            select(Service).where(
                Service.node_id == node_id,
                Service.service_name == service_name,
            )
        )
        svc = svc_result.scalar_one_or_none()
        if svc:
            new_status = (
                ServiceStatus.STOPPED.value
                if action == "stop"
                else ServiceStatus.RUNNING.value
            )
            svc.status = new_status
            await db.commit()

    return ServiceActionResponse(
        service_name=service_name,
        action=action,
        success=success,
        message=message,
        node_id=node_id,
        host=node.ip_address,
    )


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
    Falls back to direct systemctl for discovered services (#1025).
    """
    request = request or ServiceActionRequest()

    # Fall back to SSH systemctl for raw systemd names not in registry
    if not service_orchestrator.registry.get_service(service_name):
        return await _per_node_systemd_action(
            db, service_name, "start", request.node_id
        )

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
    Falls back to direct systemctl for discovered services (#1025).
    """
    request = request or ServiceActionRequest()

    if not service_orchestrator.registry.get_service(service_name):
        return await _per_node_systemd_action(db, service_name, "stop", request.node_id)

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
    Falls back to direct systemctl for discovered services (#1025).
    """
    request = request or ServiceActionRequest()

    if not service_orchestrator.registry.get_service(service_name):
        return await _per_node_systemd_action(
            db, service_name, "restart", request.node_id
        )

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
    This provides intelligent service orchestration for the distributed fleet.

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


# =============================================================================
# Fleet-wide Service Management Endpoints (Issue #850)
# =============================================================================

# Fleet sub-router for aggregated service operations
fleet_router = APIRouter(prefix="/fleet", tags=["orchestration-fleet"])


async def _run_ssh_service_action(
    node: Node,
    service_name: str,
    action: str,
) -> tuple[bool, str]:
    """
    Control a service via Ansible playbook.

    Helper for fleet operations. Returns (success, message).

    Migrated from SSH to Ansible playbook execution.
    """
    from services.playbook_executor import get_playbook_executor

    # Map action to Ansible service state
    action_to_state = {
        "start": "started",
        "stop": "stopped",
        "restart": "restarted",
        "reload": "reloaded",
    }

    if action not in action_to_state:
        return False, f"Invalid action: {action}"

    try:
        executor = get_playbook_executor()
        result = await executor.execute_playbook(
            playbook_name="manage-service.yml",
            limit=[node.node_id],
            extra_vars={
                "service_name": service_name,
                "service_action": action_to_state[action],
            },
        )

        if result["success"]:
            logger.info(
                "Ansible service action successful: node=%s service=%s action=%s",
                node.node_id,
                service_name,
                action,
            )
            return True, f"{action.capitalize()} successful"
        else:
            logger.warning(
                "Ansible service action failed: node=%s service=%s action=%s output=%s",
                node.node_id,
                service_name,
                action,
                result["output"][:200],
            )
            return False, f"Failed: {result['output'][:200]}"

    except Exception as e:
        logger.error(
            "Ansible service action exception: node=%s service=%s action=%s error=%s",
            node.node_id,
            service_name,
            action,
            str(e),
        )
        return False, f"Error: {str(e)[:200]}"


@fleet_router.get("/services", response_model=FleetServicesResponse)
async def get_fleet_services(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetServicesResponse:
    """
    Get aggregated service status across all nodes.

    Issue #850: Moved from /fleet/services to /orchestration/fleet/services.
    """
    # Get all services grouped by name
    query = select(Service).order_by(Service.service_name)
    result = await db.execute(query)
    all_services = result.scalars().all()

    # Get node info for hostname lookup
    nodes_result = await db.execute(select(Node))
    nodes = {n.node_id: n for n in nodes_result.scalars().all()}

    # Aggregate by service name
    service_map: Dict[str, dict] = {}
    for svc in all_services:
        if svc.service_name not in service_map:
            service_map[svc.service_name] = {
                "nodes": [],
                "category": getattr(svc, "category", "system") or "system",
            }
        node = nodes.get(svc.node_id)
        service_map[svc.service_name]["nodes"].append(
            FleetServiceNodeStatus(
                node_id=svc.node_id,
                hostname=node.hostname if node else "unknown",
                status=svc.status,
            )
        )

    # Build response
    fleet_services = []
    for service_name, data in service_map.items():
        node_statuses = data["nodes"]
        running = sum(1 for n in node_statuses if n.status == "running")
        stopped = sum(1 for n in node_statuses if n.status == "stopped")
        failed = sum(1 for n in node_statuses if n.status == "failed")

        fleet_services.append(
            FleetServiceStatus(
                service_name=service_name,
                category=data["category"],
                nodes=node_statuses,
                running_count=running,
                stopped_count=stopped,
                failed_count=failed,
                total_nodes=len(node_statuses),
            )
        )

    return FleetServicesResponse(
        services=fleet_services,
        total_services=len(fleet_services),
    )


@fleet_router.patch("/services/{service_name}/category")
async def update_fleet_service_category(
    service_name: str,
    update: ServiceCategoryUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Update the category for a service across all nodes.

    This is an admin override - manually categorize a service as
    'autobot' or 'system' across all nodes that have it.

    Issue #850: Moved from /fleet/services/{name}/category to /orchestration/fleet/services/{name}/category.
    """
    # Find all service records with this name
    query = select(Service).where(Service.service_name == service_name)
    result = await db.execute(query)
    services = result.scalars().all()

    if not services:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_name} not found on any node",
        )

    # Update category on all records
    for svc in services:
        svc.category = update.category

    await db.commit()

    logger.info(
        "Service %s category updated to %s across %d nodes",
        service_name,
        update.category,
        len(services),
    )

    return {
        "service_name": service_name,
        "category": update.category,
        "nodes_updated": len(services),
    }


@fleet_router.post(
    "/services/{service_name}/start",
    response_model=ServiceActionResponse,
)
async def start_fleet_service(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceActionResponse:
    """
    Start a service on all nodes that have it.

    Issue #850: Moved from /fleet/services/{name}/start to /orchestration/fleet/services/{name}/start.
    """
    # Find all nodes with this service
    query = select(Service).where(Service.service_name == service_name)
    result = await db.execute(query)
    services = result.scalars().all()

    if not services:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_name} not found on any node",
        )

    # Get nodes
    node_ids = [s.node_id for s in services]
    nodes_result = await db.execute(select(Node).where(Node.node_id.in_(node_ids)))
    nodes = {n.node_id: n for n in nodes_result.scalars().all()}

    # Start on each node
    success_count = 0
    fail_count = 0
    for svc in services:
        node = nodes.get(svc.node_id)
        if not node:
            fail_count += 1
            continue

        success, msg = await _run_ssh_service_action(node, service_name, "start")
        if success:
            success_count += 1
            svc.status = ServiceStatus.RUNNING.value
            svc.active_state = "active"
            svc.sub_state = "running"
            svc.last_checked = datetime.utcnow()
            # Broadcast status change for this node
            await ws_manager.send_service_status(
                node_id=svc.node_id,
                service_name=service_name,
                status="running",
                action="start",
                success=True,
                message=msg,
            )
        else:
            fail_count += 1
            await ws_manager.send_service_status(
                node_id=svc.node_id,
                service_name=service_name,
                status="unknown",
                action="start",
                success=False,
                message=msg,
            )

    await db.commit()

    return ServiceActionResponse(
        action="start",
        service_name=service_name,
        node_id="fleet",
        success=fail_count == 0,
        message=f"Started on {success_count}/{len(services)} nodes",
    )


@fleet_router.post(
    "/services/{service_name}/stop",
    response_model=ServiceActionResponse,
)
async def stop_fleet_service(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceActionResponse:
    """
    Stop a service on all nodes.

    Issue #850: Moved from /fleet/services/{name}/stop to /orchestration/fleet/services/{name}/stop.
    """
    query = select(Service).where(Service.service_name == service_name)
    result = await db.execute(query)
    services = result.scalars().all()

    if not services:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_name} not found on any node",
        )

    node_ids = [s.node_id for s in services]
    nodes_result = await db.execute(select(Node).where(Node.node_id.in_(node_ids)))
    nodes = {n.node_id: n for n in nodes_result.scalars().all()}

    success_count = 0
    fail_count = 0
    for svc in services:
        node = nodes.get(svc.node_id)
        if not node:
            fail_count += 1
            continue

        success, msg = await _run_ssh_service_action(node, service_name, "stop")
        if success:
            success_count += 1
            svc.status = ServiceStatus.STOPPED.value
            svc.active_state = "inactive"
            svc.sub_state = "dead"
            svc.last_checked = datetime.utcnow()
            # Broadcast status change for this node
            await ws_manager.send_service_status(
                node_id=svc.node_id,
                service_name=service_name,
                status="stopped",
                action="stop",
                success=True,
                message=msg,
            )
        else:
            fail_count += 1
            await ws_manager.send_service_status(
                node_id=svc.node_id,
                service_name=service_name,
                status="unknown",
                action="stop",
                success=False,
                message=msg,
            )

    await db.commit()

    return ServiceActionResponse(
        action="stop",
        service_name=service_name,
        node_id="fleet",
        success=fail_count == 0,
        message=f"Stopped on {success_count}/{len(services)} nodes",
    )


@fleet_router.post(
    "/services/{service_name}/restart",
    response_model=ServiceActionResponse,
)
async def restart_fleet_service(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceActionResponse:
    """
    Restart a service on all nodes that have it.

    Issue #850: Moved from /fleet/services/{name}/restart to /orchestration/fleet/services/{name}/restart.
    """
    query = select(Service).where(Service.service_name == service_name)
    result = await db.execute(query)
    services = result.scalars().all()

    if not services:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_name} not found on any node",
        )

    node_ids = [s.node_id for s in services]
    nodes_result = await db.execute(select(Node).where(Node.node_id.in_(node_ids)))
    nodes = {n.node_id: n for n in nodes_result.scalars().all()}

    success_count = 0
    fail_count = 0
    for svc in services:
        node = nodes.get(svc.node_id)
        if not node:
            fail_count += 1
            continue

        success, msg = await _run_ssh_service_action(node, service_name, "restart")
        if success:
            success_count += 1
            svc.status = ServiceStatus.RUNNING.value
            svc.active_state = "active"
            svc.sub_state = "running"
            svc.last_checked = datetime.utcnow()
            # Broadcast status change for this node
            await ws_manager.send_service_status(
                node_id=svc.node_id,
                service_name=service_name,
                status="running",
                action="restart",
                success=True,
                message=msg,
            )
        else:
            fail_count += 1
            await ws_manager.send_service_status(
                node_id=svc.node_id,
                service_name=service_name,
                status="unknown",
                action="restart",
                success=False,
                message=msg,
            )

    await db.commit()

    return ServiceActionResponse(
        action="restart",
        service_name=service_name,
        node_id="fleet",
        success=fail_count == 0,
        message=f"Restarted on {success_count}/{len(services)} nodes",
    )


# Include fleet sub-router in main orchestration router
router.include_router(fleet_router)
