# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GPU Optimization Package

Issue #381: Extracted from gpu_acceleration_optimizer.py god class refactoring.
Provides GPU acceleration optimization for multi-modal AI workloads.

- types.py: Configuration and result dataclasses
- gpu_detection.py: GPU availability and capability detection
- optimization_strategies.py: Individual optimization strategy implementations
- benchmarking.py: GPU performance benchmarking
- monitoring.py: GPU efficiency monitoring and recommendations
"""

from .benchmarking import (
    benchmark_compute_performance,
    benchmark_memory_bandwidth,
    benchmark_mixed_precision,
    benchmark_tensor_cores,
    generate_benchmark_recommendations,
    run_comprehensive_benchmark,
)
from .gpu_detection import (
    check_gpu_availability,
    detect_gpu_capabilities,
    get_gpu_capabilities_dict,
)
from .monitoring import (
    calculate_memory_efficiency,
    calculate_power_efficiency,
    calculate_thermal_efficiency,
    calculate_utilization_efficiency,
    identify_optimization_opportunities,
    monitor_gpu_acceleration_efficiency,
)
from .optimization_strategies import (
    enable_mixed_precision,
    optimize_batch_processing,
    optimize_memory_allocation,
    optimize_model_compilation,
    optimize_tensor_cores,
)
from .types import (
    DEFAULT_PERFORMANCE_BASELINES,
    GPUCapabilities,
    GPUOptimizationConfig,
    GPUOptimizationResult,
)

__all__ = [
    # Types
    "GPUOptimizationConfig",
    "GPUOptimizationResult",
    "GPUCapabilities",
    "DEFAULT_PERFORMANCE_BASELINES",
    # Detection
    "check_gpu_availability",
    "detect_gpu_capabilities",
    "get_gpu_capabilities_dict",
    # Optimization strategies
    "optimize_memory_allocation",
    "optimize_batch_processing",
    "enable_mixed_precision",
    "optimize_tensor_cores",
    "optimize_model_compilation",
    # Benchmarking
    "benchmark_memory_bandwidth",
    "benchmark_compute_performance",
    "benchmark_mixed_precision",
    "benchmark_tensor_cores",
    "generate_benchmark_recommendations",
    "run_comprehensive_benchmark",
    # Monitoring
    "calculate_utilization_efficiency",
    "calculate_memory_efficiency",
    "calculate_thermal_efficiency",
    "calculate_power_efficiency",
    "identify_optimization_opportunities",
    "monitor_gpu_acceleration_efficiency",
]
