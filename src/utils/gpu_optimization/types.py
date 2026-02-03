# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GPU Optimization Types Module

Issue #381: Extracted from gpu_acceleration_optimizer.py god class refactoring.
Contains dataclasses and type definitions for GPU optimization.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GPUOptimizationConfig:
    """GPU optimization configuration"""

    # Memory Management
    memory_growth_enabled: bool = True
    memory_limit_mb: Optional[int] = None
    memory_allocation_strategy: str = "dynamic"  # dynamic, pre_allocated, growth_limit

    # Performance Settings
    mixed_precision_enabled: bool = True
    tensor_core_optimization: bool = True
    cuda_graphs_enabled: bool = False
    memory_pool_enabled: bool = True

    # Batch Processing
    auto_batch_sizing: bool = True
    max_batch_size: int = 64
    adaptive_batching: bool = True
    batch_timeout_ms: int = 100

    # Multi-Modal Specific
    image_batch_size: int = 16
    text_batch_size: int = 32
    audio_batch_size: int = 8
    cross_modal_fusion_batch_size: int = 8

    # Inference Optimization
    model_compilation_enabled: bool = True
    kernel_fusion_enabled: bool = True
    operator_optimization: bool = True

    # Monitoring
    performance_tracking_enabled: bool = True
    thermal_monitoring_enabled: bool = True
    power_monitoring_enabled: bool = True


@dataclass
class GPUOptimizationResult:
    """Result of GPU optimization operation"""

    success: bool
    optimization_type: str
    performance_improvement: float  # Percentage improvement
    memory_savings_mb: float
    throughput_improvement: float
    latency_reduction_ms: float
    recommendations: List[str]
    warnings: List[str]
    applied_optimizations: List[str]
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def create_failed(
        cls, optimization_type: str, error: str
    ) -> "GPUOptimizationResult":
        """Create a failed optimization result."""
        return cls(
            success=False,
            optimization_type=optimization_type,
            performance_improvement=0.0,
            memory_savings_mb=0.0,
            throughput_improvement=0.0,
            latency_reduction_ms=0.0,
            recommendations=[],
            warnings=[f"Optimization failed: {error}"],
            applied_optimizations=[],
        )


@dataclass
class GPUCapabilities:
    """GPU hardware capabilities"""

    name: str = ""
    tensor_cores: bool = False
    mixed_precision: bool = False
    cuda_version: Optional[str] = None
    compute_capability: Optional[str] = None
    memory_gb: float = 0
    max_threads_per_block: int = 0
    multiprocessor_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "tensor_cores": self.tensor_cores,
            "mixed_precision": self.mixed_precision,
            "cuda_version": self.cuda_version,
            "compute_capability": self.compute_capability,
            "memory_gb": self.memory_gb,
            "max_threads_per_block": self.max_threads_per_block,
            "multiprocessor_count": self.multiprocessor_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GPUCapabilities":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            tensor_cores=data.get("tensor_cores", False),
            mixed_precision=data.get("mixed_precision", False),
            cuda_version=data.get("cuda_version"),
            compute_capability=data.get("compute_capability"),
            memory_gb=data.get("memory_gb", 0),
            max_threads_per_block=data.get("max_threads_per_block", 0),
            multiprocessor_count=data.get("multiprocessor_count", 0),
        )


# Default performance baselines
DEFAULT_PERFORMANCE_BASELINES: Dict[str, float] = {
    "inference_latency_ms": 50.0,
    "memory_utilization_target": 80.0,
    "throughput_target_fps": 30.0,
    "temperature_threshold_c": 75.0,
    "power_efficiency_target": 0.8,  # Performance per watt
}
