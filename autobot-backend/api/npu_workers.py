# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Worker Registry API

RESTful API endpoints for managing NPU workers, load balancing, and monitoring.

Issue #641: Workers no longer self-register. Main host controls all registration.
- Workers are added via POST /api/npu/workers/pair (contacts worker, assigns ID)
- Heartbeats from unpaired workers are rejected
- Bootstrap endpoint deprecated in favor of pair endpoint

Endpoints:
- GET    /api/npu/workers - List all workers
- POST   /api/npu/workers - Register new worker (manual)
- POST   /api/npu/workers/pair - Pair with worker at URL (Issue #641 - preferred method)
- GET    /api/npu/workers/{id} - Get worker details
- PUT    /api/npu/workers/{id} - Update worker
- DELETE /api/npu/workers/{id} - Remove worker
- POST   /api/npu/workers/{id}/test - Test worker connection
- GET    /api/npu/workers/{id}/metrics - Get worker metrics
- POST   /api/npu/workers/{id}/unpair - Unpair worker from master (Issue #640)
- POST   /api/npu/workers/{id}/repair - Re-pair worker with master (Issue #640)
- GET    /api/npu/load-balancing - Get load balancing config
- PUT    /api/npu/load-balancing - Update load balancing config
- GET    /api/npu/status - Get NPU worker pool status
- POST   /api/npu/workers/heartbeat - Receive worker heartbeat (paired workers only)
- POST   /api/npu/workers/bootstrap - Bootstrap configuration (deprecated)
- GET    /api/npu/pool/stats - Get pool-level statistics (Issue #168)
- GET    /api/npu/pool/workers - Get per-worker health states (Issue #168)
- POST   /api/npu/pool/reload - Hot-reload pool configuration (Issue #168)
"""

import logging
from typing import List, Optional

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.models.npu_models import (
    LoadBalancingConfig,
    NPUWorkerConfig,
    NPUWorkerDetails,
    NPUWorkerMetrics,
    WorkerHeartbeat,
    WorkerTestResult,
)
from backend.services.npu_worker_manager import get_worker_manager

logger = logging.getLogger(__name__)

# Create router with /api/npu prefix
router = APIRouter()


# ==============================================
# WORKER MANAGEMENT ENDPOINTS
# ==============================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_workers",
    error_code_prefix="NPU_WORKERS",
)
@router.get("/npu/workers", response_model=List[NPUWorkerDetails])
async def list_workers(admin_check: bool = Depends(check_admin_permission)):
    """
    List all registered NPU workers with their current status.

    Issue #744: Requires admin authentication.

    Returns:
        List of worker details including configuration and runtime status
    """
    try:
        manager = await get_worker_manager()
        workers = await manager.list_workers()
        return workers

    except Exception as e:
        logger.error("Failed to list workers: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve workers: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_worker",
    error_code_prefix="NPU_WORKERS",
)
@router.post(
    "/npu/workers", response_model=NPUWorkerDetails, status_code=status.HTTP_201_CREATED
)
async def add_worker(
    admin_check: bool = Depends(check_admin_permission),
    worker_config: NPUWorkerConfig = None,
):
    """
    Register a new NPU worker.

    Issue #744: Requires admin authentication.

    The worker will be validated by testing connectivity before registration.

    Args:
        worker_config: Worker configuration

    Returns:
        Created worker details with initial status

    Raises:
        400: If worker ID already exists or connection test fails
        500: If registration fails
    """
    try:
        manager = await get_worker_manager()
        worker_details = await manager.add_worker(worker_config)

        logger.info("Successfully registered worker: %s", worker_config.id)
        return worker_details

    except ValueError as e:
        logger.warning("Worker registration failed: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Failed to add worker: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register worker: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_worker",
    error_code_prefix="NPU_WORKERS",
)
@router.get("/npu/workers/{worker_id}", response_model=NPUWorkerDetails)
async def get_worker(
    admin_check: bool = Depends(check_admin_permission),
    worker_id: str = None,
):
    """
    Get detailed information about a specific worker.

    Issue #744: Requires admin authentication.

    Args:
        worker_id: Worker identifier

    Returns:
        Worker details including config, status, and metrics

    Raises:
        404: If worker not found
        500: If retrieval fails
    """
    try:
        manager = await get_worker_manager()
        worker = await manager.get_worker(worker_id)

        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worker '{worker_id}' not found",
            )

        return worker

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get worker %s: %s", worker_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve worker: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_worker",
    error_code_prefix="NPU_WORKERS",
)
@router.put("/npu/workers/{worker_id}", response_model=NPUWorkerDetails)
async def update_worker(
    admin_check: bool = Depends(check_admin_permission),
    worker_id: str = None,
    worker_config: NPUWorkerConfig = None,
):
    """
    Update existing worker configuration.

    Issue #744: Requires admin authentication.

    The updated configuration will be validated by testing connectivity.

    Args:
        worker_id: Worker identifier
        worker_config: Updated worker configuration

    Returns:
        Updated worker details

    Raises:
        400: If worker ID mismatch or connection test fails
        404: If worker not found
        500: If update fails
    """
    try:
        # Validate worker_id matches config
        if worker_config.id != worker_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Worker ID in path must match ID in configuration",
            )

        manager = await get_worker_manager()
        worker_details = await manager.update_worker(worker_id, worker_config)

        logger.info("Successfully updated worker: %s", worker_id)
        return worker_details

    except ValueError as e:
        logger.warning("Worker update failed: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update worker %s: %s", worker_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update worker: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="remove_worker",
    error_code_prefix="NPU_WORKERS",
)
@router.delete("/npu/workers/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_worker(
    admin_check: bool = Depends(check_admin_permission),
    worker_id: str = None,
):
    """
    Remove worker from registry.

    Issue #744: Requires admin authentication.

    Args:
        worker_id: Worker identifier

    Raises:
        404: If worker not found
        500: If removal fails
    """
    try:
        manager = await get_worker_manager()
        await manager.remove_worker(worker_id)

        logger.info("Successfully removed worker: %s", worker_id)
        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)

    except ValueError as e:
        logger.warning("Worker removal failed: %s", e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Failed to remove worker %s: %s", worker_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove worker: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_worker",
    error_code_prefix="NPU_WORKERS",
)
@router.post("/npu/workers/{worker_id}/test", response_model=WorkerTestResult)
async def test_worker(
    admin_check: bool = Depends(check_admin_permission),
    worker_id: str = None,
):
    """
    Test connection to a specific worker.

    Issue #744: Requires admin authentication.

    Args:
        worker_id: Worker identifier

    Returns:
        Test result with connection details and response time

    Raises:
        404: If worker not found
        500: If test fails
    """
    try:
        manager = await get_worker_manager()
        worker = await manager.get_worker(worker_id)

        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worker '{worker_id}' not found",
            )

        # Test connection using worker config
        test_result = await manager.test_worker_connection(worker.config)

        logger.info(
            f"Worker {worker_id} test: {'SUCCESS' if test_result.success else 'FAILED'}"
        )
        return test_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to test worker %s: %s", worker_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test worker: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_worker_metrics",
    error_code_prefix="NPU_WORKERS",
)
@router.get(
    "/npu/workers/{worker_id}/metrics", response_model=Optional[NPUWorkerMetrics]
)
async def get_worker_metrics(
    admin_check: bool = Depends(check_admin_permission),
    worker_id: str = None,
):
    """
    Get performance metrics for a specific worker.

    Issue #744: Requires admin authentication.

    Args:
        worker_id: Worker identifier

    Returns:
        Worker performance metrics or None if not available

    Raises:
        404: If worker not found
        500: If retrieval fails
    """
    try:
        manager = await get_worker_manager()
        worker = await manager.get_worker(worker_id)

        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worker '{worker_id}' not found",
            )

        metrics = await manager.get_worker_metrics(worker_id)
        return metrics

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get metrics for worker %s: %s", worker_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metrics: {str(e)}",
        )


# ==============================================
# WORKER LOGGING CONFIGURATION ENDPOINTS
# ==============================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_worker_log_level",
    error_code_prefix="NPU_WORKERS",
)
@router.get("/npu/workers/{worker_id}/logging")
async def get_worker_log_level(
    admin_check: bool = Depends(check_admin_permission),
    worker_id: str = None,
):
    """
    Get the current log level of a worker.

    Issue #744: Requires admin authentication.

    Args:
        worker_id: Worker identifier

    Returns:
        Current log level configuration

    Raises:
        404: If worker not found
        500: If request fails
    """
    import httpx

    try:
        manager = await get_worker_manager()
        worker = await manager.get_worker(worker_id)

        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worker '{worker_id}' not found",
            )

        worker_url = f"http://{worker.config.ip_address}:{worker.config.port}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{worker_url}/config/logging")
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Worker returned error: {response.status_code}",
                )
            return response.json()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get log level for worker %s: %s", worker_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get log level: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="set_worker_log_level",
    error_code_prefix="NPU_WORKERS",
)
@router.put("/npu/workers/{worker_id}/logging")
async def set_worker_log_level(
    admin_check: bool = Depends(check_admin_permission),
    worker_id: str = None,
    level: str = "INFO",
):
    """
    Set the log level of a worker at runtime.

    Issue #744: Requires admin authentication.

    Args:
        worker_id: Worker identifier
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Updated log level configuration

    Raises:
        400: If invalid log level
        404: If worker not found
        500: If request fails
    """
    import httpx

    level = level.upper()
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    if level not in valid_levels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid log level '{level}'. Must be one of: {valid_levels}",
        )

    try:
        manager = await get_worker_manager()
        worker = await manager.get_worker(worker_id)

        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worker '{worker_id}' not found",
            )

        worker_url = f"http://{worker.config.ip_address}:{worker.config.port}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.put(
                f"{worker_url}/config/logging", params={"level": level}
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Worker returned error: {response.status_code}",
                )

            logger.info("Set log level to %s for worker %s", level, worker_id)
            return response.json()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to set log level for worker %s: %s", worker_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set log level: {str(e)}",
        )


# ==============================================
# LOAD BALANCING CONFIGURATION ENDPOINTS
# ==============================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_load_balancing_config",
    error_code_prefix="NPU_WORKERS",
)
@router.get("/npu/load-balancing", response_model=LoadBalancingConfig)
async def get_load_balancing_config(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get current load balancing configuration.

    Issue #744: Requires admin authentication.

    Returns:
        Load balancing configuration including strategy and health check settings
    """
    try:
        manager = await get_worker_manager()
        config = manager.get_load_balancing_config()
        return config

    except Exception as e:
        logger.error("Failed to get load balancing config: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve load balancing configuration: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_load_balancing_config",
    error_code_prefix="NPU_WORKERS",
)
@router.put("/npu/load-balancing", response_model=LoadBalancingConfig)
async def update_load_balancing_config(
    admin_check: bool = Depends(check_admin_permission),
    config: LoadBalancingConfig = None,
):
    """
    Update load balancing configuration.

    Issue #744: Requires admin authentication.

    Args:
        config: New load balancing configuration

    Returns:
        Updated load balancing configuration

    Raises:
        400: If configuration is invalid
        500: If update fails
    """
    try:
        manager = await get_worker_manager()
        await manager.update_load_balancing_config(config)

        logger.info("Updated load balancing config: strategy=%s", config.strategy)
        return config

    except ValueError as e:
        logger.warning("Load balancing config update failed: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Failed to update load balancing config: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update load balancing configuration: {str(e)}",
        )


# ==============================================
# HEALTH AND STATUS ENDPOINTS
# ==============================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_npu_status",
    error_code_prefix="NPU_WORKERS",
)
@router.get("/npu/status")
async def get_npu_status(admin_check: bool = Depends(check_admin_permission)):
    """
    Get overall NPU worker pool status.

    Issue #744: Requires admin authentication.

    Returns:
        Summary of worker pool health and availability
    """
    try:
        manager = await get_worker_manager()
        workers = await manager.list_workers()

        # Aggregate statistics
        total_workers = len(workers)
        online_workers = sum(1 for w in workers if w.status.status == "online")
        total_capacity = sum(
            w.config.max_concurrent_tasks for w in workers if w.config.enabled
        )
        current_load = sum(w.status.current_load for w in workers)

        return {
            "status": "healthy" if online_workers > 0 else "degraded",
            "total_workers": total_workers,
            "online_workers": online_workers,
            "offline_workers": total_workers - online_workers,
            "total_capacity": total_capacity,
            "current_load": current_load,
            "utilization_percent": round(
                (current_load / total_capacity * 100) if total_capacity > 0 else 0, 2
            ),
            "load_balancing_strategy": manager.get_load_balancing_config().strategy,
        }

    except Exception as e:
        logger.error("Failed to get NPU status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve NPU status: {str(e)}",
        )


# ==============================================
# NPU HEALTH PROXY (Issue #1007)
# ==============================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="proxy_npu_health",
    error_code_prefix="NPU_WORKERS",
)
@router.get("/npu/health")
async def proxy_npu_health():
    """
    Proxy NPU worker health check to avoid CORS/mixed content.

    Issue #1007: Frontend must not fetch NPU directly from browser.
    """
    from autobot_shared.ssot_config import config as ssot_config

    npu_host = ssot_config.get_host("npu_worker", "172.16.168.22")
    npu_port = ssot_config.get_port("npu_worker", 8081)
    url = f"http://{npu_host}:{npu_port}/health"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            return JSONResponse(
                status_code=resp.status_code,
                content=resp.json(),
            )
    except httpx.ConnectError:
        return JSONResponse(
            status_code=503,
            content={"status": "offline", "detail": "NPU worker unreachable"},
        )
    except Exception as e:
        logger.error("NPU health proxy failed: %s", e)
        return JSONResponse(
            status_code=502,
            content={"status": "error", "detail": str(e)},
        )


# ==============================================
# WORKER RE-PAIRING ENDPOINTS (Issue #640)
# ==============================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unpair_worker",
    error_code_prefix="NPU_WORKERS",
)
@router.post("/npu/workers/{worker_id}/unpair")
async def unpair_worker(
    admin_check: bool = Depends(check_admin_permission),
    worker_id: str = None,
):
    """
    Unpair a worker from the master (Issue #640).

    Issue #744: Requires admin authentication.

    This clears the worker's registration, allowing it to re-pair
    when it next starts or receives a bootstrap request.

    Args:
        worker_id: Worker identifier to unpair

    Returns:
        Confirmation of unpair action

    Raises:
        404: If worker not found
        500: If unpair fails
    """
    try:
        manager = await get_worker_manager()
        worker = await manager.get_worker(worker_id)

        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worker '{worker_id}' not found",
            )

        # Remove worker from registry
        await manager.remove_worker(worker_id)

        logger.info("Successfully unpaired worker: %s", worker_id)
        return {
            "success": True,
            "worker_id": worker_id,
            "message": "Worker unpaired successfully. It will re-register on next startup.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to unpair worker %s: %s", worker_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unpair worker: {str(e)}",
        )


def _generate_repair_bootstrap_config() -> dict:
    """
    Generate fresh bootstrap configuration for worker re-pairing.

    Issue #665: Extracted from repair_worker() for single responsibility.

    Returns:
        Dict with redis, backend, models, and logging configuration.
    """
    from autobot_shared.ssot_config import config as ssot_config

    return {
        "redis": {
            "host": ssot_config.redis.host,
            "port": ssot_config.redis.port,
            "password": ssot_config.redis.password,
            "db": 0,
            "socket_timeout": 5,
            "max_connections": 10,
        },
        "backend": {
            "host": ssot_config.backend.host,
            "port": ssot_config.backend.port,
            "register_with_backend": True,
            "health_check_interval": 30,
        },
        "models": {
            "autoload_defaults": True,
            "default_embedding": "nomic-embed-text",
            "default_llm": "llama3.2:1b-instruct-q4_K_M",
        },
        "logging": {"level": "INFO", "format": "structured"},
    }


async def _handle_existing_worker_removal(
    manager, worker, worker_id: str, force: bool
) -> tuple[str, str]:
    """
    Handle removal of existing worker registration.

    Issue #665: Extracted from repair_worker() for single responsibility.

    Returns:
        Tuple of (worker_url, platform)

    Raises:
        HTTPException: If worker is active and force is not set
    """
    worker_url = worker.config.url
    platform = worker.config.platform

    if worker.status.status == "online" and not force:
        logger.warning(
            "Attempted to re-pair active worker %s without force flag", worker_id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Worker is currently active. Use force=true to re-pair anyway.",
        )

    await manager.remove_worker(worker_id)
    logger.info("Removed existing registration for worker: %s", worker_id)

    return worker_url, platform


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="repair_worker",
    error_code_prefix="NPU_WORKERS",
)
@router.post("/npu/workers/{worker_id}/repair")
async def repair_worker(
    admin_check: bool = Depends(check_admin_permission),
    worker_id: str = None,
    request: dict = None,
):
    """
    Re-pair a worker with the master (Issue #640).

    Issue #744: Requires admin authentication.

    This initiates a re-pairing sequence:
    1. Removes existing worker registration (if any)
    2. Optionally sends command to worker to clear its local pairing
    3. Returns new bootstrap configuration for immediate re-registration

    Issue #665: Refactored to extract helper methods.

    Args:
        worker_id: Worker identifier
        request: Optional dict with:
            - url: Worker URL (if different from registered)
            - force: Force re-pair even if worker is active

    Returns:
        New bootstrap configuration for the worker

    Raises:
        400: If re-pair is not possible
        500: If re-pair fails
    """
    import uuid
    from datetime import datetime

    try:
        manager = await get_worker_manager()
        worker = await manager.get_worker(worker_id)

        request = request or {}
        force = request.get("force", False)

        if worker:
            worker_url, platform = await _handle_existing_worker_removal(
                manager, worker, worker_id, force
            )
            worker_url = request.get("url", "") or worker_url
        else:
            worker_url = request.get("url", "")
            platform = request.get("platform", "unknown")

        new_worker_id = f"{platform}_npu_worker_{uuid.uuid4().hex[:8]}"

        logger.info(
            "Re-pair initiated for worker %s -> new ID: %s", worker_id, new_worker_id
        )

        return {
            "success": True,
            "old_worker_id": worker_id,
            "new_worker_id": new_worker_id,
            "config": _generate_repair_bootstrap_config(),
            "server_timestamp": datetime.utcnow().isoformat() + "Z",
            "message": "Worker unpaired. Use provided config for re-registration.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to re-pair worker %s: %s", worker_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to re-pair worker: {str(e)}",
        )


# ==============================================
# WORKER PAIRING ENDPOINT (Issue #641)
# ==============================================

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple

import httpx


@dataclass
class WorkerHealthInfo:
    """Health information from a worker."""

    platform: str
    existing_worker_id: Optional[str]
    already_paired: bool


async def _check_worker_health(
    client: httpx.AsyncClient, worker_url: str
) -> WorkerHealthInfo:
    """
    Check if worker is reachable and get health information.

    Args:
        client: HTTP client for requests
        worker_url: Base URL of the worker

    Returns:
        WorkerHealthInfo with platform and pairing status

    Raises:
        HTTPException: If worker is unreachable or health check fails
    """
    try:
        health_response = await client.get(f"{worker_url}/health")
        if health_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Worker health check failed: {health_response.status_code}",
            )
        health_data = health_response.json()

        info = WorkerHealthInfo(
            platform=health_data.get("platform", "unknown"),
            existing_worker_id=health_data.get("worker_id"),
            already_paired=health_data.get("paired", False),
        )

        logger.info(
            "Worker reachable: platform=%s, existing_id=%s, paired=%s",
            info.platform,
            info.existing_worker_id,
            info.already_paired,
        )
        return info

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reach worker at {worker_url}: {str(e)}",
        )


