# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM Service Restart

The restart execution steps, plus the session-owning seam for the part of a
restart that outlives the HTTP request which started it (#15611).

``api/services.py``'s ``restart_all_node_services`` defers the SLM services to a
FastAPI background task so the response is sent before the backend restarts
itself (#816). Background tasks run *after* the response, which is after
``Depends(get_db)`` teardown has committed and closed the request session
(``services/database.py``). A job therefore cannot borrow that session, and it
cannot borrow a row loaded through it either: the boundary carries plain
identifiers only, and ``restart_slm_services`` opens and owns its own session
here — the idiom ``_run_backup``/``_run_restore`` (``api/stateful.py``) and
``_run_deployment`` (``services/deployment.py``) already follow.

The failure this replaces was silent rather than loud. ``expire_on_commit=False``
leaves the already-loaded columns readable on the detached rows, so the Ansible
restart really ran and the WebSocket notification really fired, while every
``svc.status`` / ``active_state`` / ``sub_state`` / ``last_checked`` write landed
on a row no live session was tracking. There was no ``commit()`` anywhere in the
deferred path — the route's own commit fires before the task starts — so those
writes were simply dropped. The job commits each service's status as it is
written, rather than depending on a commit that has already happened.

Extracted from ``api/services.py`` rather than added to it: that module sits at
the line count the Python file-size ratchet grandfathered it at (#14236), and
the restart steps have to live somewhere a background job can import without
importing the router.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Tuple

from autobot_shared.env_utils import env_float_clamped
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.ssot_config import config
from models.database import Node, Service, ServiceStatus

logger = logging.getLogger(__name__)

# Seconds the deferred SLM restart waits for the HTTP response to flush before
# it starts killing the services that carried it (#816). Env-backed module
# constant rather than a literal: the right value depends on the deployment.
#
# Read through `env_float_clamped`, not a bare `float(os.getenv(...))`, for two
# reasons the registry alone does not cover: `EnvVarSpec`'s `range=` is
# documentation and enforces nothing, and a malformed value in a bare `float()`
# raises at IMPORT time, taking the whole backend down over a typo in an env
# file. The clamped reader falls back to the default with a warning instead.
# Same helper the sibling ceiling in `services/journal_fetch.py` uses.
_RESPONSE_FLUSH_DELAY_SECONDS = env_float_clamped("AUTOBOT_SLM_RESTART_FLUSH_DELAY_SECONDS", 1.0, 0.0, 60.0)

# Seconds to wait for one `systemctl restart` over SSH before giving up on it.
# Same reasoning as the flush delay: a literal here is a deployment assumption
# in disguise, since a slow node restarting a heavy unit legitimately exceeds a
# value that is generous on a fast one.
_RESTART_SSH_TIMEOUT_SECONDS = env_float_clamped("AUTOBOT_SLM_RESTART_SSH_TIMEOUT_SECONDS", 30.0, 1.0, 600.0)


def build_service_ssh_cmd(node: Node, remote_cmd: str) -> list:
    """Build SSH command list for service action. Ref: #1088."""
    ssh_user = node.ssh_user or "autobot"
    ssh_port = node.ssh_port or 22
    ssh_key = config.path.ssh_key_path  # canonical inter-node key (#12429)
    return [
        "/usr/bin/ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
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


async def run_ansible_service_action(
    node: Node,
    service_name: str,
    action: str,
) -> Tuple[bool, str]:
    """Run SSH command to control a service via systemctl. Ref: #1088."""
    remote_cmd = f"sudo -n systemctl {action} {service_name}"
    ssh_cmd = build_service_ssh_cmd(node, remote_cmd)

    try:
        process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=_RESTART_SSH_TIMEOUT_SECONDS,
        )

        if process.returncode == 0:
            logger.info("Service %s %s on %s completed", service_name, action, node.hostname)
            return True, f"Service {service_name} {action} completed"
        else:
            error = stderr.decode("utf-8", errors="replace")
            logger.error("Service action failed on %s: %s", node.hostname, error[:500])
            return False, f"Failed to {action} service: {error[:200]}"

    except asyncio.TimeoutError:
        return False, f"Timeout waiting for {action} to complete"
    except Exception as e:
        logger.exception("Service action error: %s", e)
        return False, "Service action failed"


def _mark_service_running(svc: Service) -> None:
    """Record a successful restart on *svc*.

    The caller owns the session ``svc`` is attached to and is responsible for
    committing: these writes are worthless on a row nothing is tracking (#15611).
    """
    svc.status = ServiceStatus.RUNNING.value
    svc.active_state = "active"
    svc.sub_state = "running"
    svc.last_checked = datetime.now(timezone.utc)


async def _notify_service_restart(node_id: str, service_name: str, success: bool, message: str) -> None:
    """Push the restart outcome to WebSocket subscribers.

    Imported at call time, as ``services/reconciler.py`` does: ``api.websocket``
    is an api-layer module and importing it here at module scope would make a
    service import a router package.
    """
    from api.websocket import ws_manager

    await ws_manager.send_service_status(
        node_id=node_id,
        service_name=service_name,
        status="running" if success else "unknown",
        action="restart",
        success=success,
        message=message,
    )


async def restart_single_service(
    node: Node,
    svc: Service,
    node_id: str,
    is_slm: bool,
) -> dict:
    """
    Execute restart for a single service and handle status updates.

    Updates the status columns on *svc*, sends a WebSocket notification, and
    logs the result. Returns a result dict with service_name, success, message,
    is_slm_agent. *svc* must be attached to a session the caller owns and
    commits (#15611).

    Helper for restart_all_node_services (Issue #665).
    """
    logger.info(
        "Restarting service %s on %s%s",
        svc.service_name,
        node.hostname,
        " (SLM service - last)" if is_slm else "",
    )

    success, message = await run_ansible_service_action(node, svc.service_name, "restart")

    if success:
        _mark_service_running(svc)
    else:
        logger.error("Failed to restart %s on %s: %s", svc.service_name, node.hostname, message)
    await _notify_service_restart(node_id, svc.service_name, success, message)

    return {
        "service_name": svc.service_name,
        "success": success,
        "message": message,
        "is_slm_agent": is_slm,
    }


async def restart_service_list(node: Node, services: list, node_id: str, is_slm: bool) -> tuple[list, int, int]:
    """Restart a list of services sequentially, return results.

    Helper for restart_all_node_services (#816).
    """
    results = []
    successful = 0
    failed = 0
    for svc in services:
        svc_result = await restart_single_service(node, svc, node_id, is_slm)
        results.append(svc_result)
        if svc_result["success"]:
            successful += 1
        else:
            failed += 1
    return results, successful, failed


async def _load_node(db: AsyncSession, node_id: str) -> Node | None:
    """Load the node through the job's own session."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    return result.scalar_one_or_none()


async def _load_services(db: AsyncSession, node_id: str, service_names: list) -> list:
    """Load *service_names* on *node_id* through the job's own session.

    Returned in the order the caller asked for, so the SLM restart sequence the
    route computed survives the trip across the background boundary as names.
    """
    result = await db.execute(
        select(Service).where(Service.node_id == node_id, Service.service_name.in_(service_names))
    )
    by_name = {svc.service_name: svc for svc in result.scalars().all()}
    return [by_name[name] for name in service_names if name in by_name]


async def restart_slm_services(node_id: str, service_names: list) -> None:
    """Restart the deferred SLM services on *node_id*, owning the session used.

    Takes identifiers rather than a ``Node`` and a list of ``Service`` rows
    (#15611): this runs as a FastAPI background task, after the request that
    scheduled it has been torn down. Each service's status is committed as it is
    written, so a failure part-way through keeps the restarts that did happen.

    Args:
        node_id: Node whose SLM services are being restarted
        service_names: Service names, in the order they must be restarted
    """
    await asyncio.sleep(_RESPONSE_FLUSH_DELAY_SECONDS)  # let the response flush (#816)

    from services.database import db_service

    async with db_service.session() as db:
        node = await _load_node(db, node_id)
        if node is None:
            logger.error("Deferred SLM restart: node %s is no longer registered", node_id)
            return
        services = await _load_services(db, node_id, service_names)
        if len(services) != len(service_names):
            missing = sorted(set(service_names) - {svc.service_name for svc in services})
            logger.warning("Deferred SLM restart on %s: services no longer known: %s", node_id, missing)
        for svc in services:
            await restart_single_service(node, svc, node_id, is_slm=True)
            # #15611: the route's commit already fired; this path must persist
            # its own writes, per service, so one failure cannot discard them all.
            await db.commit()
