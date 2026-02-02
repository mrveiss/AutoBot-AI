# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Service Discovery API Routes (Issue #760)

Endpoints for discovering service locations dynamically.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Node, Service, ServiceStatus
from models.schemas import ServiceDiscoveryListResponse, ServiceDiscoveryResponse
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/discover", tags=["discovery"])


def _build_service_url(node: Node, service: Service) -> str:
    """Build full URL for a service."""
    protocol = service.protocol or "http"
    host = node.ip_address
    port = service.port

    if port:
        base = f"{protocol}://{host}:{port}"
    else:
        base = f"{protocol}://{host}"

    if service.endpoint_path:
        return f"{base}{service.endpoint_path}"
    return base


@router.get("/{service_name}", response_model=ServiceDiscoveryResponse)
async def discover_service(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    prefer_healthy: bool = Query(True, description="Prefer healthy instances"),
) -> ServiceDiscoveryResponse:
    """
    Discover a service by name.

    Returns the first available (preferably healthy) instance of the service.
    """
    query = (
        select(Service, Node)
        .join(Node, Service.node_id == Node.node_id)
        .where(
            Service.service_name == service_name,
            Service.is_discoverable.is_(True),
        )
    )

    if prefer_healthy:
        query = query.order_by(
            (Service.status == ServiceStatus.RUNNING.value).desc(),
            Node.hostname,
        )

    result = await db.execute(query)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found or not discoverable",
        )

    service, node = row
    is_healthy = service.status == ServiceStatus.RUNNING.value

    return ServiceDiscoveryResponse(
        service_name=service.service_name,
        host=node.ip_address,
        port=service.port,
        protocol=service.protocol or "http",
        endpoint_path=service.endpoint_path,
        url=_build_service_url(node, service),
        healthy=is_healthy,
        node_id=node.node_id,
    )


@router.get("/{service_name}/all")
async def discover_service_all(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Discover all instances of a service.

    Returns all instances for load balancing or failover scenarios.
    """
    query = (
        select(Service, Node)
        .join(Node, Service.node_id == Node.node_id)
        .where(
            Service.service_name == service_name,
            Service.is_discoverable.is_(True),
        )
        .order_by(Node.hostname)
    )

    result = await db.execute(query)
    rows = result.all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found or not discoverable",
        )

    instances = []
    for service, node in rows:
        is_healthy = service.status == ServiceStatus.RUNNING.value
        instances.append(
            ServiceDiscoveryResponse(
                service_name=service.service_name,
                host=node.ip_address,
                port=service.port,
                protocol=service.protocol or "http",
                endpoint_path=service.endpoint_path,
                url=_build_service_url(node, service),
                healthy=is_healthy,
                node_id=node.node_id,
            )
        )

    return {"instances": instances, "total": len(instances)}


@router.get("", response_model=ServiceDiscoveryListResponse)
async def discover_all_services(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    healthy_only: bool = Query(False, description="Only return healthy services"),
) -> ServiceDiscoveryListResponse:
    """
    Discover all services.

    Returns all discoverable services grouped by service name.
    """
    query = (
        select(Service, Node)
        .join(Node, Service.node_id == Node.node_id)
        .where(Service.is_discoverable.is_(True))
    )

    if healthy_only:
        query = query.where(Service.status == ServiceStatus.RUNNING.value)

    query = query.order_by(Service.service_name, Node.hostname)

    result = await db.execute(query)
    rows = result.all()

    services_map: dict = {}
    for service, node in rows:
        if service.service_name not in services_map:
            services_map[service.service_name] = []

        is_healthy = service.status == ServiceStatus.RUNNING.value
        services_map[service.service_name].append(
            ServiceDiscoveryResponse(
                service_name=service.service_name,
                host=node.ip_address,
                port=service.port,
                protocol=service.protocol or "http",
                endpoint_path=service.endpoint_path,
                url=_build_service_url(node, service),
                healthy=is_healthy,
                node_id=node.node_id,
            )
        )

    return ServiceDiscoveryListResponse(services=services_map)
