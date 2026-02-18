# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GPU Monitoring Module

Issue #381: Extracted from gpu_acceleration_optimizer.py god class refactoring.
Contains GPU monitoring and efficiency calculation functionality.
"""

import logging
import time
from typing import Any, Dict, List

from backend.utils.performance_monitor import performance_monitor

from .types import DEFAULT_PERFORMANCE_BASELINES, GPUCapabilities

logger = logging.getLogger(__name__)


def calculate_utilization_efficiency(gpu_metrics: Any) -> float:
    """Calculate GPU utilization efficiency (0-100)."""
    if not gpu_metrics:
        return 0.0

    utilization = gpu_metrics.utilization_percent

    # Optimal utilization is around 70-90%
    if 70 <= utilization <= 90:
        return 100.0
    elif utilization < 70:
        return (utilization / 70) * 100
    else:
        # Slightly penalize over-utilization
        return max(0, 100 - (utilization - 90) * 2)


def calculate_memory_efficiency(gpu_metrics: Any) -> float:
    """Calculate memory efficiency (0-100)."""
    if not gpu_metrics:
        return 0.0

    target = DEFAULT_PERFORMANCE_BASELINES["memory_utilization_target"]
    memory_util = gpu_metrics.memory_utilization_percent

    # Optimal memory utilization is around target
    if memory_util <= target:
        return (memory_util / target) * 100
    else:
        # Penalize over-utilization
        over_percent = memory_util - target
        return max(0, 100 - over_percent * 2)


def calculate_thermal_efficiency(gpu_metrics: Any) -> float:
    """Calculate thermal efficiency (0-100)."""
    if not gpu_metrics:
        return 100.0

    threshold = DEFAULT_PERFORMANCE_BASELINES["temperature_threshold_c"]
    temperature = gpu_metrics.temperature_celsius

    if temperature < threshold:
        return 100.0
    else:
        # Linearly decrease efficiency above threshold
        over_temp = temperature - threshold
        return max(0, 100 - over_temp * 5)


def calculate_power_efficiency(
    gpu_metrics: Any,
    capabilities: GPUCapabilities,
) -> float:
    """Calculate power efficiency (0-100)."""
    if not gpu_metrics:
        return 0.0

    # RTX 4070 TDP is ~200W
    expected_power = 200.0
    power_draw = gpu_metrics.power_draw_watts

    if power_draw <= 0:
        return 100.0

    # Calculate performance per watt efficiency
    utilization = gpu_metrics.utilization_percent
    if power_draw > 0:
        perf_per_watt = utilization / power_draw
        expected_perf_per_watt = 90 / expected_power  # 90% util at TDP

        efficiency = min(100, (perf_per_watt / expected_perf_per_watt) * 100)
        return efficiency

    return 0.0


def _check_metrics_opportunities(
    gpu_metrics: Any, opportunities: List[Dict[str, Any]]
) -> None:
    """Check GPU metrics for optimization opportunities (Issue #665: extracted helper)."""
    # Low utilization opportunity
    if gpu_metrics.utilization_percent < 50:
        opportunities.append(
            {
                "type": "utilization",
                "priority": "high",
                "description": "GPU utilization is low. Consider:",
                "recommendations": [
                    "Increase batch sizes",
                    "Enable parallel processing",
                    "Reduce CPU bottlenecks",
                ],
            }
        )

    # Memory pressure opportunity
    if gpu_metrics.memory_utilization_percent > 85:
        opportunities.append(
            {
                "type": "memory",
                "priority": "medium",
                "description": "GPU memory usage is high. Consider:",
                "recommendations": [
                    "Enable gradient checkpointing",
                    "Use mixed precision (FP16)",
                    "Reduce batch sizes",
                    "Enable memory pooling",
                ],
            }
        )

    # Thermal throttling opportunity
    if gpu_metrics.temperature_celsius > 80:
        opportunities.append(
            {
                "type": "thermal",
                "priority": "high",
                "description": "GPU temperature is high. Consider:",
                "recommendations": [
                    "Improve cooling",
                    "Reduce power limit",
                    "Add cooling breaks between heavy workloads",
                ],
            }
        )


def _check_capability_opportunities(
    capabilities: GPUCapabilities,
    current_optimizations: set,
    opportunities: List[Dict[str, Any]],
) -> None:
    """Check GPU capabilities for optimization opportunities (Issue #665: extracted helper)."""
    # Mixed precision opportunity
    if (
        capabilities.mixed_precision
        and "mixed_precision_enabled" not in current_optimizations
    ):
        opportunities.append(
            {
                "type": "mixed_precision",
                "priority": "medium",
                "description": "Mixed precision is available but not enabled. Consider:",
                "recommendations": [
                    "Enable automatic mixed precision",
                    "Use FP16 for inference",
                    "Configure loss scaling for training",
                ],
            }
        )

    # Tensor Core opportunity
    if (
        capabilities.tensor_cores
        and "tensor_core_optimization" not in current_optimizations
    ):
        opportunities.append(
            {
                "type": "tensor_cores",
                "priority": "medium",
                "description": "Tensor Cores available but not optimized. Consider:",
                "recommendations": [
                    "Align batch sizes to multiples of 8",
                    "Use matrix dimensions divisible by 16",
                    "Enable Tensor Core acceleration in framework",
                ],
            }
        )


def identify_optimization_opportunities(
    gpu_metrics: Any,
    capabilities: GPUCapabilities,
    current_optimizations: set,
) -> List[Dict[str, Any]]:
    """Identify potential optimization opportunities (Issue #665: uses extracted helpers)."""
    opportunities = []

    if not gpu_metrics:
        return opportunities

    _check_metrics_opportunities(gpu_metrics, opportunities)
    _check_capability_opportunities(capabilities, current_optimizations, opportunities)

    return opportunities


def _build_metrics_dict(gpu_metrics: Any) -> Dict[str, Any]:
    """
    Build metrics dictionary from GPU metrics object.

    Issue #620.
    """
    return {
        "utilization_percent": gpu_metrics.utilization_percent,
        "memory_used_mb": gpu_metrics.memory_used_mb,
        "memory_utilization_percent": gpu_metrics.memory_utilization_percent,
        "temperature_celsius": gpu_metrics.temperature_celsius,
        "power_draw_watts": gpu_metrics.power_draw_watts,
    }


def _calculate_efficiency_scores(
    gpu_metrics: Any, capabilities: GPUCapabilities
) -> Dict[str, float]:
    """
    Calculate all efficiency scores for GPU metrics.

    Issue #620.
    """
    return {
        "utilization_efficiency": calculate_utilization_efficiency(gpu_metrics),
        "memory_efficiency": calculate_memory_efficiency(gpu_metrics),
        "thermal_efficiency": calculate_thermal_efficiency(gpu_metrics),
        "power_efficiency": calculate_power_efficiency(gpu_metrics, capabilities),
    }


def _calculate_overall_efficiency(scores: Dict[str, float]) -> float:
    """
    Calculate weighted overall efficiency from individual scores.

    Issue #620.
    """
    return (
        scores["utilization_efficiency"] * 0.3
        + scores["memory_efficiency"] * 0.25
        + scores["thermal_efficiency"] * 0.25
        + scores["power_efficiency"] * 0.2
    )


async def monitor_gpu_acceleration_efficiency(
    capabilities: GPUCapabilities,
    current_optimizations: set,
) -> Dict[str, Any]:
    """Monitor GPU acceleration efficiency and identify improvements."""
    try:
        logger.info("Monitoring GPU acceleration efficiency...")
        gpu_metrics = await performance_monitor.collect_gpu_metrics()

        efficiency_report = {
            "timestamp": time.time(),
            "gpu_available": gpu_metrics is not None,
            "metrics": {},
            "efficiency_scores": {},
            "optimization_opportunities": [],
            "overall_efficiency": 0.0,
        }

        if not gpu_metrics:
            efficiency_report["message"] = "No GPU metrics available"
            return efficiency_report

        efficiency_report["metrics"] = _build_metrics_dict(gpu_metrics)
        efficiency_report["efficiency_scores"] = _calculate_efficiency_scores(
            gpu_metrics, capabilities
        )
        efficiency_report["overall_efficiency"] = _calculate_overall_efficiency(
            efficiency_report["efficiency_scores"]
        )
        efficiency_report[
            "optimization_opportunities"
        ] = identify_optimization_opportunities(
            gpu_metrics, capabilities, current_optimizations
        )

        logger.info(
            f"GPU efficiency monitoring completed. "
            f"Overall: {efficiency_report['overall_efficiency']:.1f}%"
        )
        return efficiency_report

    except Exception as e:
        logger.error("GPU efficiency monitoring failed: %s", e)
        return {"error": str(e), "timestamp": time.time()}
