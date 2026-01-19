# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Services API Routes

API endpoints for managing systemd services on nodes.
Related to Issue #728.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Node, Service, ServiceStatus
from models.schemas import (
    ServiceResponse,
    ServiceListResponse,
    ServiceActionResponse,
    ServiceLogsResponse,
    FleetServiceStatus,
    FleetServicesResponse,
)
from services.auth import get_current_user
from services.database import get_db

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
) -> tuple[bool, str]:
    """
    Run Ansible playbook to control a service.

    Returns (success, message).
    """
    import tempfile
    import os

    # Build inventory
    inventory_content = f"""[target]
{node.ip_address} ansible_user={node.ssh_user} ansible_port={node.ssh_port}
"""

    # Build playbook
    playbook_content = f"""---
- name: Service {action}
  hosts: target
  become: yes
  gather_facts: no
  tasks:
    - name: {action.capitalize()} service {service_name}
      ansible.builtin.systemd:
        name: {service_name}
        state: {"started" if action == "start" else "stopped" if action == "stop" else "restarted"}
"""

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            inv_path = os.path.join(tmpdir, "inventory")
            pb_path = os.path.join(tmpdir, "playbook.yml")

            with open(inv_path, "w", encoding="utf-8") as f:
                f.write(inventory_content)
            with open(pb_path, "w", encoding="utf-8") as f:
                f.write(playbook_content)

            # Run ansible-playbook
            cmd = [
                "ansible-playbook",
                "-i", inv_path,
                pb_path,
                "--timeout", "30",
            ]

            # Add SSH key if key-based auth
            if node.auth_method == "key":
                cmd.extend(["--private-key", "/home/autobot/.ssh/id_rsa"])

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60.0,
            )

            if process.returncode == 0:
                return True, f"Service {service_name} {action} completed"
            else:
                error = stderr.decode("utf-8", errors="replace")
                logger.error(
                    "Ansible service action failed: %s", error[:500]
                )
                return False, f"Failed to {action} service: {error[:200]}"

    except asyncio.TimeoutError:
        return False, f"Timeout waiting for {action} to complete"
    except Exception as e:
        logger.exception("Service action error: %s", e)
        return False, f"Error: {str(e)[:200]}"


async def _run_ansible_get_logs(
    node: Node,
    service_name: str,
    lines: int = 100,
    since: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Run Ansible to fetch service logs via journalctl.

    Returns (success, logs_or_error).
    """
    import tempfile
    import os

    # Build journalctl command
    journal_cmd = f"journalctl -u {service_name} -n {lines} --no-pager"
    if since:
        journal_cmd += f" --since='{since}'"

    inventory_content = f"""[target]
{node.ip_address} ansible_user={node.ssh_user} ansible_port={node.ssh_port}
"""

    playbook_content = f"""---
- name: Get service logs
  hosts: target
  become: yes
  gather_facts: no
  tasks:
    - name: Fetch logs for {service_name}
      ansible.builtin.shell: "{journal_cmd}"
      register: logs_output
      ignore_errors: yes

    - name: Output logs
      debug:
        var: logs_output.stdout
"""

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            inv_path = os.path.join(tmpdir, "inventory")
            pb_path = os.path.join(tmpdir, "playbook.yml")

            with open(inv_path, "w", encoding="utf-8") as f:
                f.write(inventory_content)
            with open(pb_path, "w", encoding="utf-8") as f:
                f.write(playbook_content)

            cmd = [
                "ansible-playbook",
                "-i", inv_path,
                pb_path,
                "--timeout", "30",
            ]

            if node.auth_method == "key":
                cmd.extend(["--private-key", "/home/autobot/.ssh/id_rsa"])

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60.0,
            )

            output = stdout.decode("utf-8", errors="replace")

            # Extract logs from Ansible output
            # Look for the debug output
            if "logs_output.stdout" in output:
                # Parse the JSON-like output
                import re
                match = re.search(
                    r'"logs_output\.stdout":\s*"([^"]*)"',
                    output,
                    re.DOTALL
                )
                if match:
                    logs = match.group(1).replace("\\n", "\n")
                    return True, logs

            # Fallback: return raw output
            if process.returncode == 0:
                return True, output
            else:
                return False, stderr.decode("utf-8", errors="replace")[:500]

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

    success, message = await _run_ansible_service_action(
        node, service_name, "start"
    )

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

    success, message = await _run_ansible_service_action(
        node, service_name, "stop"
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
            service.status = ServiceStatus.STOPPED.value
            service.active_state = "inactive"
            service.sub_state = "dead"
            service.last_checked = datetime.utcnow()
            await db.commit()

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
    """Restart a service on a node."""
    node = await _get_node_or_404(db, node_id)

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

    success, logs = await _run_ansible_get_logs(
        node, service_name, lines, since
    )

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
    service_map: dict[str, list] = {}
    for svc in all_services:
        if svc.service_name not in service_map:
            service_map[svc.service_name] = []
        node = nodes.get(svc.node_id)
        service_map[svc.service_name].append({
            "node_id": svc.node_id,
            "hostname": node.hostname if node else "unknown",
            "status": svc.status,
        })

    # Build response
    fleet_services = []
    for service_name, node_statuses in service_map.items():
        running = sum(1 for n in node_statuses if n["status"] == "running")
        stopped = sum(1 for n in node_statuses if n["status"] == "stopped")
        failed = sum(1 for n in node_statuses if n["status"] == "failed")

        fleet_services.append(
            FleetServiceStatus(
                service_name=service_name,
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
    nodes_result = await db.execute(
        select(Node).where(Node.node_id.in_(node_ids))
    )
    nodes = {n.node_id: n for n in nodes_result.scalars().all()}

    # Start on each node
    success_count = 0
    fail_count = 0
    for svc in services:
        node = nodes.get(svc.node_id)
        if not node:
            fail_count += 1
            continue

        success, _ = await _run_ansible_service_action(node, service_name, "start")
        if success:
            success_count += 1
            svc.status = ServiceStatus.RUNNING.value
            svc.active_state = "active"
            svc.sub_state = "running"
            svc.last_checked = datetime.utcnow()
        else:
            fail_count += 1

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
    nodes_result = await db.execute(
        select(Node).where(Node.node_id.in_(node_ids))
    )
    nodes = {n.node_id: n for n in nodes_result.scalars().all()}

    success_count = 0
    fail_count = 0
    for svc in services:
        node = nodes.get(svc.node_id)
        if not node:
            fail_count += 1
            continue

        success, _ = await _run_ansible_service_action(node, service_name, "stop")
        if success:
            success_count += 1
            svc.status = ServiceStatus.STOPPED.value
            svc.active_state = "inactive"
            svc.sub_state = "dead"
            svc.last_checked = datetime.utcnow()
        else:
            fail_count += 1

    await db.commit()

    return ServiceActionResponse(
        action="stop",
        service_name=service_name,
        node_id="fleet",
        success=fail_count == 0,
        message=f"Stopped on {success_count}/{len(services)} nodes",
    )