def _generate_worker_id(health_info: WorkerHealthInfo) -> str:
    """Generate or reuse worker ID based on health information."""
    if health_info.existing_worker_id and health_info.already_paired:
        logger.info("Reusing existing worker ID: %s", health_info.existing_worker_id)
        return health_info.existing_worker_id

    worker_id = f"{health_info.platform}_npu_worker_{uuid.uuid4().hex[:8]}"
    logger.info("Generated new worker ID: %s", worker_id)
    return worker_id


def _build_pairing_config() -> Tuple[Dict, str]:
    """
    Build configuration to send to worker during pairing.

    Returns:
        Tuple of (worker_config dict, main_host string)
    """
    from autobot_shared.ssot_config import config as ssot_config

    worker_config = {
        "redis": {
            "host": ssot_config.redis.host,
            "port": ssot_config.redis.port,
            "password": ssot_config.redis.password,
            "db": 0,
        },
        "backend": {
            "host": ssot_config.backend.host,
            "port": ssot_config.backend.port,
        },
    }
    main_host = f"{ssot_config.backend.host}:{ssot_config.backend.port}"
    return worker_config, main_host


async def _send_pairing_request(
    client: httpx.AsyncClient,
    worker_url: str,
    worker_id: str,
    worker_config: Dict,
    main_host: str,
) -> Dict:
    """
    Send pairing request to worker and return device info.

    Args:
        client: HTTP client for requests
        worker_url: Base URL of the worker
        worker_id: Assigned worker ID
        worker_config: Configuration for the worker
        main_host: Main host address

    Returns:
        Device info dict from worker response

    Raises:
        HTTPException: If pairing request fails
    """
    pair_request = {
        "worker_id": worker_id,
        "main_host": main_host,
        "config": worker_config,
    }

    try:
        pair_response = await client.post(f"{worker_url}/pair", json=pair_request)
        if pair_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Worker rejected pairing: {pair_response.text}",
            )
        pair_result = pair_response.json()
        return pair_result.get("device_info", {})

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to send pair request to worker: {str(e)}",
        )


