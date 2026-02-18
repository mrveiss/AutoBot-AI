# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Monitor API

Provides endpoints for checking the health of AutoBot's supporting services.
Consumed by the frontend health status widget.

Issue #925: Re-created after removal in Issue #729.
"""

import asyncio
import logging
from typing import Any, Dict, List, Tuple

import aiohttp
from fastapi import APIRouter

from config import UnifiedConfigManager

logger = logging.getLogger(__name__)
config = UnifiedConfigManager()

router = APIRouter(tags=["Service Monitor"])

# Timeout for external health checks (seconds)
_HEALTH_TIMEOUT = aiohttp.ClientTimeout(total=3)


async def _check_http_health(url: str) -> Tuple[str, str]:
    """Perform an HTTP GET and return (status, message).

    Returns ("online", "Healthy") on 2xx, ("offline", reason) otherwise.
    Issue #925: helper for get_service_statuses / get_vm_statuses.
    """
    try:
        async with aiohttp.ClientSession(timeout=_HEALTH_TIMEOUT) as session:
            async with session.get(url, ssl=False) as resp:
                if resp.status < 300:
                    return "online", "Healthy"
                return "offline", f"HTTP {resp.status}"
    except asyncio.TimeoutError:
        return "offline", "Timeout"
    except aiohttp.ClientConnectorError:
        return "offline", "Connection refused"
    except Exception as exc:
        logger.debug("HTTP health check failed for %s: %s", url, exc)
        return "offline", str(exc)


async def _check_redis_health() -> Tuple[str, str]:
    """Check Redis connectivity using the canonical client utility.

    Issue #925: helper for get_service_statuses / get_vm_statuses.
    """
    try:
        from autobot_shared.redis_client import get_redis_client

        client = get_redis_client(async_client=False, database="main")
        client.ping()
        return "online", "Connected"
    except Exception as exc:
        logger.debug("Redis health check failed: %s", exc)
        return "offline", "Unreachable"


@router.get("/services")
async def get_service_statuses() -> Dict[str, Any]:
    """Return health status for each AutoBot supporting service.

    Used by the frontend system-status widget (Issue #925).
    No authentication required — checked before and after login.
    """
    npu_url = config.get_service_url("npu_worker", "health")
    browser_url = config.get_service_url("browser", "health")
    ollama_url = f"{config.get_ollama_url()}/api/version"

    (
        (redis_status, redis_msg),
        (npu_status, npu_msg),
        (ollama_status, ollama_msg),
        (
            browser_status,
            browser_msg,
        ),
    ) = await asyncio.gather(
        _check_redis_health(),
        _check_http_health(npu_url),
        _check_http_health(ollama_url),
        _check_http_health(browser_url),
    )

    return {
        "services": {
            "backend": {"status": "online", "health": "Running"},
            "redis": {"status": redis_status, "health": redis_msg},
            "npu_worker": {"status": npu_status, "health": npu_msg},
            "ollama": {"status": ollama_status, "health": ollama_msg},
            "browser": {"status": browser_status, "health": browser_msg},
        }
    }


@router.get("/vms/status")
async def get_vm_statuses() -> Dict[str, Any]:
    """Return status for AutoBot VMs as a list.

    Used by the frontend system-status widget (Issue #925).
    No authentication required.
    """
    npu_url = config.get_service_url("npu_worker", "health")
    browser_url = config.get_service_url("browser", "health")

    (
        (redis_status, redis_msg),
        (npu_status, npu_msg),
        (
            browser_status,
            browser_msg,
        ),
    ) = await asyncio.gather(
        _check_redis_health(),
        _check_http_health(npu_url),
        _check_http_health(browser_url),
    )

    vms: List[Dict[str, str]] = [
        {"name": "Backend API", "status": "online", "message": "Running"},
        {"name": "Redis", "status": redis_status, "message": redis_msg},
        {"name": "NPU Worker", "status": npu_status, "message": npu_msg},
        {"name": "Browser Service", "status": browser_status, "message": browser_msg},
    ]
    return {"vms": vms}
