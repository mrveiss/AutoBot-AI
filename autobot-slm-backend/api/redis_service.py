# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Redis Service API Routes

Local systemctl control for the redis-stack-server service on the SLM node.
The Ansible sudoers playbook (configure-redis-service-management.yml) grants
the `autobot` user passwordless sudo for start/stop/restart/status of this
service.

Related to Issue #11340.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger(__name__)

# Service name is a module constant — never interpolated from user input.
_REDIS_SERVICE_NAME = "redis-stack-server"

# Actions allowed through this API — validated as an allowlist.
_ALLOWED_ACTIONS = frozenset({"start", "stop", "restart"})

router = APIRouter(prefix="/redis-service", tags=["redis-service"])


async def _run_systemctl(args: list[str], timeout: float = 15.0) -> tuple[int, str, str]:
    """Run a systemctl command via asyncio subprocess (arg-list, no shell)."""
    cmd = ["/usr/bin/sudo", "/usr/bin/systemctl"] + args
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        raw_out, raw_err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"systemctl {args[0]} timed out after {timeout}s",
        )
    return proc.returncode, raw_out.decode("utf-8", errors="replace"), raw_err.decode("utf-8", errors="replace")


def _map_active_state(active_output: str) -> str:
    """Map systemctl is-active output to the vocabulary expected by the panel."""
    text = active_output.strip().lower()
    if text == "active":
        return "running"
    if text in ("inactive", "deactivating"):
        return "stopped"
    if text in ("failed", "error"):
        return "failed"
    return "unknown"


@router.get("/status")
async def get_redis_status() -> dict:
    """Return the current status of redis-stack-server."""
    returncode, stdout, _stderr = await _run_systemctl(["is-active", _REDIS_SERVICE_NAME])
    mapped = _map_active_state(stdout) if returncode == 0 else _map_active_state(stdout)

    # Fetch richer stats from redis-cli INFO if running; gracefully degrade.
    uptime_seconds = None
    memory_used_bytes = None
    memory_peak_bytes = None
    connected_clients = None

    if mapped == "running":
        uptime_seconds, memory_used_bytes, memory_peak_bytes, connected_clients = await _fetch_redis_info()

    return {
        "status": mapped,
        "uptime_seconds": uptime_seconds,
        "memory_used_bytes": memory_used_bytes,
        "memory_peak_bytes": memory_peak_bytes,
        "connected_clients": connected_clients,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }


async def _fetch_redis_info() -> tuple[int | None, int | None, int | None, int | None]:
    """Fetch uptime/memory/clients from redis-cli INFO; return Nones on any failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/bin/redis-cli",
            "INFO",
            "server",
            "memory",
            "clients",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        raw_out, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
    except Exception:
        return None, None, None, None

    if proc.returncode != 0:
        return None, None, None, None

    uptime = memory_used = memory_peak = clients = None
    for line in raw_out.decode("utf-8", errors="replace").splitlines():
        if line.startswith("uptime_in_seconds:"):
            try:
                uptime = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("used_memory:"):
            try:
                memory_used = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("used_memory_peak:"):
            try:
                memory_peak = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("connected_clients:"):
            try:
                clients = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return uptime, memory_used, memory_peak, clients


@router.post("/{action}")
async def control_redis_service(action: str) -> dict:
    """Start, stop, or restart redis-stack-server."""
    if action not in _ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action '{action}'. Allowed: {sorted(_ALLOWED_ACTIONS)}",
        )

    returncode, _stdout, stderr = await _run_systemctl([action, _REDIS_SERVICE_NAME])

    if returncode != 0:
        logger.error("systemctl %s %s failed (rc=%d): %s", action, _REDIS_SERVICE_NAME, returncode, stderr[:500])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"systemctl {action} failed: {stderr[:300]}",
        )

    logger.info("redis-stack-server %s succeeded", action)
    return {"action": action, "service": _REDIS_SERVICE_NAME, "success": True}
