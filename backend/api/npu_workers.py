# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU Worker Registry API

RESTful API endpoints for managing NPU workers, load balancing, and monitoring.

Endpoints:
- GET    /api/npu/workers - List all workers
- POST   /api/npu/workers - Register new worker
- GET    /api/npu/workers/{id} - Get worker details
- PUT    /api/npu/workers/{id} - Update worker
- DELETE /api/npu/workers/{id} - Remove worker
- POST   /api/npu/workers/{id}/test - Test worker connection
- GET    /api/npu/workers/{id}/metrics - Get worker metrics
- GET    /api/npu/load-balancing - Get load balancing config
- PUT    /api/npu/load-balancing - Update load balancing config
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from backend.models.npu_models import (
    LoadBalancingConfig,
    NPUWorkerConfig,
    NPUWorkerDetails,
    NPUWorkerMetrics,
    WorkerTestResult,
)
from backend.services.npu_worker_manager import get_worker_manager
from src.constants.network_constants import NetworkConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

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
async def list_workers():
    """
    List all registered NPU workers with their current status.

    Returns:
        List of worker details including configuration and runtime status
    """
    try:
        manager = await get_worker_manager()
        workers = await manager.list_workers()
        return workers

    except Exception as e:
        logger.error(f"Failed to list workers: {e}")
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
async def add_worker(worker_config: NPUWorkerConfig):
    """
    Register a new NPU worker.

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

        logger.info(f"Successfully registered worker: {worker_config.id}")
        return worker_details

    except ValueError as e:
        logger.warning(f"Worker registration failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to add worker: {e}")
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
async def get_worker(worker_id: str):
    """
    Get detailed information about a specific worker.

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
        logger.error(f"Failed to get worker {worker_id}: {e}")
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
async def update_worker(worker_id: str, worker_config: NPUWorkerConfig):
    """
    Update existing worker configuration.

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

        logger.info(f"Successfully updated worker: {worker_id}")
        return worker_details

    except ValueError as e:
        logger.warning(f"Worker update failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update worker {worker_id}: {e}")
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
async def remove_worker(worker_id: str):
    """
    Remove worker from registry.

    Args:
        worker_id: Worker identifier

    Raises:
        404: If worker not found
        500: If removal fails
    """
    try:
        manager = await get_worker_manager()
        await manager.remove_worker(worker_id)

        logger.info(f"Successfully removed worker: {worker_id}")
        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)

    except ValueError as e:
        logger.warning(f"Worker removal failed: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to remove worker {worker_id}: {e}")
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
async def test_worker(worker_id: str):
    """
    Test connection to a specific worker.

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
        logger.error(f"Failed to test worker {worker_id}: {e}")
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
async def get_worker_metrics(worker_id: str):
    """
    Get performance metrics for a specific worker.

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
        logger.error(f"Failed to get metrics for worker {worker_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metrics: {str(e)}",
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
async def get_load_balancing_config():
    """
    Get current load balancing configuration.

    Returns:
        Load balancing configuration including strategy and health check settings
    """
    try:
        manager = await get_worker_manager()
        config = manager.get_load_balancing_config()
        return config

    except Exception as e:
        logger.error(f"Failed to get load balancing config: {e}")
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
async def update_load_balancing_config(config: LoadBalancingConfig):
    """
    Update load balancing configuration.

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

        logger.info(f"Updated load balancing config: strategy={config.strategy}")
        return config

    except ValueError as e:
        logger.warning(f"Load balancing config update failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update load balancing config: {e}")
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
async def get_npu_status():
    """
    Get overall NPU worker pool status.

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
        logger.error(f"Failed to get NPU status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve NPU status: {str(e)}",
        )