async def _register_worker_in_backend(
    worker_id: str,
    worker_url: str,
    platform: str,
    worker_name: str,
    enabled: bool,
) -> None:
    """
    Register or update worker in backend database.

    Args:
        worker_id: Worker's unique ID
        worker_url: Worker's URL
        platform: Worker's platform (windows/linux)
        worker_name: Friendly name for worker
        enabled: Whether worker is enabled
    """
    manager = await get_worker_manager()

    existing = await manager.get_worker(worker_id)
    if existing:
        logger.info("Updating existing worker registration: %s", worker_id)
        heartbeat = WorkerHeartbeat(
            worker_id=worker_id,
            platform=platform,
            url=worker_url,
            status="online",
            current_load=0,
            models_loaded=[],
            uptime_seconds=0,
        )
        await manager.update_worker_status_from_heartbeat(heartbeat)
    else:
        new_config = NPUWorkerConfig(
            id=worker_id,
            name=worker_name or f"NPU Worker ({platform})",
            url=worker_url,
            platform=platform,
            enabled=enabled,
            priority=5,
            weight=1,
            max_concurrent_tasks=4,
        )
        await manager.add_worker(new_config)
        logger.info("Registered new worker: %s", worker_id)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="pair_worker",
    error_code_prefix="NPU_WORKERS",
)
@router.post("/npu/workers/pair")
async def pair_worker(
    admin_check: bool = Depends(check_admin_permission),
    request: dict = None,
):
    """
    Issue #641: Pair with an NPU worker at the given IP:port.

    Issue #744: Requires admin authentication.

    This is the AUTHORITATIVE way to register workers. The main host:
    1. Contacts the worker at the given URL
    2. Generates a permanent worker ID
    3. Sends the ID to the worker via POST /pair
    4. Registers the worker in the backend

    Workers do NOT self-register. All registration goes through this endpoint.

    Args:
        request: Pairing request containing:
            - url: Worker URL (e.g., "http://192.168.1.100:8082")
            - name: Optional friendly name for the worker
            - enabled: Whether worker is enabled (default: True)

    Returns:
        Pairing result with worker details

    Raises:
        400: If worker is unreachable or pairing fails
        500: If registration fails
    """
    try:
        worker_url = request.get("url", "").rstrip("/")
        worker_name = request.get("name", "")
        enabled = request.get("enabled", True)

        if not worker_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Worker URL is required",
            )

        logger.info("Attempting to pair with worker at %s", worker_url)

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Step 1: Check worker health
            health_info = await _check_worker_health(client, worker_url)

            # Step 2: Generate or reuse worker ID
            worker_id = _generate_worker_id(health_info)

            # Step 3: Build pairing configuration
            worker_config, main_host = _build_pairing_config()

            # Step 4: Send pairing request to worker
            device_info = await _send_pairing_request(
                client, worker_url, worker_id, worker_config, main_host
            )

        # Step 5: Register worker in backend
        await _register_worker_in_backend(
            worker_id, worker_url, health_info.platform, worker_name, enabled
        )

        return {
            "success": True,
            "worker_id": worker_id,
            "url": worker_url,
            "platform": health_info.platform,
            "device_info": device_info,
            "paired_at": datetime.utcnow().isoformat() + "Z",
            "message": f"Successfully paired with worker at {worker_url}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to pair with worker: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pair with worker: {str(e)}",
        )


