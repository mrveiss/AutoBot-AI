# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
from typing import Any, Dict, List, Tuple

import aiohttp
from fastapi import APIRouter

from api.schemas_system import (
    ServiceMonitorServicesResponse,
    ServiceMonitorVMsResponse,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as _ssot

logger = get_logger(__name__)

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


@router.get("/services", response_model=ServiceMonitorServicesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_service_statuses",
    error_code_prefix="SERVICE_MONITOR",
)
async def get_service_statuses() -> Dict[str, Any]:
    """Return health status for each AutoBot supporting service.

    Used by the frontend system-status widget (Issue #925).
    No authentication required — checked before and after login.
    """
    npu_url = f"http://{_ssot.vm.npu}:{_ssot.port.npu}/health"
    browser_url = f"http://{_ssot.vm.browser}:{_ssot.port.browser}/health"
    ollama_url = f"http://{_ssot.vm.ollama}:{_ssot.port.ollama}/api/version"
    chromadb_url = f"http://{_ssot.vm.aistack}:{_ssot.port.aistack}/health"  # Issue #3461: ChromaDB

    (
        (redis_status, redis_msg),
        (npu_status, npu_msg),
        (ollama_status, ollama_msg),
        (
            browser_status,
            browser_msg,
        ),
        (
            chromadb_status,
            chromadb_msg,
        ),
    ) = await asyncio.gather(
        _check_redis_health(),
        _check_http_health(npu_url),
        _check_http_health(ollama_url),
        _check_http_health(browser_url),
        _check_http_health(chromadb_url),
    )

    return {
        "services": {
            "backend": {"status": "online", "health": "Running"},
            "redis": {"status": redis_status, "health": redis_msg},
            "npu_worker": {"status": npu_status, "health": npu_msg},
            "ollama": {"status": ollama_status, "health": ollama_msg},
            "browser": {"status": browser_status, "health": browser_msg},
            "chromadb": {"status": chromadb_status, "health": chromadb_msg},  # Issue #3461
        }
    }


@router.get("/vms/status", response_model=ServiceMonitorVMsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vm_statuses",
    error_code_prefix="SERVICE_MONITOR",
)
async def get_vm_statuses() -> Dict[str, Any]:
    """Return status for AutoBot VMs as a list.

    Used by the frontend system-status widget (Issue #925).
    No authentication required.
    """
    npu_url = f"http://{_ssot.vm.npu}:{_ssot.port.npu}/health"
    browser_url = f"http://{_ssot.vm.browser}:{_ssot.port.browser}/health"
    chromadb_url = f"http://{_ssot.vm.aistack}:{_ssot.port.aistack}/health"  # Issue #3461: ChromaDB

    (
        (redis_status, redis_msg),
        (npu_status, npu_msg),
        (
            browser_status,
            browser_msg,
        ),
        (
            chromadb_status,
            chromadb_msg,
        ),
    ) = await asyncio.gather(
        _check_redis_health(),
        _check_http_health(npu_url),
        _check_http_health(browser_url),
        _check_http_health(chromadb_url),
    )

    vms: List[Dict[str, str]] = [
        {"name": "Backend API", "status": "online", "message": "Running"},
        {"name": "Redis", "status": redis_status, "message": redis_msg},
        {"name": "NPU Worker", "status": npu_status, "message": npu_msg},
        {"name": "Browser Service", "status": browser_status, "message": browser_msg},
        {"name": "AI Stack (ChromaDB)", "status": chromadb_status, "message": chromadb_msg},  # Issue #3461
    ]
    return {"vms": vms}
