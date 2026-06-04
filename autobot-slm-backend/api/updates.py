# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Updates API Routes

Provides update management with job tracking and status polling.
"""

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import (
    EventSeverity,
    EventType,
    Node,
    NodeEvent,
    UpdateInfo,
    UpdateJob,
    UpdateJobStatus,
)
from models.schemas import (
    FleetUpdateSummaryResponse,
    NodeUpdateSummary,
    UpdateApplyAllRequest,
    UpdateApplyRequest,
    UpdateApplyResponse,
    UpdateCheckResponse,
    UpdateDiscoverRequest,
    UpdateDiscoverResponse,
    UpdateDiscoverStatus,
    UpdateInfoResponse,
    UpdateJobListResponse,
    UpdateJobResponse,
    UpdatePackagesResponse,
    UpdateSummaryResponse,
)
from services.auth import get_current_user
from services.database import get_db
from services.playbook_executor import get_playbook_executor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/updates", tags=["updates"])

# Track running update tasks
_running_jobs: Dict[str, asyncio.Task] = {}

# Track running discovery jobs (in-memory, transient)
_discover_jobs: Dict[str, dict] = {}


async def _create_node_event(
    db: AsyncSession,
    node_id: str,
    event_type: EventType,
    severity: EventSeverity,
    message: str,
    details: dict = None,
) -> NodeEvent:
    """Helper to create a node event."""
    event = NodeEvent(
        event_id=str(uuid.uuid4())[:16],
        node_id=node_id,
        event_type=event_type.value,
        severity=severity.value,
        message=message,
        details=details or {},
    )
    db.add(event)
    await db.flush()
    return event


async def _broadcast_job_update(job_id: str, status: str, progress: int, message: str = None) -> None:
    """Broadcast job update via WebSocket."""
    try:
        from api.websocket import ws_manager

        await ws_manager.broadcast(
            "events:global",
            {
                "type": "update_job_progress",
                "data": {
                    "job_id": job_id,
                    "status": status,
                    "progress": progress,
                    "message": message,
                },
                "timestamp": asyncio.get_running_loop().time(),
            },
        )
    except Exception as e:
        logger.debug("Failed to broadcast job update: %s", e)


async def _get_update_job_data(db: AsyncSession, job_id: str, node_id: str, update_ids: List[str]) -> tuple | None:
    """
    Helper for _run_update_job (Issue #665).

    Fetch job, node, and updates from database. Returns tuple of (job, node, updates)
    or None if validation fails. Sets job to FAILED status if node or updates not found.
    """
    result = await db.execute(select(UpdateJob).where(UpdateJob.job_id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        logger.error("Update job not found: %s", job_id)
        return None

    node_result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = node_result.scalar_one_or_none()

    if not node:
        job.status = UpdateJobStatus.FAILED.value
        job.error = "Node not found"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return None

    updates_result = await db.execute(select(UpdateInfo).where(UpdateInfo.update_id.in_(update_ids)))
    updates = updates_result.scalars().all()

    if not updates:
        job.status = UpdateJobStatus.FAILED.value
        job.error = "No valid updates found"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return None

    return (job, node, updates)


async def _execute_update_playbook(node: Node, updates: List[UpdateInfo]) -> Dict[str, any]:
    """
    Execute Ansible playbook to apply updates.

    Helper for _run_update_job (Issue #665).
    """
    executor = get_playbook_executor()
    package_names = [u.package_name for u in updates]

    limit = _resolve_ips_to_inventory_names([node.ip_address])
    extra_vars = {
        "update_type": "specific",
        "specific_packages": ",".join(package_names),
        "dry_run": "false",
        "auto_reboot": "false",
    }

    return await executor.execute_playbook(
        playbook_name="apply-system-updates.yml",
        limit=limit,
        extra_vars=extra_vars,
    )


async def _handle_successful_update(
    db: AsyncSession,
    job: UpdateJob,
    node_id: str,
    updates: List[UpdateInfo],
    output: str,
) -> None:
    """
    Handle successful update completion.

    Helper for _run_update_job (Issue #665).
    """
    job.status = UpdateJobStatus.COMPLETED.value
    job.output = output
    job.progress = 100
    job.current_step = "Completed"
    job.completed_steps = len(updates)

    for update in updates:
        update.is_applied = True
        update.applied_at = datetime.now(timezone.utc)

    await db.commit()
    await _broadcast_job_update(job.job_id, "completed", 100, f"Completed: {len(updates)} updates applied")

    await _create_node_event(
        db,
        node_id,
        EventType.DEPLOYMENT_COMPLETED,
        EventSeverity.INFO,
        f"Update job {job.job_id} completed: {len(updates)} applied",
        {"job_id": job.job_id, "applied": len(updates)},
    )


async def _handle_failed_update(db: AsyncSession, job: UpdateJob, node_id: str, output: str) -> None:
    """
    Handle failed update completion.

    Helper for _run_update_job (Issue #665).
    """
    job.status = UpdateJobStatus.FAILED.value
    job.error = f"Playbook failed: {output[:500]}"
    job.output = output

    await db.commit()
    await _broadcast_job_update(job.job_id, "failed", job.progress, job.error)

    await _create_node_event(
        db,
        node_id,
        EventType.DEPLOYMENT_FAILED,
        EventSeverity.WARNING,
        f"Update job {job.job_id} failed",
        {"job_id": job.job_id, "error": job.error},
    )


async def _run_update_job(job_id: str, node_id: str, update_ids: List[str]) -> None:
    """Execute update job using Ansible playbook."""
    from services.database import db_service

    async with db_service.session() as db:
        job_data = await _get_update_job_data(db, job_id, node_id, update_ids)
        if not job_data:
            return

        job, node, updates = job_data

        job.status = UpdateJobStatus.RUNNING.value
        job.started_at = datetime.now(timezone.utc)
        job.total_steps = len(updates)
        await db.commit()

        await _broadcast_job_update(job_id, "running", 0, "Starting update process...")

        try:
            job.current_step = f"Applying {len(updates)} update(s) via Ansible"
            await db.commit()
            await _broadcast_job_update(job_id, "running", 50, job.current_step)

            result = await _execute_update_playbook(node, updates)

            if result["success"]:
                await _handle_successful_update(db, job, node_id, updates, result["output"])
            else:
                await _handle_failed_update(db, job, node_id, result["output"])

            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

        except asyncio.CancelledError:
            job.status = UpdateJobStatus.CANCELLED.value
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Update job cancelled: %s", job_id)
            raise

        except Exception as e:
            logger.error("Update job failed: %s - %s", job_id, e)
            job.status = UpdateJobStatus.FAILED.value
            job.error = "Internal server error"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await _broadcast_job_update(job_id, "failed", job.progress, "Update job failed")


def _parse_discover_output(output: str) -> List[dict]:
    """Parse AUTOBOT_UPDATES_JSON markers from Ansible output.

    Ansible's default callback wraps long msg values across multiple
    lines, so we search the full output and extract JSON by matching
    balanced braces rather than parsing line-by-line (#1789).
    """
    import re

    results = []
    marker = "AUTOBOT_UPDATES_JSON:"
    start = 0

    while True:
        idx = output.find(marker, start)
        if idx == -1:
            break

        brace_start = output.find("{", idx + len(marker))
        if brace_start == -1:
            break

        depth = 0
        pos = brace_start
        while pos < len(output):
            if output[pos] == "{":
                depth += 1
            elif output[pos] == "}":
                depth -= 1
                if depth == 0:
                    break
            pos += 1

        if depth != 0:
            start = idx + 1
            continue

        json_str = output[brace_start : pos + 1]
        json_str = re.sub(r"\n\s*", "", json_str)
        try:
            data = json.loads(json_str)
            results.append(data)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse discover JSON: %.200s",
                json_str,
            )
        start = pos + 1

    return results


def _parse_unreachable_hosts(output: str) -> List[str]:
    """Extract hostnames of unreachable nodes from Ansible output.

    Ansible emits lines like:
        fatal: [hostname]: UNREACHABLE! => {...}
    This function collects all such hostnames so callers can report
    partial success with a descriptive warning (Issue #1816).
    """
    import re

    pattern = re.compile(r"^fatal:\s+\[([^\]]+)\]:\s+UNREACHABLE!", re.MULTILINE)
    return list(dict.fromkeys(m.group(1) for m in pattern.finditer(output)))


async def _resolve_host_to_node(
    db: AsyncSession,
    hostname: str,
    ip_address: str | None = None,
) -> str | None:
    """Map an Ansible host back to a node_id (#1789).

    Tries hostname match first, then falls back to ip_address.
    Ansible's ansible_hostname (OS hostname) often differs from
    the display name stored in nodes.hostname, so IP is the
    reliable fallback.
    """
    result = await db.execute(select(Node).where(Node.hostname == hostname))
    node = result.scalar_one_or_none()
    if node:
        return node.node_id

    if ip_address:
        result = await db.execute(select(Node).where(Node.ip_address == ip_address))
        node = result.scalar_one_or_none()
        if node:
            return node.node_id

    return None


def _classify_severity(pkg_name: str, security_packages: List[str], repo: str = "") -> str:
    """Classify package update severity.

    A package is classified as 'security' when its name appears in the
    security_packages list (packages whose apt repo field contained '-security')
    OR when the repo field captured from the apt output itself contains '-security'.
    Using both signals handles cases where the Ansible grep and the regex capture
    produce slightly different sets.
    """
    if "-security" in repo or pkg_name in security_packages:
        return "security"
    return "standard"


async def _upsert_update_info(
    db: AsyncSession,
    node_id: str,
    pkg: dict,
    severity: str,
) -> None:
    """Insert or update an UpdateInfo record."""
    existing = await db.execute(
        select(UpdateInfo).where(
            UpdateInfo.node_id == node_id,
            UpdateInfo.package_name == pkg["p"],
            UpdateInfo.is_applied.is_(False),
        )
    )
    record = existing.scalar_one_or_none()

    if record:
        record.available_version = pkg["a"]
        record.current_version = pkg["c"]
        record.severity = severity
    else:
        new_record = UpdateInfo(
            update_id=str(uuid.uuid4())[:16],
            node_id=node_id,
            package_name=pkg["p"],
            current_version=pkg["c"],
            available_version=pkg["a"],
            severity=severity,
            is_applied=False,
        )
        db.add(new_record)


def _build_ip_to_inventory_map() -> Dict[str, str]:
    """Parse Ansible inventory to map IP addresses to inventory hostnames.

    DB hostnames are display names (e.g. '00-SLM-Manager') which don't
    match Ansible inventory hostnames (e.g. 'autobot-slm'). Ansible's
    --limit only matches inventory hostnames, so we need this mapping
    to target specific nodes (#1789).
    """
    import yaml

    executor = get_playbook_executor()
    inv_path = executor.inventory_path
    if not inv_path or not Path(inv_path).exists():
        return {}

    try:
        with open(inv_path, encoding="utf-8") as f:
            inv = yaml.safe_load(f)
    except Exception:
        logger.warning("Failed to parse inventory: %s", inv_path)
        return {}

    mapping: Dict[str, str] = {}

    def _walk(node: dict) -> None:
        if not isinstance(node, dict):
            return
        for key, val in node.items():
            if key == "hosts" and isinstance(val, dict):
                for hostname, hvars in val.items():
                    if not isinstance(hvars, dict):
                        continue
                    ip = hvars.get("ansible_host", "")
                    if ip and ip not in ("127.0.0.1", "localhost"):
                        mapping[ip] = hostname
                    net = hvars.get("network_address", "")
                    if net:
                        mapping[net] = hostname
            elif key not in ("vars",):
                if isinstance(val, dict):
                    _walk(val)

    _walk(inv.get("all", inv))
    return mapping


def _resolve_ips_to_inventory_names(ips: List[str]) -> List[str]:
    """Convert IP addresses to Ansible inventory hostnames (#1789)."""
    ip_map = _build_ip_to_inventory_map()
    names = []
    for ip in ips:
        name = ip_map.get(ip)
        if name:
            names.append(name)
        else:
            logger.warning("No inventory hostname for IP: %s", ip)
            names.append(ip)
    return names


async def _resolve_target_nodes(
    db: AsyncSession,
    node_ids: List[str] | None,
    role: str | None,
) -> tuple:
    """Resolve target nodes for discovery. Returns (limit, extra_vars, count).

    Maps DB node IPs to Ansible inventory hostnames for --limit (#1789).
    """
    extra_vars: dict = {}
    limit = None
    if node_ids:
        result = await db.execute(select(Node).where(Node.node_id.in_(node_ids)))
        nodes = result.scalars().all()
        ips = [n.ip_address for n in nodes]
        limit = _resolve_ips_to_inventory_names(ips)
        return limit, extra_vars, len(limit)
    if role:
        extra_vars["target_hosts"] = role
    result = await db.execute(select(Node))
    all_nodes = result.scalars().all()
    return limit, extra_vars, len(all_nodes)


async def _store_host_packages(
    db: AsyncSession,
    host_data: dict,
    job: dict,
) -> int:
    """Store discovered packages for one host. Returns package count."""
    hostname = host_data.get("hostname", "")
    ip_address = host_data.get("ip_address", "")
    node_id = await _resolve_host_to_node(db, hostname, ip_address)
    if not node_id:
        logger.warning("Unknown host: %s / %s", hostname, ip_address)
        return 0

    await db.execute(
        UpdateInfo.__table__.delete().where(
            UpdateInfo.node_id == node_id,
            UpdateInfo.is_applied.is_(False),
        )
    )

    packages = host_data.get("packages", [])
    security_pkgs = host_data.get("security_packages", [])
    held = host_data.get("held", [])
    count = 0

    for pkg_json in packages:
        pkg = pkg_json
        if isinstance(pkg_json, str):
            try:
                pkg = json.loads(pkg_json)
            except json.JSONDecodeError:
                continue
        if not isinstance(pkg, dict) or pkg.get("p") in held:
            continue
        severity = _classify_severity(pkg["p"], security_pkgs, pkg.get("r", ""))
        await _upsert_update_info(db, node_id, pkg, severity)
        count += 1

    job["nodes_checked"] = job.get("nodes_checked", 0) + 1
    return count


async def _run_discover_job(
    job_id: str,
    node_ids: List[str] | None,
    role: str | None,
) -> None:
    """Background task: run check-system-updates.yml."""
    from services.database import db_service

    job = _discover_jobs.get(job_id)
    if not job:
        return

    job["status"] = "running"
    job["started_at"] = datetime.now(timezone.utc).isoformat()

    try:
        executor = get_playbook_executor()
        async with db_service.session() as db:
            limit, extra_vars, total = await _resolve_target_nodes(db, node_ids, role)
        job["total_nodes"] = total
        job["message"] = "Running apt update on fleet nodes..."
        job["progress"] = 10
        await _broadcast_job_update(job_id, "running", 10, job["message"])

        result = await executor.execute_playbook(
            playbook_name="check-system-updates.yml",
            limit=limit,
            extra_vars=(extra_vars if extra_vars else None),
        )

        job["progress"] = 70
        job["message"] = "Parsing discovered packages..."
        host_results = _parse_discover_output(result["output"])
        unreachable = _parse_unreachable_hosts(result["output"]) if not result["success"] else []

        if not result["success"] and not host_results:
            job["status"] = "failed"
            job["message"] = "Playbook failed: " + result["output"][:500]
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
            logger.error("Discover job %s failed — no nodes reported results", job_id)
            return

        total_packages = 0
        async with db_service.session() as db:
            for host_data in host_results:
                total_packages += await _store_host_packages(db, host_data, job)
            await db.commit()

        nodes_checked = job.get("nodes_checked", 0)
        total_nodes = job.get("total_nodes", 0)

        if unreachable:
            unreachable_names = ", ".join(unreachable)
            job["status"] = "completed_with_warnings"
            job["unreachable_nodes"] = unreachable
            job["message"] = (
                f"Found {total_packages} upgradable packages across "
                f"{nodes_checked}/{total_nodes} nodes "
                f"({len(unreachable)} unreachable: {unreachable_names})"
            )
            logger.warning(
                "Discover job %s partial success: %d unreachable node(s): %s",
                job_id,
                len(unreachable),
                unreachable_names,
            )
        else:
            job["status"] = "completed"
            job["message"] = f"Found {total_packages} upgradable packages " f"across {nodes_checked} nodes"

        job["progress"] = 100
        job["packages_found"] = total_packages
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        await _broadcast_job_update(job_id, job["status"], 100, job["message"])

    except Exception:
        logger.exception("Discover job failed: %s", job_id)
        job["status"] = "failed"
        job["message"] = "Discover job failed"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        await _broadcast_job_update(job_id, "failed", job.get("progress", 0), "Discover job failed")


@router.post("/discover", response_model=UpdateDiscoverResponse)
async def discover_updates(
    request: UpdateDiscoverRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateDiscoverResponse:
    """Trigger package discovery on fleet nodes."""
    job_id = str(uuid.uuid4())[:16]

    _discover_jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": 0,
        "message": "Queued for discovery...",
        "nodes_checked": 0,
        "total_nodes": 0,
        "packages_found": 0,
        "unreachable_nodes": [],
        "started_at": None,
        "completed_at": None,
    }

    asyncio.create_task(_run_discover_job(job_id, request.node_ids, request.role))

    logger.info("Discover job created: %s", job_id)
    return UpdateDiscoverResponse(
        success=True,
        message="Update discovery started",
        job_id=job_id,
    )


@router.get(
    "/discover/{job_id}",
    response_model=UpdateDiscoverStatus,
)
async def get_discover_status(
    job_id: str,
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateDiscoverStatus:
    """Poll status of an update discovery job."""
    job = _discover_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery job not found",
        )
    return UpdateDiscoverStatus(**job)


@router.get("/summary", response_model=UpdateSummaryResponse)
async def get_update_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateSummaryResponse:
    """Lightweight summary for sidebar badge polling."""
    total_result = await db.execute(select(UpdateInfo).where(UpdateInfo.is_applied.is_(False)))
    all_updates = total_result.scalars().all()

    security_count = sum(1 for u in all_updates if u.severity == "security")
    nodes_with = len({u.node_id for u in all_updates if u.node_id})

    last_checked = None
    if all_updates:
        last_checked = max(u.created_at for u in all_updates)

    return UpdateSummaryResponse(
        system_update_count=len(all_updates),
        security_update_count=security_count,
        nodes_with_updates=nodes_with,
        last_checked=last_checked,
    )


@router.get("/packages", response_model=UpdatePackagesResponse)
async def list_packages(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(500, ge=1, le=1000),
) -> UpdatePackagesResponse:
    """List discovered upgradable packages."""
    query = select(UpdateInfo).where(UpdateInfo.is_applied.is_(False))

    if node_id:
        query = query.where(UpdateInfo.node_id == node_id)
    if severity:
        query = query.where(UpdateInfo.severity == severity)

    query = query.order_by(
        UpdateInfo.severity.desc(),
        UpdateInfo.package_name,
    ).limit(limit)

    result = await db.execute(query)
    packages = result.scalars().all()

    by_node: Dict[str, int] = defaultdict(int)
    for pkg in packages:
        if pkg.node_id:
            by_node[pkg.node_id] += 1

    return UpdatePackagesResponse(
        packages=[UpdateInfoResponse.model_validate(p) for p in packages],
        total=len(packages),
        by_node=dict(by_node),
    )


@router.get("/check", response_model=UpdateCheckResponse)
async def check_updates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: str | None = Query(None),
) -> UpdateCheckResponse:
    """Check for available updates."""
    query = select(UpdateInfo).where(UpdateInfo.is_applied.is_(False))

    if node_id:
        query = query.where(or_(UpdateInfo.node_id == node_id, UpdateInfo.node_id.is_(None)))

    query = query.order_by(UpdateInfo.severity.desc(), UpdateInfo.created_at.desc())

    result = await db.execute(query)
    updates = result.scalars().all()

    return UpdateCheckResponse(
        updates=[UpdateInfoResponse.model_validate(u) for u in updates],
        total=len(updates),
    )


def _build_node_summaries(nodes: list, updates_by_node: dict, global_count: int) -> list:
    """Build per-node update summaries.

    Helper for get_fleet_update_summary (#682).
    """
    summaries = []
    for node in nodes:
        sys_count = len(updates_by_node.get(node.node_id, []))
        sys_count += global_count
        code_outdated = (node.code_status or "") == "outdated"
        total = sys_count + (1 if code_outdated else 0)
        summaries.append(
            NodeUpdateSummary(
                node_id=node.node_id,
                hostname=node.hostname,
                system_updates=sys_count,
                code_update_available=code_outdated,
                code_status=node.code_status or "unknown",
                total_updates=total,
            )
        )
    return summaries


@router.get(
    "/fleet-summary",
    response_model=FleetUpdateSummaryResponse,
)
async def get_fleet_update_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetUpdateSummaryResponse:
    """Get update summary for all fleet nodes (#682)."""
    nodes_result = await db.execute(select(Node))
    nodes = nodes_result.scalars().all()

    updates_result = await db.execute(select(UpdateInfo).where(UpdateInfo.is_applied.is_(False)))
    all_updates = updates_result.scalars().all()

    # Partition: node-specific vs global updates
    updates_by_node: dict = {}
    global_updates = []
    for upd in all_updates:
        if upd.node_id:
            updates_by_node.setdefault(upd.node_id, []).append(upd)
        else:
            global_updates.append(upd)

    summaries = _build_node_summaries(nodes, updates_by_node, len(global_updates))

    # Unique total: per-node specific + global (not per-node * global)
    total_sys = sum(len(v) for v in updates_by_node.values()) + len(global_updates)
    total_code = sum(1 for s in summaries if s.code_update_available)
    needing = sum(1 for s in summaries if s.total_updates > 0)

    return FleetUpdateSummaryResponse(
        nodes=summaries,
        total_system_updates=total_sys,
        total_code_updates=total_code,
        nodes_needing_updates=needing,
    )


async def _validate_node_and_updates(
    db: AsyncSession,
    node_id: str,
    update_ids: List[str],
) -> tuple:
    """Helper for apply_updates. Ref: #1088.

    Fetch and validate node and updates. Raises HTTPException on failure.
    Returns (node, updates).
    """
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )
    updates_result = await db.execute(select(UpdateInfo).where(UpdateInfo.update_id.in_(update_ids)))
    updates = updates_result.scalars().all()
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No valid updates found",
        )
    return node, updates


async def _create_and_dispatch_update_job(
    db: AsyncSession,
    request: UpdateApplyRequest,
    updates: list,
) -> str:
    """Helper for apply_updates. Ref: #1088.

    Create UpdateJob record, emit start event, commit, launch background task.
    Returns the new job_id.
    """
    job_id = str(uuid.uuid4())[:16]
    job = UpdateJob(
        job_id=job_id,
        node_id=request.node_id,
        status=UpdateJobStatus.PENDING.value,
        update_ids=request.update_ids,
        total_steps=len(updates),
    )
    db.add(job)
    await _create_node_event(
        db,
        request.node_id,
        EventType.DEPLOYMENT_STARTED,
        EventSeverity.INFO,
        f"Update job started: {len(updates)} package(s)",
        {"job_id": job_id, "update_ids": request.update_ids},
    )
    await db.commit()
    task = asyncio.create_task(_run_update_job(job_id, request.node_id, request.update_ids))
    _running_jobs[job_id] = task
    return job_id


@router.post("/apply", response_model=UpdateApplyResponse)
async def apply_updates(
    request: UpdateApplyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateApplyResponse:
    """
    Apply updates to a node.

    Creates an update job that runs in the background. Use the job_id
    to poll for status via GET /updates/jobs/{job_id}.
    """
    _node, updates = await _validate_node_and_updates(db, request.node_id, request.update_ids)
    job_id = await _create_and_dispatch_update_job(db, request, updates)

    logger.info(
        "Update job created: %s for node %s (%d updates)",
        job_id,
        request.node_id,
        len(updates),
    )

    return UpdateApplyResponse(
        success=True,
        message=f"Update job started for {len(updates)} package(s)",
        job_id=job_id,
    )


async def _execute_upgrade_playbook(
    sess: AsyncSession,
    j: UpdateJob,
    node_id: str,
    ip_address: str,
    job_id: str,
) -> None:
    """Execute apply-system-updates.yml and update job state."""
    executor = get_playbook_executor()
    limit = _resolve_ips_to_inventory_names([ip_address])
    r = await executor.execute_playbook(
        playbook_name="apply-system-updates.yml",
        limit=limit,
        extra_vars={
            "update_type": "all",
            "dry_run": "false",
            "auto_reboot": "false",
        },
    )
    if r["success"]:
        j.status = UpdateJobStatus.COMPLETED.value
        j.progress = 100
        j.output = r["output"]
        await sess.execute(
            UpdateInfo.__table__.update()
            .where(
                UpdateInfo.node_id == node_id,
                UpdateInfo.is_applied.is_(False),
            )
            .values(
                is_applied=True,
                applied_at=datetime.now(timezone.utc),
            )
        )
    else:
        j.status = UpdateJobStatus.FAILED.value
        j.error = r["output"][:500]
        j.output = r["output"]
    j.completed_at = datetime.now(timezone.utc)
    await sess.commit()
    await _broadcast_job_update(job_id, j.status, j.progress, j.current_step)


async def _run_upgrade_all(jid: str, nid: str) -> None:
    """Background task: run apt upgrade all on a node."""
    from services.database import db_service

    async with db_service.session() as sess:
        res = await sess.execute(select(UpdateJob).where(UpdateJob.job_id == jid))
        j = res.scalar_one_or_none()
        if not j:
            return
        n_res = await sess.execute(select(Node).where(Node.node_id == nid))
        n = n_res.scalar_one_or_none()
        if not n:
            j.status = UpdateJobStatus.FAILED.value
            j.error = "Node not found"
            j.completed_at = datetime.now(timezone.utc)
            await sess.commit()
            return

        j.status = UpdateJobStatus.RUNNING.value
        j.started_at = datetime.now(timezone.utc)
        j.current_step = "Running apt upgrade on node"
        await sess.commit()
        await _broadcast_job_update(jid, "running", 10, j.current_step)

        try:
            await _execute_upgrade_playbook(sess, j, nid, n.ip_address, jid)
        except Exception:
            logger.exception("Upgrade all failed: %s", jid)
            j.status = UpdateJobStatus.FAILED.value
            j.error = "Internal server error"
            j.completed_at = datetime.now(timezone.utc)
            await sess.commit()


@router.post("/apply-all", response_model=UpdateApplyResponse)
async def apply_all_updates(
    request: UpdateApplyAllRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateApplyResponse:
    """Apply all available updates on a node."""
    result = await db.execute(select(Node).where(Node.node_id == request.node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    job_id = str(uuid.uuid4())[:16]
    job = UpdateJob(
        job_id=job_id,
        node_id=request.node_id,
        status=UpdateJobStatus.PENDING.value,
        update_ids=[],
        total_steps=1,
    )
    db.add(job)
    await db.commit()

    task = asyncio.create_task(_run_upgrade_all(job_id, request.node_id))
    _running_jobs[job_id] = task

    return UpdateApplyResponse(
        success=True,
        message="Upgrade all started",
        job_id=job_id,
    )


@router.get("/jobs/{job_id}", response_model=UpdateJobResponse)
async def get_job_status(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateJobResponse:
    """
    Get status of an update job.

    Use this endpoint to poll for job progress and completion.
    """
    result = await db.execute(select(UpdateJob).where(UpdateJob.job_id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Update job not found",
        )

    return UpdateJobResponse.model_validate(job)


@router.get("/jobs", response_model=UpdateJobListResponse)
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
) -> UpdateJobListResponse:
    """List update jobs with optional filters."""
    query = select(UpdateJob)

    if node_id:
        query = query.where(UpdateJob.node_id == node_id)
    if status_filter:
        query = query.where(UpdateJob.status == status_filter)

    query = query.order_by(UpdateJob.created_at.desc()).limit(limit)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return UpdateJobListResponse(
        jobs=[UpdateJobResponse.model_validate(j) for j in jobs],
        total=len(jobs),
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """Cancel a running update job."""
    result = await db.execute(select(UpdateJob).where(UpdateJob.job_id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Update job not found",
        )

    if job.status not in [UpdateJobStatus.PENDING.value, UpdateJobStatus.RUNNING.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in status: {job.status}",
        )

    # Cancel the task if running
    if job_id in _running_jobs:
        _running_jobs[job_id].cancel()
        del _running_jobs[job_id]

    job.status = UpdateJobStatus.CANCELLED.value
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("Update job cancelled: %s", job_id)

    return {"success": True, "message": "Job cancelled"}
