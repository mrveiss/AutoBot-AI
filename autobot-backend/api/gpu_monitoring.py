# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GPU Monitoring API

Issue #2267: Expose GPU acceleration optimizer functions as API endpoints.
Provides endpoints for GPU efficiency monitoring, benchmarking, capability
reporting, multimodal optimization, and config updates.

Issue #2315: Fix decorator order, router prefix, GPU guard, and tag case.
"""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas_common import DataResponse
from api.schemas_system import (
    GPUBenchmarkResponse,
    GPUCapabilitiesResponse,
    GPUConfigUpdateRequest,
    GPUConfigUpdateResponse,
    GPUEfficiencyResponse,
    GPUOptimizeResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["gpu-monitoring"])


def _gpu_unavailable_error() -> HTTPException:
    """Return a 503 error indicating GPU is not available."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": "GPU not available",
            "message": "No GPU hardware detected on this node.",
        },
    )


@router.get("/efficiency", response_model=DataResponse[GPUEfficiencyResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_gpu_efficiency",
    error_code_prefix="GPU_MONITORING",
)
async def get_gpu_efficiency(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get current GPU acceleration efficiency metrics.

    Issue #2267: Returns real-time efficiency metrics including utilization,
    throughput estimates, and optimization recommendations.
    """
    from utils.gpu_acceleration_optimizer import (
        gpu_optimizer,
        monitor_gpu_efficiency,
    )

    if not gpu_optimizer.gpu_available:
        raise _gpu_unavailable_error()

    result = await monitor_gpu_efficiency()
    return {"success": True, "efficiency": result}


@router.get("/capabilities", response_model=DataResponse[GPUCapabilitiesResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_gpu_capabilities",
    error_code_prefix="GPU_MONITORING",
)
async def get_gpu_capabilities(
    admin_check: bool = Depends(check_admin_permission),
):
    """Get GPU hardware capabilities and optimization configuration.

    Issue #2267: Returns detected capabilities (tensor cores, mixed precision,
    compute capability, memory) and current optimization config.

    Note: Intentionally does NOT check gpu_optimizer.gpu_available — returns
    data even when no GPU is present (gpu_available=false in response).
    """
    from utils.gpu_acceleration_optimizer import get_gpu_capabilities

    caps = get_gpu_capabilities()
    return {"success": True, "capabilities": caps}


@router.post("/benchmark", response_model=DataResponse[GPUBenchmarkResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="run_gpu_benchmark",
    error_code_prefix="GPU_MONITORING",
)
async def run_gpu_benchmark(
    admin_check: bool = Depends(check_admin_permission),
):
    """Run a comprehensive GPU performance benchmark.

    Issue #2267: Executes compute, memory bandwidth, mixed-precision, and
    tensor-core benchmarks. May take several seconds to complete.
    """
    from utils.gpu_acceleration_optimizer import benchmark_gpu, gpu_optimizer

    if not gpu_optimizer.gpu_available:
        raise _gpu_unavailable_error()

    result = await benchmark_gpu()
    return {"success": True, "benchmark": result}


@router.post("/optimize", response_model=DataResponse[GPUOptimizeResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="optimize_gpu_multimodal",
    error_code_prefix="GPU_MONITORING",
)
async def optimize_gpu_multimodal(
    admin_check: bool = Depends(check_admin_permission),
):
    """Optimize GPU for multimodal AI processing.

    Issue #2267: Applies memory, batch, mixed-precision, tensor-core, and
    model-compilation optimizations. Returns a structured result with
    performance improvement metrics and applied optimization list.
    """
    from utils.gpu_acceleration_optimizer import (
        gpu_optimizer,
        optimize_gpu_for_multimodal,
    )

    if not gpu_optimizer.gpu_available:
        raise _gpu_unavailable_error()

    result = await optimize_gpu_for_multimodal()
    return {"success": True, "optimization": asdict(result)}


@router.patch("/config", response_model=DataResponse[GPUConfigUpdateResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_gpu_config",
    error_code_prefix="GPU_MONITORING",
)
async def update_gpu_config(
    body: GPUConfigUpdateRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """Update GPU optimization configuration.

    Issue #2267: Accepts a dict of config field names to new values.
    Unknown keys are ignored with a warning; valid keys are applied
    immediately to the running optimizer instance.
    """
    from utils.gpu_acceleration_optimizer import gpu_optimizer, update_gpu_config

    if not gpu_optimizer.gpu_available:
        raise _gpu_unavailable_error()

    if not body.updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'updates' must be a non-empty dict.",
        )

    updated = await update_gpu_config(body.updates)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to apply GPU configuration updates.",
        )

    logger.info("GPU optimization config updated: %s", list(body.updates.keys()))
    return {"success": True, "updated_keys": list(body.updates.keys())}