# ==============================================
# WORKER HEARTBEAT/TELEMETRY ENDPOINTS
# ==============================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="worker_heartbeat",
    error_code_prefix="NPU_WORKERS",
)
def _update_prometheus_heartbeat_metrics(heartbeat: WorkerHeartbeat) -> None:
    """Update Prometheus metrics for worker heartbeat. Issue #620."""
    import time

    try:
        from monitoring.prometheus_metrics import get_metrics_manager

        metrics = get_metrics_manager()
        if metrics and hasattr(metrics, "performance"):
            perf = metrics.performance
            perf.update_npu_worker_status(
                heartbeat.worker_id,
                heartbeat.platform,
                heartbeat.status == "online",
            )
            perf.update_npu_worker_metrics(
                heartbeat.worker_id,
                heartbeat.current_load,
                heartbeat.uptime_seconds,
            )
            perf.update_npu_worker_heartbeat(heartbeat.worker_id, time.time())
    except Exception as metrics_error:
        logger.warning("Failed to update Prometheus metrics: %s", metrics_error)


@router.post("/npu/workers/heartbeat")
async def worker_heartbeat(heartbeat: WorkerHeartbeat):
    """
    Receive heartbeat/telemetry from NPU worker.

    Issue #641: Workers no longer self-register via heartbeat.
    Workers must be explicitly paired via /npu/workers/pair endpoint.
    Heartbeats from unpaired workers are rejected.

    Issue #620: Refactored to extract _update_prometheus_heartbeat_metrics.

    Args:
        heartbeat: Heartbeat data from worker

    Returns:
        Acknowledgement with server timestamp

    Raises:
        400: If worker is not paired (Issue #641)
    """
    from datetime import datetime

    try:
        manager = await get_worker_manager()

        # Check if worker exists
        worker = await manager.get_worker(heartbeat.worker_id)

        if not worker:
            # Issue #641: Do NOT auto-register workers from heartbeat
            # Workers must be explicitly paired via GUI/API
            logger.warning(
                "Heartbeat from unpaired worker %s at %s - ignoring. "
                "Worker must be paired via /npu/workers/pair endpoint.",
                heartbeat.worker_id,
                heartbeat.url,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Worker '{heartbeat.worker_id}' is not paired. "
                f"Add worker via GUI or POST /api/npu/workers/pair",
            )

        # Update worker status from heartbeat
        await manager.update_worker_status_from_heartbeat(heartbeat)

        # Update Prometheus metrics (Issue #620: uses helper)
        _update_prometheus_heartbeat_metrics(heartbeat)

        logger.debug(
            "Received heartbeat from worker %s: status=%s",
            heartbeat.worker_id,
            heartbeat.status,
        )

        return {
            "acknowledged": True,
            "worker_id": heartbeat.worker_id,
            "server_timestamp": datetime.utcnow().isoformat() + "Z",
            "message": "Heartbeat received",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to process heartbeat from %s: %s", heartbeat.worker_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process heartbeat: {str(e)}",
        )


