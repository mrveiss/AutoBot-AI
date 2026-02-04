# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Services API Routes

API endpoints for managing systemd services on nodes.
Related to Issue #728.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

from api.websocket import ws_manager
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import Node, Service, ServiceConflict, ServiceStatus
from models.schemas import (
    FleetServicesResponse,
    FleetServiceStatus,
    RestartAllServicesRequest,
    RestartAllServicesResponse,
    ServiceActionResponse,
    ServiceCategoryUpdate,
    ServiceConflictCreateRequest,
    ServiceConflictListResponse,
    ServiceConflictResponse,
    ServiceListResponse,
    ServiceLogsResponse,
    ServiceResponse,
    ServiceScanResponse,
)
from services.auth import get_current_user
from services.database import get_db
from services.service_categorizer import categorize_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nodes", tags=["services"])


async def _get_node_or_404(db: AsyncSession, node_id: str) -> Node:
    """Get node or raise 404."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    return node


async def _run_ansible_service_action(
    node: Node,
    service_name: str,
    action: str,
) -> Tuple[bool, str]:
    """
    Run SSH command to control a service via systemctl.

    Returns (success, message).
    """
    # Map action to systemctl command
    systemctl_action = action
    if action == "start":
        systemctl_action = "start"
    elif action == "stop":
        systemctl_action = "stop"
    elif action == "restart":
        systemctl_action = "restart"

    # Build SSH command
    ssh_user = node.ssh_user or "autobot"
    ssh_port = node.ssh_port or 22
    ssh_key = "/home/autobot/.ssh/id_rsa"

    # Use sudo -n (non-interactive) to run systemctl as root
    remote_cmd = f"sudo -n systemctl {systemctl_action} {service_name}"

    ssh_cmd = [
        "/usr/bin/ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "BatchMode=yes",
        "-i",
        ssh_key,
        "-p",
        str(ssh_port),
        f"{ssh_user}@{node.ip_address}",
        remote_cmd,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=30.0,
        )

        if process.returncode == 0:
            logger.info(
                "Service %s %s on %s completed", service_name, action, node.hostname
            )
            return True, f"Service {service_name} {action} completed"
        else:
            error = stderr.decode("utf-8", errors="replace")
            logger.error("Service action failed on %s: %s", node.hostname, error[:500])
            return False, f"Failed to {action} service: {error[:200]}"

    except asyncio.TimeoutError:
        return False, f"Timeout waiting for {action} to complete"
    except Exception as e:
        logger.exception("Service action error: %s", e)
        return False, f"Error: {str(e)[:200]}"


# Port mapping for services that bind to specific ports
SERVICE_PORT_MAP = {
    "autobot-frontend": 5173,
    "autobot-backend": 8001,
    "slm-backend": 8000,
    "slm-admin-ui": 5174,
    "redis-server": 6379,
    "redis": 6379,
    "grafana-server": 3000,
    "prometheus": 9090,
    "nginx": 80,
}


async def _kill_orphan_on_port(node: Node, port: int) -> Tuple[bool, str]:
    """
    Kill any orphaned process using a specific port on a node.

    This is needed when a service fails to start due to "Port already in use"
    but the blocking process is not managed by systemd (orphaned process).

    Returns (killed_something, message).
    """
    ssh_user = node.ssh_user or "autobot"
    ssh_port = node.ssh_port or 22
    ssh_key = "/home/autobot/.ssh/id_rsa"

    # Command to find and kill process on port
    # Using fuser which is more reliable than lsof for this purpose
    kill_cmd = f"sudo -n fuser -k {port}/tcp 2>/dev/null || true"

    ssh_cmd = [
        "/usr/bin/ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "BatchMode=yes",
        "-i",
        ssh_key,
        "-p",
        str(ssh_port),
        f"{ssh_user}@{node.ip_address}",
        kill_cmd,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        await asyncio.wait_for(process.communicate(), timeout=15.0)
        logger.info("Killed orphan processes on port %d on %s", port, node.hostname)
        return True, f"Killed orphan processes on port {port}"

    except Exception as e:
        logger.warning("Could not kill orphan on port %d: %s", port, e)
        return False, str(e)


async def _run_ansible_get_logs(
    node: Node,
    service_name: str,
    lines: int = 100,
    since: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Fetch service logs via SSH and journalctl.

    Returns (success, logs_or_error).
    """
    # Build journalctl command (sudo -n for non-interactive)
    journal_cmd = f"sudo -n journalctl -u {service_name} -n {lines} --no-pager"
    if since:
        journal_cmd += f" --since='{since}'"

    # Build SSH command
    ssh_user = node.ssh_user or "autobot"
    ssh_port = node.ssh_port or 22
    ssh_key = "/home/autobot/.ssh/id_rsa"

    ssh_cmd = [
        "/usr/bin/ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "BatchMode=yes",
        "-i",
        ssh_key,
        "-p",
        str(ssh_port),
        f"{ssh_user}@{node.ip_address}",
        journal_cmd,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=30.0,
        )

        if process.returncode == 0:
            logs = stdout.decode("utf-8", errors="replace")
            return True, logs
        else:
            error = stderr.decode("utf-8", errors="replace")
            return False, f"Failed to fetch logs: {error[:200]}"

    except asyncio.TimeoutError:
        return False, "Timeout fetching logs"
    except Exception as e:
        logger.exception("Get logs error: %s", e)
        return False, f"Error: {str(e)[:200]}"


