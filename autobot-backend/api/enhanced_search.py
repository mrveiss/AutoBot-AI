#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Search API with NPU Acceleration
Provides NPU-accelerated semantic search endpoints for AutoBot
"""

import asyncio
import time
from typing import List, Optional

from ai_hardware_accelerator import HardwareDevice
from backend.type_defs.common import Metadata
from fastapi import APIRouter, HTTPException

# Import NPU semantic search components
from npu_semantic_search import get_npu_search_engine
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_llm_logger

logger = get_llm_logger("enhanced_search_api")

router = APIRouter(tags=["Enhanced Search"])


# Pydantic models for API
class SearchRequest(BaseModel):
    """Enhanced search request model."""

    query: str = Field(..., description="Search query")
    similarity_top_k: int = Field(
        10, description="Number of results to return", ge=1, le=100
    )
    filters: Optional[Metadata] = Field(None, description="Optional metadata filters")
    enable_npu_acceleration: bool = Field(True, description="Enable NPU acceleration")
    force_device: Optional[str] = Field(
        None, description="Force specific device (npu/gpu/cpu)"
    )


class SearchResponse(BaseModel):
    """Enhanced search response model."""

    query: str
    results: List[Metadata]
    metrics: Metadata
    total_results: int
    search_time_ms: float
    device_used: str
    cache_hit: bool = False


class BenchmarkRequest(BaseModel):
    """Benchmark request model."""

    test_queries: List[str] = Field(..., description="List of test queries")
    iterations: int = Field(
        3, description="Number of iterations per query", ge=1, le=10
    )


class OptimizationRequest(BaseModel):
    """Optimization request model."""

    workload_type: str = Field(
        "balanced",
        description=(
            "Workload type: latency_optimized, throughput_optimized, quality_optimized,"
            "balanced"
        ),
    )


def _parse_force_device(force_device_str: Optional[str]) -> Optional[HardwareDevice]:
    """
    Parse and validate force_device parameter (Issue #665: extracted helper).

    Args:
        force_device_str: Optional device string (npu/gpu/cpu)

    Returns:
        HardwareDevice enum or None

    Raises:
        HTTPException: If device string is invalid
    """
    if not force_device_str:
        return None
    try:
        return HardwareDevice(force_device_str.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid device '{force_device_str}'. Must be one of: npu, gpu, cpu",
        )


def _convert_search_results_to_api_format(search_results: list) -> list:
    """
    Convert search results to API response format (Issue #665: extracted helper).
    """
    return [
        {
            "content": result.content,
            "metadata": result.metadata,
            "score": result.score,
            "doc_id": result.doc_id,
            "device_used": result.device_used,
            "processing_time_ms": result.processing_time_ms,
            "embedding_model": result.embedding_model,
        }
        for result in search_results
    ]


def _convert_metrics_to_api_format(metrics) -> dict:
    """
    Convert metrics object to API response format (Issue #665: extracted helper).
    """
    return {
        "total_documents_searched": metrics.total_documents_searched,
        "embedding_generation_time_ms": metrics.embedding_generation_time_ms,
        "similarity_computation_time_ms": metrics.similarity_computation_time_ms,
        "total_search_time_ms": metrics.total_search_time_ms,
        "device_used": metrics.device_used,
        "hardware_utilization": metrics.hardware_utilization,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_semantic_search",
    error_code_prefix="ENHANCED_SEARCH",
)
@router.post("/semantic", response_model=SearchResponse)
async def enhanced_semantic_search(request: SearchRequest):
    """
    Perform NPU-enhanced semantic search.

    Issue #665: Refactored to use extracted helper functions.

    This endpoint provides intelligent hardware-accelerated semantic search:
    - NPU acceleration for lightweight embedding generation
    - GPU acceleration for heavy compute tasks
    - CPU fallback for reliability
    - Intelligent device selection based on workload
    """
    start_time = time.time()

    try:
        search_engine = await get_npu_search_engine()
        force_device = _parse_force_device(request.force_device)

        search_results, metrics = await search_engine.enhanced_search(
            query=request.query,
            similarity_top_k=request.similarity_top_k,
            filters=request.filters,
            enable_npu_acceleration=request.enable_npu_acceleration,
            force_device=force_device,
        )

        results_data = _convert_search_results_to_api_format(search_results)
        metrics_data = _convert_metrics_to_api_format(metrics)
        total_time = (time.time() - start_time) * 1000

        logger.info(
            "Enhanced search completed: '%s...' -> %d results in %.2fms using %s",
            request.query[:50],
            len(results_data),
            total_time,
            metrics.device_used,
        )

        return SearchResponse(
            query=request.query,
            results=results_data,
            metrics=metrics_data,
            total_results=len(results_data),
            search_time_ms=total_time,
            device_used=metrics.device_used,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Enhanced search failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_hardware_status",
    error_code_prefix="ENHANCED_SEARCH",
)
@router.get("/hardware/status")
async def get_hardware_status():
    """
    Get current hardware status and utilization metrics.

    Returns information about NPU, GPU, and CPU availability and performance.
    """
    try:
        search_engine = await get_npu_search_engine()
        statistics = await search_engine.get_search_statistics()

        return {
            "hardware_status": statistics.get("hardware_status", {}),
            "knowledge_base_ready": statistics.get("knowledge_base_ready", False),
            "cache_stats": statistics.get("cache_stats", {}),
            "configuration": statistics.get("configuration", {}),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Failed to get hardware status: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get hardware status: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="benchmark_search_performance",
    error_code_prefix="ENHANCED_SEARCH",
)
@router.post("/benchmark")
async def benchmark_search_performance(request: BenchmarkRequest):
    """
    Benchmark search performance across different hardware configurations.

    Tests search performance on NPU, GPU, and CPU to provide optimization insights.
    """
    try:
        search_engine = await get_npu_search_engine()

        # Run benchmark
        benchmark_results = await search_engine.benchmark_search_performance(
            test_queries=request.test_queries, iterations=request.iterations
        )

        return {
            "benchmark_results": benchmark_results,
            "timestamp": time.time(),
            "recommendations": _generate_performance_recommendations(benchmark_results),
        }

    except Exception as e:
        logger.error("Benchmark failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Benchmark failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="optimize_search_engine",
    error_code_prefix="ENHANCED_SEARCH",
)
@router.post("/optimize")
async def optimize_search_engine(request: OptimizationRequest):
    """
    Optimize search engine for specific workload types.

    Available workload types:
    - latency_optimized: Minimize response time
    - throughput_optimized: Maximize requests per second
    - quality_optimized: Best search result quality
    - balanced: Balanced performance (default)
    """
    try:
        search_engine = await get_npu_search_engine()

        optimizations = await search_engine.optimize_for_workload(request.workload_type)

        return {
            "optimization_applied": request.workload_type,
            "configuration": optimizations,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Optimization failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_analytics",
    error_code_prefix="ENHANCED_SEARCH",
)
@router.get("/performance/analytics")
async def get_performance_analytics():
    """
    Get comprehensive performance analytics and recommendations.

    Provides insights into search engine performance, hardware utilization,
    and optimization opportunities.
    """
    try:
        search_engine = await get_npu_search_engine()

        # Get current statistics
        statistics = await search_engine.get_search_statistics()

        # Get hardware status from AI accelerator
        ai_accelerator = search_engine.ai_accelerator
        if ai_accelerator:
            # Issue #619: Parallelize independent hardware operations
            hardware_status, performance_analysis = await asyncio.gather(
                ai_accelerator.get_hardware_status(),
                ai_accelerator.optimize_performance(),
            )
        else:
            hardware_status = {}
            performance_analysis = {"message": "AI accelerator not available"}

        return {
            "search_statistics": statistics,
            "hardware_status": hardware_status,
            "performance_analysis": performance_analysis,
            "recommendations": _generate_system_recommendations(
                statistics, hardware_status
            ),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Failed to get performance analytics: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get performance analytics: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_npu_connectivity",
    error_code_prefix="ENHANCED_SEARCH",
)
@router.get("/test/connectivity")
async def test_npu_connectivity():
    """
    Test NPU Worker connectivity and capabilities.

    Verifies that the NPU Worker is accessible and NPU hardware is available.
    """
    try:
        search_engine = await get_npu_search_engine()

        # Test basic connectivity
        await search_engine._test_npu_connectivity()

        # Test search functionality with a simple query
        test_results, test_metrics = await search_engine.enhanced_search(
            query="test connectivity", similarity_top_k=3, enable_npu_acceleration=True
        )

        return {
            "connectivity": "success",
            "npu_worker_url": search_engine.npu_worker_url,
            "test_search_results": len(test_results),
            "test_device_used": test_metrics.device_used,
            "test_time_ms": test_metrics.total_search_time_ms,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.warning("NPU connectivity test failed: %s", e)
        return {
            "connectivity": "failed",
            "error": str(e),
            "fallback_available": True,
            "timestamp": time.time(),
        }


def _evaluate_device_timing(
    stats: Optional[Metadata],
    device_name: str,
    low_threshold: float,
    high_threshold: float,
    excellent_msg: str,
    slow_msg: str,
) -> List[str]:
    """
    Evaluate device timing stats and generate recommendations.

    Issue #281: Extracted helper to reduce repetition in _generate_performance_recommendations.

    Args:
        stats: Device stats dictionary with 'average_total_time_ms' key
        device_name: Name of device for logging (unused, kept for clarity)
        low_threshold: Threshold below which performance is excellent
        high_threshold: Threshold above which performance is slow
        excellent_msg: Message for excellent performance
        slow_msg: Message for slow performance

    Returns:
        List of recommendation strings (0 or 1 item)
    """
    if not stats:
        return []

    avg_time = stats.get("average_total_time_ms", 0)

    if avg_time < low_threshold:
        return [excellent_msg]
    elif avg_time > high_threshold:
        return [slow_msg]

    return []


def _generate_performance_recommendations(
    benchmark_results: Metadata,
) -> List[str]:
    """Generate performance recommendations based on benchmark results."""
    recommendations = []

    summary = benchmark_results.get("summary", {})

    # Analyze NPU performance (Issue #281: success_rate check kept separate)
    npu_stats = summary.get("npu")
    if npu_stats:
        if npu_stats.get("success_rate", 100) < 80:
            recommendations.append(
                "NPU success rate is low - check NPU Worker stability and connectivity"
            )
        else:
            recommendations.extend(
                _evaluate_device_timing(
                    npu_stats,
                    "NPU",
                    low_threshold=1000,
                    high_threshold=3000,
                    excellent_msg="NPU performance is excellent - consider routing more lightweight tasks to NPU",
                    slow_msg="NPU response times are high - consider model optimization or reduce batch sizes",
                )
            )
    else:
        recommendations.append(
            "NPU not available - verify NPU Worker setup and Intel NPU drivers"
        )

    # Analyze GPU performance (Issue #281: Using extracted helper)
    gpu_stats = summary.get("gpu")
    recommendations.extend(
        _evaluate_device_timing(
            gpu_stats,
            "GPU",
            low_threshold=500,
            high_threshold=2000,
            excellent_msg="GPU performance is excellent - consider routing more complex tasks to GPU",
            slow_msg="GPU response times are high - check GPU utilization and memory usage",
        )
    )

    # Compare devices
    if npu_stats and gpu_stats:
        npu_time = npu_stats["average_total_time_ms"]
        gpu_time = gpu_stats["average_total_time_ms"]

        if npu_time < gpu_time * 0.7:
            recommendations.append(
                "NPU significantly outperforms GPU for these queries - increase NPU utilization"
            )
        elif gpu_time < npu_time * 0.7:
            recommendations.append(
                "GPU significantly outperforms NPU for these queries - prefer GPU for similar workloads"
            )

    if not recommendations:
        recommendations.append(
            "Performance looks good across all devices - system is well optimized"
        )

    return recommendations


def _generate_system_recommendations(
    statistics: Metadata, hardware_status: Metadata
) -> List[str]:
    """Generate system-wide recommendations."""
    recommendations = []

    # Cache analysis
    cache_stats = statistics.get("cache_stats", {})
    cache_size = cache_stats.get("cache_size", 0)
    cache_max_size = cache_stats.get("cache_max_size", 100)

    if cache_size == 0:
        recommendations.append(
            "Search cache is empty - performance will improve as cache builds up"
        )
    elif cache_size >= cache_max_size * 0.9:
        recommendations.append(
            "Search cache is near capacity - consider increasing cache_max_size for better hit rates"
        )

    # Hardware availability
    devices = hardware_status.get("devices", {})

    npu_available = devices.get("npu", {}).get("available", False)
    gpu_available = devices.get("gpu", {}).get("available", False)

    if not npu_available and not gpu_available:
        recommendations.append(
            "CRITICAL: No hardware acceleration available - check NPU Worker and GPU drivers"
        )
    elif not npu_available:
        recommendations.append(
            "NPU not available - missing Intel NPU optimization opportunity"
        )
    elif not gpu_available:
        recommendations.append(
            "GPU not available - missing RTX 4070 optimization opportunity"
        )

    # Knowledge base status
    kb_ready = statistics.get("knowledge_base_ready", False)
    if not kb_ready:
        recommendations.append(
            "Knowledge base vector store not ready - semantic search quality may be degraded"
        )

    return recommendations


# Health check endpoint
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="health_check",
    error_code_prefix="ENHANCED_SEARCH",
)
@router.get("/health")
async def health_check():
    """Health check for enhanced search service."""
    try:
        search_engine = await get_npu_search_engine()
        statistics = await search_engine.get_search_statistics()

        return {
            "status": "healthy",
            "service": "enhanced_search",
            "npu_search_engine_ready": True,
            "knowledge_base_ready": statistics.get("knowledge_base_ready", False),
            "cache_size": statistics.get("cache_stats", {}).get("cache_size", 0),
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error("Health check failed: %s", e)
        return {
            "status": "unhealthy",
            "service": "enhanced_search",
            "error": str(e),
            "timestamp": time.time(),
        }