def _build_worker_redis_config(ssot_config) -> dict:
    """
    Build Redis configuration for NPU worker bootstrap.

    Issue #665: Extracted from worker_bootstrap to reduce function length.

    Args:
        ssot_config: SSOT configuration object

    Returns:
        Redis configuration dict for workers
    """
    return {
        "host": ssot_config.redis.host,
        "port": ssot_config.redis.port,
        "password": ssot_config.redis.password,
        "db": 0,  # Default db for workers
        "socket_timeout": 5,
        "max_connections": 10,
    }


def _build_worker_backend_config(ssot_config) -> dict:
    """
    Build backend configuration for NPU worker bootstrap.

    Issue #665: Extracted from worker_bootstrap to reduce function length.

    Args:
        ssot_config: SSOT configuration object

    Returns:
        Backend configuration dict for workers
    """
    return {
        "host": ssot_config.backend.host,
        "port": ssot_config.backend.port,
        "register_with_backend": True,
        "health_check_interval": 30,
    }


def _build_worker_models_config() -> dict:
    """
    Build model configuration for NPU worker bootstrap.

    Issue #665: Extracted from worker_bootstrap to reduce function length.

    Returns:
        Model configuration dict for workers
    """
    return {
        "autoload_defaults": True,
        "default_embedding": "nomic-embed-text",
        "default_llm": "llama3.2:1b-instruct-q4_K_M",
    }