@router.get("/{node_id}/services", response_model=ServiceListResponse)
async def list_node_services(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> ServiceListResponse:
    """List all services on a node."""
    await _get_node_or_404(db, node_id)

    query = select(Service).where(Service.node_id == node_id)

    if status_filter:
        query = query.where(Service.status == status_filter)

    if search:
        query = query.where(Service.service_name.ilike(f"%{search}%"))

    query = query.order_by(Service.service_name)

    # Count total
    count_query = select(func.count(Service.id)).where(Service.node_id == node_id)
    if status_filter:
        count_query = count_query.where(Service.status == status_filter)
    if search:
        count_query = count_query.where(Service.service_name.ilike(f"%{search}%"))

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    services = result.scalars().all()

    return ServiceListResponse(
        services=[ServiceResponse.model_validate(s) for s in services],
        total=total,
    )


@router.post("/{node_id}/services/scan", response_model=ServiceScanResponse)
async def scan_node_services(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceScanResponse:
    """
    Manually scan and refresh services on a node via SSH.

    This endpoint discovers all systemd services on the node by running
    'systemctl list-units --type=service' via SSH and updates the database.
    """
    node = await _get_node_or_404(db, node_id)

    # Build SSH command to list all services
    ssh_user = node.ssh_user or "autobot"
    ssh_port = node.ssh_port or 22
    ssh_key = "/home/autobot/.ssh/id_rsa"

    # Get detailed service info in JSON-like format
    remote_cmd = (
        "systemctl list-units --type=service --all --no-pager --plain "
        "--output=json 2>/dev/null || "
        "systemctl list-units --type=service --all --no-pager --plain"
    )

    ssh_cmd = [
        "/usr/bin/ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "BatchMode=yes",
        "-i",
        ssh_key,
        "-p",
        str(ssh_port),
        f"{ssh_user}@{node.ip_address}",
        remote_cmd,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=60.0,
        )

        if process.returncode != 0:
            error = stderr.decode("utf-8", errors="replace")
            logger.error("Service scan failed on %s: %s", node.hostname, error[:500])
            return ServiceScanResponse(
                node_id=node_id,
                success=False,
                message=f"SSH command failed: {error[:200]}",
                services_discovered=0,
                services_updated=0,
                services_created=0,
            )

        output = stdout.decode("utf-8", errors="replace")
        services_discovered = 0
        services_updated = 0
        services_created = 0
        now = datetime.utcnow()

        # Parse output - handle both JSON and plain formats
        try:
            services_data = json.loads(output)
            # JSON format from newer systemd
            for svc in services_data:
                service_name = svc.get("unit", "").replace(".service", "")
                if not service_name:
                    continue
                services_discovered += 1
                created, updated = await _upsert_service(
                    db, node_id, service_name, svc, now
                )
                if created:
                    services_created += 1
                elif updated:
                    services_updated += 1
        except json.JSONDecodeError:
            # Plain text format - parse line by line
            for line in output.strip().split("\n"):
                if not line.strip() or line.startswith("UNIT"):
                    continue
                parts = line.split()
                if len(parts) < 4:
                    continue
                service_name = parts[0].replace(".service", "")
                if not service_name:
                    continue
                services_discovered += 1

                # Parse status from columns: UNIT LOAD ACTIVE SUB DESCRIPTION...
                active_state = parts[2] if len(parts) > 2 else "unknown"
                sub_state = parts[3] if len(parts) > 3 else "unknown"
                description = " ".join(parts[4:]) if len(parts) > 4 else None

                svc_data = {
                    "active": active_state,
                    "sub": sub_state,
                    "description": description,
                }
                created, updated = await _upsert_service(
                    db, node_id, service_name, svc_data, now
                )
                if created:
                    services_created += 1
                elif updated:
                    services_updated += 1

        await db.commit()
        logger.info(
            "Service scan on %s: %d discovered, %d created, %d updated",
            node.hostname,
            services_discovered,
            services_created,
            services_updated,
        )

        return ServiceScanResponse(
            node_id=node_id,
            success=True,
            message=f"Scan complete: {services_discovered} services discovered",
            services_discovered=services_discovered,
            services_updated=services_updated,
            services_created=services_created,
        )

    except asyncio.TimeoutError:
        logger.warning("Service scan timeout on %s", node.hostname)
        return ServiceScanResponse(
            node_id=node_id,
            success=False,
            message="SSH command timed out",
            services_discovered=0,
            services_updated=0,
            services_created=0,
        )
    except Exception as e:
        logger.exception("Service scan error on %s: %s", node.hostname, e)
        return ServiceScanResponse(
            node_id=node_id,
            success=False,
            message=f"Error: {str(e)[:200]}",
            services_discovered=0,
            services_updated=0,
            services_created=0,
        )


async def _upsert_service(
    db: AsyncSession,
    node_id: str,
    service_name: str,
    svc_data: dict,
    now: datetime,
) -> Tuple[bool, bool]:
    """
    Insert or update a service record.

    Returns (created, updated) tuple.
    """
    # Map systemd states to our status enum
    active_state = svc_data.get("active", "unknown")
    sub_state = svc_data.get("sub", "unknown")

    if active_state == "active" and sub_state == "running":
        status = ServiceStatus.RUNNING.value
    elif active_state == "inactive" or sub_state == "dead":
        status = ServiceStatus.STOPPED.value
    elif active_state == "failed":
        status = ServiceStatus.FAILED.value
    else:
        status = ServiceStatus.UNKNOWN.value

    # Check if service exists
    result = await db.execute(
        select(Service).where(
            Service.node_id == node_id,
            Service.service_name == service_name,
        )
    )
    service = result.scalar_one_or_none()

    if service:
        # Update existing
        service.status = status
        service.active_state = active_state
        service.sub_state = sub_state
        service.description = svc_data.get("description") or service.description
        service.last_checked = now
        return False, True
    else:
        # Create new
        category = categorize_service(service_name)
        service = Service(
            node_id=node_id,
            service_name=service_name,
            status=status,
            category=category,
            active_state=active_state,
            sub_state=sub_state,
            description=svc_data.get("description"),
            enabled=False,  # Will be updated on next detailed scan
            last_checked=now,
        )
        db.add(service)
        return True, False


@router.post(
    "/{node_id}/services/{service_name}/start",
    response_model=ServiceActionResponse,
)
async def start_service(
    node_id: str,
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceActionResponse:
    """Start a service on a node."""
    node = await _get_node_or_404(db, node_id)

    success, message = await _run_ansible_service_action(node, service_name, "start")

    # Update service status in DB if we have a record
    if success:
        result = await db.execute(
            select(Service).where(
                Service.node_id == node_id,
                Service.service_name == service_name,
            )
        )
        service = result.scalar_one_or_none()
        if service:
            service.status = ServiceStatus.RUNNING.value
            service.active_state = "active"
            service.sub_state = "running"
            service.last_checked = datetime.utcnow()
            await db.commit()

        # Broadcast status change via WebSocket
        await ws_manager.send_service_status(
            node_id=node_id,
            service_name=service_name,
            status="running",
            action="start",
            success=True,
            message=message,
        )
    else:
        # Broadcast failure
        await ws_manager.send_service_status(
            node_id=node_id,
            service_name=service_name,
            status="unknown",
            action="start",
            success=False,
            message=message,
        )

    return ServiceActionResponse(
        action="start",
        service_name=service_name,
        node_id=node_id,
        success=success,
        message=message,
    )


@router.post(
    "/{node_id}/services/{service_name}/stop",
    response_model=ServiceActionResponse,
)
async def stop_service(
    node_id: str,
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceActionResponse:
    """Stop a service on a node."""
    node = await _get_node_or_404(db, node_id)

    success, message = await _run_ansible_service_action(node, service_name, "stop")

    if success:
        result = await db.execute(
            select(Service).where(
                Service.node_id == node_id,
                Service.service_name == service_name,
            )
        )
        service = result.scalar_one_or_none()
        if service:
            service.status = ServiceStatus.STOPPED.value
            service.active_state = "inactive"
            service.sub_state = "dead"
            service.last_checked = datetime.utcnow()
            await db.commit()

        # Broadcast status change via WebSocket
        await ws_manager.send_service_status(
            node_id=node_id,
            service_name=service_name,
            status="stopped",
            action="stop",
            success=True,
            message=message,
        )
    else:
        await ws_manager.send_service_status(
            node_id=node_id,
            service_name=service_name,
            status="unknown",
            action="stop",
            success=False,
            message=message,
        )

    return ServiceActionResponse(
        action="stop",
        service_name=service_name,
        node_id=node_id,
        success=success,
        message=message,
    )


@router.post(
    "/{node_id}/services/{service_name}/restart",
    response_model=ServiceActionResponse,
)
async def restart_service(
    node_id: str,
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceActionResponse:
    """Restart a service on a node.

    For services that bind to specific ports, this will:
    1. Stop the service
    2. Kill any orphaned processes on the port
    3. Start the service

    This ensures orphaned processes don't block the service from starting.
    """
    node = await _get_node_or_404(db, node_id)

    # Check if service uses a known port - if so, do stop/kill/start
    port = SERVICE_PORT_MAP.get(service_name)
    if port:
        # Stop service first
        await _run_ansible_service_action(node, service_name, "stop")
        # Small delay to let port release
        await asyncio.sleep(1)
        # Kill any orphan processes on the port
        await _kill_orphan_on_port(node, port)
        # Small delay after kill
        await asyncio.sleep(1)
        # Start the service
        success, message = await _run_ansible_service_action(
            node, service_name, "start"
        )
    else:
        # Regular restart for services without known ports
        success, message = await _run_ansible_service_action(
            node, service_name, "restart"
        )

    if success:
        result = await db.execute(
            select(Service).where(
                Service.node_id == node_id,
                Service.service_name == service_name,
            )
        )
        service = result.scalar_one_or_none()
        if service:
            service.status = ServiceStatus.RUNNING.value
            service.active_state = "active"
            service.sub_state = "running"
            service.last_checked = datetime.utcnow()
            await db.commit()

        # Broadcast status change via WebSocket
        await ws_manager.send_service_status(
            node_id=node_id,
            service_name=service_name,
            status="running",
            action="restart",
            success=True,
            message=message,
        )
    else:
        await ws_manager.send_service_status(
            node_id=node_id,
            service_name=service_name,
            status="unknown",
            action="restart",
            success=False,
            message=message,
        )

    return ServiceActionResponse(
        action="restart",
        service_name=service_name,
        node_id=node_id,
        success=success,
        message=message,
    )


@router.get(
    "/{node_id}/services/{service_name}/logs",
    response_model=ServiceLogsResponse,
)
async def get_service_logs(
    node_id: str,
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    lines: int = Query(100, ge=1, le=1000),
    since: Optional[str] = Query(None, description="Time period, e.g. '1h', '30m'"),
) -> ServiceLogsResponse:
    """Get logs for a service on a node."""
    node = await _get_node_or_404(db, node_id)

    success, logs = await _run_ansible_get_logs(node, service_name, lines, since)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch logs: {logs}",
        )

    return ServiceLogsResponse(
        service_name=service_name,
        node_id=node_id,
        logs=logs,
        lines_returned=len(logs.split("\n")),
    )


# =============================================================================
# Restart All Services endpoint (Issue #725)
# =============================================================================


@router.post(
    "/{node_id}/services/restart-all",
    response_model=RestartAllServicesResponse,
)
async def restart_all_node_services(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    request: Optional[RestartAllServicesRequest] = None,
) -> RestartAllServicesResponse:
    """
    Restart all services on a node in ordered sequence.

    The SLM agent is always restarted last to ensure the node remains
    manageable during the restart process. Other services are restarted
    in alphabetical order.

    Related to Issue #725.
    """
    node = await _get_node_or_404(db, node_id)

    # Get all services on this node
    query = select(Service).where(Service.node_id == node_id)

    # Filter by category if specified
    if request and request.category and request.category != "all":
        query = query.where(Service.category == request.category)

    result = await db.execute(query)
    all_services = result.scalars().all()

    if not all_services:
        return RestartAllServicesResponse(
            node_id=node_id,
            success=True,
            message="No services to restart",
            total_services=0,
            successful_restarts=0,
            failed_restarts=0,
            results=[],
            slm_agent_restarted=False,
        )

    # Separate SLM services from other services (SLM services restart last)
    # SLM services include: slm-agent, slm-backend, slm-admin-ui, and any slm-* service
    SLM_SERVICE_NAMES = {"slm-agent", "slm-backend", "slm-admin-ui"}

    def is_slm_service(service_name: str) -> bool:
        """Check if a service is an SLM service that should restart last."""
        return service_name in SLM_SERVICE_NAMES or service_name.startswith("slm-")

    slm_services = []
    other_services = []
    excluded_services = request.exclude_services if request else []

    for svc in all_services:
        if svc.service_name in excluded_services:
            continue
        if is_slm_service(svc.service_name):
            slm_services.append(svc)
        else:
            other_services.append(svc)

    # Sort services alphabetically (SLM services included, they'll be appended at end)
    other_services.sort(key=lambda s: s.service_name)
    slm_services.sort(key=lambda s: s.service_name)

    # Build ordered restart list: other services first, then SLM services (restart last)
    ordered_services = other_services + slm_services

    # Execute restarts sequentially
    results = []
    successful = 0
    failed = 0
    slm_agent_restarted = False

    for svc in ordered_services:
        is_slm = is_slm_service(svc.service_name)

        logger.info(
            "Restarting service %s on %s%s",
            svc.service_name,
            node.hostname,
            " (SLM service - last)" if is_slm else "",
        )

        success, message = await _run_ansible_service_action(
            node, svc.service_name, "restart"
        )

        results.append(
            {
                "service_name": svc.service_name,
                "success": success,
                "message": message,
                "is_slm_agent": is_slm,  # Indicates any SLM service
            }
        )

        if success:
            successful += 1
            svc.status = ServiceStatus.RUNNING.value
            svc.active_state = "active"
            svc.sub_state = "running"
            svc.last_checked = datetime.utcnow()

            if is_slm:
                slm_agent_restarted = True

            # Broadcast status change via WebSocket
            await ws_manager.send_service_status(
                node_id=node_id,
                service_name=svc.service_name,
                status="running",
                action="restart",
                success=True,
                message=message,
            )
        else:
            failed += 1
            await ws_manager.send_service_status(
                node_id=node_id,
                service_name=svc.service_name,
                status="unknown",
                action="restart",
                success=False,
                message=message,
            )

            # If a service fails, continue with others
            # SLM services failing is logged but we continue
            logger.error(
                "Failed to restart %s on %s: %s",
                svc.service_name,
                node.hostname,
                message,
            )

    await db.commit()

    total = len(ordered_services)
    overall_success = failed == 0

    return RestartAllServicesResponse(
        node_id=node_id,
        success=overall_success,
        message=(
            f"Successfully restarted {successful}/{total} services"
            if overall_success
            else f"Restarted {successful}/{total} services, {failed} failed"
        ),
        total_services=total,
        successful_restarts=successful,
        failed_restarts=failed,
        results=results,
        slm_agent_restarted=slm_agent_restarted,
    )


# =============================================================================
# Service Conflicts endpoints (Issue #760)
# =============================================================================


@router.get("/conflicts", response_model=ServiceConflictListResponse)
async def list_service_conflicts(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceConflictListResponse:
    """List all known service conflicts."""
    result = await db.execute(
        select(ServiceConflict).order_by(ServiceConflict.service_name_a)
    )
    conflicts = result.scalars().all()

    return ServiceConflictListResponse(
        conflicts=[ServiceConflictResponse.model_validate(c) for c in conflicts],
        total=len(conflicts),
    )


@router.post("/conflicts", response_model=ServiceConflictResponse, status_code=201)
async def create_service_conflict(
    request: ServiceConflictCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceConflictResponse:
    """Create a new service conflict."""
    # Normalize order (alphabetical) to prevent duplicates
    service_a, service_b = sorted([request.service_a, request.service_b])

    # Check if already exists
    result = await db.execute(
        select(ServiceConflict).where(
            ServiceConflict.service_name_a == service_a,
            ServiceConflict.service_name_b == service_b,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict already exists",
        )

    conflict = ServiceConflict(
        service_name_a=service_a,
        service_name_b=service_b,
        reason=request.reason,
        conflict_type=request.conflict_type,
    )
    db.add(conflict)
    await db.commit()
    await db.refresh(conflict)

    logger.info(
        "Created service conflict: %s <-> %s (%s)",
        service_a,
        service_b,
        request.conflict_type,
    )

    return ServiceConflictResponse.model_validate(conflict)


@router.delete("/conflicts/{conflict_id}")
async def delete_service_conflict(
    conflict_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Delete a service conflict."""
    result = await db.execute(
        select(ServiceConflict).where(ServiceConflict.id == conflict_id)
    )
    conflict = result.scalar_one_or_none()

    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conflict not found",
        )

    await db.delete(conflict)
    await db.commit()

    logger.info(
        "Deleted service conflict: %s <-> %s",
        conflict.service_name_a,
        conflict.service_name_b,
    )

    return {"message": "Conflict deleted", "id": conflict_id}


@router.get("/{service_name}/conflicts")
async def get_service_conflicts(
    service_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ServiceConflictListResponse:
    """Get all conflicts for a specific service."""
    result = await db.execute(
        select(ServiceConflict).where(
            (ServiceConflict.service_name_a == service_name)
            | (ServiceConflict.service_name_b == service_name)
        )
    )
    conflicts = result.scalars().all()

    return ServiceConflictListResponse(
        conflicts=[ServiceConflictResponse.model_validate(c) for c in conflicts],
        total=len(conflicts),
    )


# =============================================================================
# Fleet-wide service endpoints
# =============================================================================

fleet_router = APIRouter(prefix="/fleet", tags=["fleet-services"])


@fleet_router.get("/services", response_model=FleetServicesResponse)
async def get_fleet_services(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetServicesResponse:
    """Get aggregated service status across all nodes."""
    # Get all services grouped by name
    query = select(Service).order_by(Service.service_name)
    result = await db.execute(query)
    all_services = result.scalars().all()

    # Get node info for hostname lookup
    nodes_result = await db.execute(select(Node))
    nodes = {n.node_id: n for n in nodes_result.scalars().all()}

    # Aggregate by service name
    # Store both node_statuses and category (take first one found)
    service_map: Dict[str, dict] = {}
    for svc in all_services:
        if svc.service_name not in service_map:
            service_map[svc.service_name] = {
                "nodes": [],
                "category": getattr(svc, "category", "system") or "system",
            }
        node = nodes.get(svc.node_id)
        service_map[svc.service_name]["nodes"].append(
            {
                "node_id": svc.node_id,
                "hostname": node.hostname if node else "unknown",
                "status": svc.status,
            }
        )

    # Build response
    fleet_services = []
    for service_name, data in service_map.items():
        node_statuses = data["nodes"]
        running = sum(1 for n in node_statuses if n["status"] == "running")
        stopped = sum(1 for n in node_statuses if n["status"] == "stopped")
        failed = sum(1 for n in node_statuses if n["status"] == "failed")

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
async def update_service_category(
    service_name: str,
    update: ServiceCategoryUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """
    Update the category for a service across all nodes.

    This is an admin override - manually categorize a service as
    'autobot' or 'system' across all nodes that have it.
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
    """Start a service on all nodes that have it."""
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

        success, msg = await _run_ansible_service_action(node, service_name, "start")
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
    """Stop a service on all nodes."""
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

        success, msg = await _run_ansible_service_action(node, service_name, "stop")
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
    """Restart a service on all nodes that have it."""
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

        success, msg = await _run_ansible_service_action(node, service_name, "restart")
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
