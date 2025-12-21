# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GPU Acceleration Optimization Utility

Issue #381: This file has been refactored into the gpu_optimization/ package.
This thin facade maintains backward compatibility while delegating to focused modules.

See: src/utils/gpu_optimization/
- types.py: GPUOptimizationConfig, GPUOptimizationResult, GPUCapabilities
- gpu_detection.py: GPU availability and capability detection
- optimization_strategies.py: Individual optimization strategy implementations
- benchmarking.py: GPU performance benchmarking
- monitoring.py: GPU efficiency monitoring and recommendations

Optimizes GPU utilization for multi-modal AI workloads and provides acceleration insights.
"""

import asyncio
import logging
import time
from dataclasses import asdict
from typing import Any, Dict, List

# Re-export all public API from the package for backward compatibility
from src.utils.gpu_optimization import (
    DEFAULT_PERFORMANCE_BASELINES,
    GPUCapabilities,
    GPUOptimizationConfig,
    GPUOptimizationResult,
    check_gpu_availability,
    detect_gpu_capabilities,
    enable_mixed_precision,
    monitor_gpu_acceleration_efficiency,
    optimize_batch_processing,
    optimize_memory_allocation,
    optimize_model_compilation,
    optimize_tensor_cores,
    run_comprehensive_benchmark,
)

# Re-export benchmarking functions for backward compatibility (used by external code)
from src.utils.gpu_optimization import (  # noqa: F401
    benchmark_compute_performance,
    benchmark_memory_bandwidth,
    benchmark_mixed_precision,
    benchmark_tensor_cores,
    generate_benchmark_recommendations,
)
from src.utils.performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


__all__ = [
    # Types
    "GPUOptimizationConfig",
    "GPUOptimizationResult",
    "GPUCapabilities",
    # Main class
    "GPUAccelerationOptimizer",
    # Global instance
    "gpu_optimizer",
    # Convenience functions
    "optimize_gpu_for_multimodal",
    "benchmark_gpu",
    "monitor_gpu_efficiency",
    "get_gpu_capabilities",
    "update_gpu_config",
]


class GPUAccelerationOptimizer:
    """
    GPU acceleration optimizer for AutoBot's multi-modal AI workloads.
    Focuses on RTX 4070 optimization and Intel NPU coordination.

    Issue #381: Refactored to delegate to gpu_optimization package components.
    """

    def __init__(self):
        """Initialize GPU optimizer with config, history, and capabilities."""
        self.logger = logging.getLogger(__name__)
        self.config = GPUOptimizationConfig()
        self.optimization_history: List[GPUOptimizationResult] = []
        self.baseline_metrics = None
        self.current_optimizations: set = set()

        # Lock for thread-safe access to shared mutable state
        self._lock = asyncio.Lock()

        # GPU availability and capabilities (delegates to package)
        self.gpu_available = check_gpu_availability()
        self._capabilities = detect_gpu_capabilities(self.gpu_available)
        self.gpu_capabilities = self._capabilities.to_dict()

        # Performance baselines
        self.performance_baselines = DEFAULT_PERFORMANCE_BASELINES.copy()

        self.logger.info("GPU Acceleration Optimizer initialized")
        if self.gpu_available:
            self.logger.info("GPU capabilities detected: %s", self.gpu_capabilities)

    async def _apply_optimization_passes(self) -> tuple:
        """Apply all optimization passes and collect results (Issue #398: extracted).

        Returns:
            Tuple of (applied_optimizations, recommendations)
        """
        applied_optimizations = []
        recommendations = []

        # Memory optimization
        memory_result = await optimize_memory_allocation(self.config)
        if memory_result["success"]:
            applied_optimizations.extend(memory_result["optimizations"])
        recommendations.extend(memory_result["recommendations"])

        # Batch processing optimization
        batch_result = await optimize_batch_processing(self.config, self._capabilities)
        if batch_result["success"]:
            applied_optimizations.extend(batch_result["optimizations"])
        recommendations.extend(batch_result["recommendations"])

        # Mixed precision optimization
        if self._capabilities.mixed_precision:
            precision_result = await enable_mixed_precision(self.config, self._capabilities)
            if precision_result["success"]:
                applied_optimizations.extend(precision_result["optimizations"])
            recommendations.extend(precision_result["recommendations"])

        # Tensor Core optimization
        if self._capabilities.tensor_cores:
            tensor_result = await optimize_tensor_cores(self.config, self._capabilities)
            if tensor_result["success"]:
                applied_optimizations.extend(tensor_result["optimizations"])
            recommendations.extend(tensor_result["recommendations"])

        # Model compilation optimization
        compilation_result = await optimize_model_compilation(self.config)
        if compilation_result["success"]:
            applied_optimizations.extend(compilation_result["optimizations"])
        recommendations.extend(compilation_result["recommendations"])

        return applied_optimizations, recommendations

    def _calculate_metrics_changes(
        self, baseline: Dict[str, float], post_optimization: Dict[str, float]
    ) -> tuple:
        """Calculate improvement metrics between baseline and post-optimization (Issue #398: extracted).

        Returns:
            Tuple of (performance_improvement, memory_savings, throughput_improvement, latency_reduction)
        """
        performance_improvement = self._calculate_performance_improvement(
            baseline, post_optimization
        )
        memory_savings = baseline.get("memory_used_mb", 0) - post_optimization.get(
            "memory_used_mb", 0
        )
        throughput_improvement = post_optimization.get(
            "throughput_fps", 0
        ) - baseline.get("throughput_fps", 0)
        latency_reduction = baseline.get(
            "inference_latency_ms", 0
        ) - post_optimization.get("inference_latency_ms", 0)

        return performance_improvement, memory_savings, throughput_improvement, latency_reduction

    async def optimize_for_multimodal_workload(self) -> GPUOptimizationResult:
        """Optimize GPU for multi-modal AI workloads (Issue #398: refactored to use helpers)."""
        try:
            self.logger.info("Starting multi-modal GPU optimization...")

            # Collect baseline metrics
            baseline = await self._collect_performance_baseline()
            warnings: List[str] = []

            # Issue #398: Apply all optimization passes using extracted helper
            applied_optimizations, recommendations = await self._apply_optimization_passes()

            # Collect post-optimization metrics
            post_optimization = await self._collect_performance_baseline()

            # Issue #398: Calculate improvements using extracted helper
            (
                performance_improvement,
                memory_savings,
                throughput_improvement,
                latency_reduction,
            ) = self._calculate_metrics_changes(baseline, post_optimization)

            # Create optimization result
            result = GPUOptimizationResult(
                success=len(applied_optimizations) > 0,
                optimization_type="multimodal_workload",
                performance_improvement=performance_improvement,
                memory_savings_mb=memory_savings,
                throughput_improvement=throughput_improvement,
                latency_reduction_ms=latency_reduction,
                recommendations=recommendations,
                warnings=warnings,
                applied_optimizations=applied_optimizations,
                timestamp=time.time(),
            )

            # Store optimization result (thread-safe)
            async with self._lock:
                self.optimization_history.append(result)

            self.logger.info(
                f"Multi-modal optimization completed: "
                f"{performance_improvement:.1f}% improvement"
            )
            return result

        except Exception as e:
            self.logger.error("Multi-modal optimization failed: %s", e)
            return GPUOptimizationResult.create_failed("multimodal_workload", str(e))

    async def _collect_performance_baseline(self) -> Dict[str, float]:
        """Collect current performance metrics as baseline."""
        try:
            gpu_metrics = await performance_monitor.collect_gpu_metrics()

            baseline = {
                "gpu_utilization_percent": 0.0,
                "memory_used_mb": 0.0,
                "memory_utilization_percent": 0.0,
                "temperature_celsius": 0.0,
                "power_draw_watts": 0.0,
                "inference_latency_ms": 50.0,
                "throughput_fps": 10.0,
            }

            if gpu_metrics:
                baseline.update({
                    "gpu_utilization_percent": gpu_metrics.utilization_percent,
                    "memory_used_mb": gpu_metrics.memory_used_mb,
                    "memory_utilization_percent": gpu_metrics.memory_utilization_percent,
                    "temperature_celsius": gpu_metrics.temperature_celsius,
                    "power_draw_watts": gpu_metrics.power_draw_watts,
                })

            return baseline

        except Exception as e:
            self.logger.error("Error collecting performance baseline: %s", e)
            return {}

    def _calculate_performance_improvement(
        self, baseline: Dict[str, float], post_opt: Dict[str, float]
    ) -> float:
        """Calculate overall performance improvement percentage."""
        try:
            if not baseline or not post_opt:
                return 0.0

            improvements = []

            # GPU utilization improvement (higher is better)
            baseline_util = baseline.get("gpu_utilization_percent", 0)
            post_util = post_opt.get("gpu_utilization_percent", 0)
            if baseline_util > 0:
                util_improvement = ((post_util - baseline_util) / baseline_util) * 100
                improvements.append(util_improvement)

            # Latency improvement (lower is better)
            baseline_latency = baseline.get("inference_latency_ms", 0)
            post_latency = post_opt.get("inference_latency_ms", 0)
            if baseline_latency > 0 and post_latency > 0:
                latency_improvement = (
                    (baseline_latency - post_latency) / baseline_latency
                ) * 100
                improvements.append(latency_improvement)

            # Throughput improvement (higher is better)
            baseline_throughput = baseline.get("throughput_fps", 0)
            post_throughput = post_opt.get("throughput_fps", 0)
            if baseline_throughput > 0:
                throughput_improvement = (
                    (post_throughput - baseline_throughput) / baseline_throughput
                ) * 100
                improvements.append(throughput_improvement)

            return sum(improvements) / len(improvements) if improvements else 0.0

        except Exception as e:
            self.logger.error("Error calculating performance improvement: %s", e)
            return 0.0

    async def benchmark_gpu_performance(self) -> Dict[str, Any]:
        """Run comprehensive GPU performance benchmark."""
        return await run_comprehensive_benchmark(self._capabilities)

    async def monitor_gpu_acceleration_efficiency(self) -> Dict[str, Any]:
        """Monitor current GPU acceleration efficiency."""
        return await monitor_gpu_acceleration_efficiency(
            self._capabilities, self.current_optimizations
        )

    def get_optimization_config(self) -> GPUOptimizationConfig:
        """Get current optimization configuration."""
        return self.config

    async def update_optimization_config(self, config_updates: Dict[str, Any]) -> bool:
        """Update optimization configuration (thread-safe)."""
        try:
            async with self._lock:
                for key, value in config_updates.items():
                    if hasattr(self.config, key):
                        setattr(self.config, key, value)
                    else:
                        self.logger.warning("Unknown config key: %s", key)

            self.logger.info("GPU optimization configuration updated")
            return True

        except Exception as e:
            self.logger.error("Failed to update optimization config: %s", e)
            return False

    async def get_optimization_history(self) -> List[GPUOptimizationResult]:
        """Get history of optimization operations (thread-safe)."""
        async with self._lock:
            return list(self.optimization_history)

    def get_gpu_capabilities_report(self) -> Dict[str, Any]:
        """Get comprehensive GPU capabilities report."""
        return {
            "gpu_available": self.gpu_available,
            "capabilities": self.gpu_capabilities,
            "optimization_config": asdict(self.config),
            "performance_baselines": self.performance_baselines,
            "supported_optimizations": {
                "mixed_precision": self._capabilities.mixed_precision,
                "tensor_cores": self._capabilities.tensor_cores,
                "cuda_graphs": True,
                "memory_pooling": True,
                "kernel_fusion": True,
                "adaptive_batching": True,
            },
            "recommendations": self._get_gpu_setup_recommendations(),
        }

    def _get_gpu_setup_recommendations(self) -> List[str]:
        """Get recommendations for GPU setup and configuration."""
        recommendations = []

        memory_gb = self._capabilities.memory_gb

        if memory_gb >= 12:
            recommendations.append(
                "High memory GPU - excellent for large models and high batch sizes"
            )
        elif memory_gb >= 8:
            recommendations.append(
                "Good memory capacity - suitable for most AI workloads"
            )
        else:
            recommendations.append(
                "Limited memory - use memory optimization techniques"
            )

        if self._capabilities.tensor_cores:
            recommendations.append(
                "Tensor Cores available - enable for maximum AI performance"
            )

        if self._capabilities.mixed_precision:
            recommendations.append(
                "Mixed precision supported - can double performance with FP16"
            )

        compute_cap = self._capabilities.compute_capability
        if compute_cap and float(compute_cap) >= 7.5:
            recommendations.append(
                "Modern compute capability - supports latest CUDA optimizations"
            )

        return recommendations


# Global GPU acceleration optimizer instance
gpu_optimizer = GPUAccelerationOptimizer()


# Convenience functions for easy integration
async def optimize_gpu_for_multimodal() -> GPUOptimizationResult:
    """Optimize GPU for multi-modal AI workloads."""
    return await gpu_optimizer.optimize_for_multimodal_workload()


async def benchmark_gpu() -> Dict[str, Any]:
    """Run comprehensive GPU benchmark."""
    return await gpu_optimizer.benchmark_gpu_performance()


async def monitor_gpu_efficiency() -> Dict[str, Any]:
    """Monitor current GPU acceleration efficiency."""
    return await gpu_optimizer.monitor_gpu_acceleration_efficiency()


def get_gpu_capabilities() -> Dict[str, Any]:
    """Get GPU capabilities report."""
    return gpu_optimizer.get_gpu_capabilities_report()


async def update_gpu_config(config_updates: Dict[str, Any]) -> bool:
    """Update GPU optimization configuration."""
    return await gpu_optimizer.update_optimization_config(config_updates)


if __name__ == "__main__":
    import json

    async def test_gpu_optimization():
        """Test GPU optimization functionality."""
        print("Testing GPU Acceleration Optimizer...")

        # Get capabilities
        capabilities = get_gpu_capabilities()
        print(f"GPU Capabilities: {json.dumps(capabilities, indent=2)}")

        # Run benchmark
        benchmark = await benchmark_gpu()
        print(f"GPU Benchmark: {json.dumps(benchmark, indent=2, default=str)}")

        # Monitor efficiency
        efficiency = await monitor_gpu_efficiency()
        print(f"GPU Efficiency: {json.dumps(efficiency, indent=2, default=str)}")

        # Optimize for multi-modal
        optimization = await optimize_gpu_for_multimodal()
        print(
            f"Optimization Result: "
            f"{json.dumps(asdict(optimization), indent=2, default=str)}"
        )

    asyncio.run(test_gpu_optimization())