def _build_worker_logging_config() -> dict:
    """
    Build logging configuration for NPU worker bootstrap.

    Issue #665: Extracted from worker_bootstrap to reduce function length.

    Returns:
        Logging configuration dict for workers
    """
    return {
        "level": "INFO",
        "format": "structured",
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="worker_bootstrap",
    error_code_prefix="NPU_WORKERS",
)
@router.post("/npu/workers/bootstrap")
async def worker_bootstrap(request: dict):
    """
    Bootstrap configuration endpoint for NPU workers.

    Workers call this on startup to receive their configuration from the
    main backend. This eliminates the need to hardcode credentials in workers.

    Issue #640: If worker provides an existing worker_id, reuse it instead of
    generating a new one. This prevents duplicate registrations on restart.

    Issue #665: Refactored to use extracted helpers for config building.

    Args:
        request: Bootstrap request containing:
            - worker_id: Worker identifier (or "auto" for auto-generated)
            - platform: Worker platform (windows, linux, macos)
            - url: Worker's accessible URL
            - capabilities: Optional list of worker capabilities

    Returns:
        Configuration for the worker including:
            - redis: Redis connection details (host, port, password, db)
            - backend: Backend connection details
            - models: Model configuration
            - logging: Logging configuration
            - worker_id: Assigned worker ID (reused if provided, generated if "auto")
    """
    from datetime import datetime

    try:
        worker_id = request.get("worker_id", "auto")
        platform = request.get("platform", "unknown")
        worker_url = request.get("url", "")

        # Issue #640: Only generate new ID if "auto" - reuse existing IDs
        if worker_id == "auto" or not worker_id:
            import uuid

            worker_id = f"{platform}_npu_worker_{uuid.uuid4().hex[:8]}"
            logger.info("Generated new worker ID: %s", worker_id)
        else:
            logger.info("Reusing existing worker ID: %s", worker_id)

        # Get configuration from SSOT (Issue #665: uses extracted helpers)
        from autobot_shared.ssot_config import config as ssot_config

        logger.info(
            "Bootstrap config sent to worker %s (%s) at %s",
            worker_id,
            platform,
            worker_url,
        )

        return {
            "success": True,
            "worker_id": worker_id,
            "config": {
                "redis": _build_worker_redis_config(ssot_config),
                "backend": _build_worker_backend_config(ssot_config),
                "models": _build_worker_models_config(),
                "logging": _build_worker_logging_config(),
            },
            "server_timestamp": datetime.utcnow().isoformat() + "Z",
            "message": "Bootstrap configuration provided",
        }

    except Exception as e:
        logger.error("Failed to bootstrap worker: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bootstrap worker: {str(e)}",
        )


# ==============================================
# POOL MANAGEMENT ENDPOINTS (Issue #168)
# ==============================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pool_stats",
    error_code_prefix="NPU_WORKERS",
)
@router.get("/npu/pool/stats")
async def get_pool_stats(admin_check: bool = Depends(check_admin_permission)):
    """
    Get NPU worker pool statistics (Issue #168).

    Issue #744: Requires admin authentication.

    Returns pool-level metrics including:
    - Total and healthy worker counts
    - Total tasks processed
    - Active tasks
    - Success rate

    Returns:
        Pool-level metrics dict
    """
    try:
        from npu_integration import get_npu_pool

        pool = await get_npu_pool()
        stats = await pool.get_pool_stats()
        return stats

    except Exception as e:
        logger.error("Failed to get pool stats: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve pool stats: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pool_workers",
    error_code_prefix="NPU_WORKERS",
)
@router.get("/npu/pool/workers")
async def get_pool_workers(admin_check: bool = Depends(check_admin_permission)):
    """
    Get per-worker health states from the pool (Issue #168).

    Issue #744: Requires admin authentication.

    Returns detailed status for each worker including:
    - Worker ID and URL
    - Priority and enabled status
    - Health and circuit breaker state
    - Active tasks and total requests
    - Last health check timestamp

    Returns:
        Dict with list of worker states
    """
    try:
        from npu_integration import get_npu_pool

        pool = await get_npu_pool()
        workers = []

        for worker_id, state in pool.workers.items():
            config = pool._worker_configs.get(worker_id, {})
            workers.append(
                {
                    "id": state.worker_id,
                    "url": config.get("url", ""),
                    "priority": config.get("priority", 5),
                    "enabled": config.get("enabled", True),
                    "healthy": state.healthy,
                    "circuit_state": state.circuit_state.value,
                    "active_tasks": state.active_tasks,
                    "total_requests": state.total_requests,
                    "failures": state.failures,
                    "last_health_check": state.last_health_check,
                }
            )

        return {"workers": workers}

    except Exception as e:
        logger.error("Failed to get pool workers: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve pool workers: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reload_pool_config",
    error_code_prefix="NPU_WORKERS",
)
@router.post("/npu/pool/reload")
async def reload_pool_config(admin_check: bool = Depends(check_admin_permission)):
    """
    Hot-reload worker pool configuration (Issue #168).

    Issue #744: Requires admin authentication.

    Reloads the worker configuration from config/npu_workers.yaml
    without restarting the server. New workers are added, removed
    workers are removed (after active tasks drain), and existing
    workers are updated.

    Returns:
        Result with number of workers loaded and status message
    """
    try:
        from npu_integration import get_npu_pool

        pool = await get_npu_pool()
        await pool.reload_config()

        workers_count = len(pool.workers)

        logger.info("Pool configuration reloaded: %d workers", workers_count)

        return {
            "success": True,
            "workers_loaded": workers_count,
            "message": "Configuration reloaded successfully",
        }

    except Exception as e:
        logger.error("Failed to reload pool config: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload pool configuration: {str(e)}",
        )
