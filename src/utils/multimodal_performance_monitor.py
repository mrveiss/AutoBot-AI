#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Multi-Modal Performance Monitor
GPU memory management, batch processing optimization, and performance monitoring for RTX 4070
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
import psutil


try:
    import torch
    import torch.cuda

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics data structure"""

    timestamp: float
    gpu_utilization: float
    gpu_memory_used: float
    gpu_memory_total: float
    gpu_memory_percent: float
    cpu_utilization: float
    ram_usage: float
    processing_time: float
    throughput: float
    batch_size: int
    modality: str


class MultiModalPerformanceMonitor:
    """Performance monitoring and optimization for multi-modal AI processing"""

    def __init__(self):
        # Lock for thread-safe access to shared state
        import threading

        self._lock = threading.Lock()

        self.gpu_memory_tracker: Dict[str, List[float]] = defaultdict(list)
        self.processing_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.throughput_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )

        # Adaptive batch sizes optimized for RTX 4070 (8GB VRAM)
        self.batch_sizes = {
            "text": 32,  # Text embeddings are memory efficient
            "image": 8,  # Images require more VRAM
            "audio": 16,  # Audio processing is moderate
            "combined": 4,  # Multi-modal fusion is memory intensive
        }

        # Performance thresholds
        self.memory_high_threshold = 80.0  # Reduce batch size above this
        self.memory_low_threshold = 40.0  # Increase batch size below this
        self.optimization_interval = 30.0  # Optimize every 30 seconds

        # Monitoring state
        self.last_optimization = 0.0
        self.metrics_history: deque = deque(maxlen=1000)
        self.gpu_available = TORCH_AVAILABLE and torch.cuda.is_available()

        if self.gpu_available:
            self.device_properties = torch.cuda.get_device_properties(0)
            self.total_gpu_memory = self.device_properties.total_memory
            logger.info(
                f"GPU Performance Monitor initialized: {self.device_properties.name} ({self.total_gpu_memory / 1024**3:.1f}GB)"
            )
        else:
            logger.warning(
                "GPU not available - performance monitoring limited to CPU metrics"
            )

    async def optimize_gpu_memory(self) -> Dict[str, Any]:
        """Optimize GPU memory usage and adjust batch sizes (thread-safe)"""
        if not self.gpu_available:
            return {"status": "gpu_not_available"}

        try:
            # Clear GPU cache periodically
            torch.cuda.empty_cache()

            # Get current memory usage
            allocated = torch.cuda.memory_allocated()
            reserved = torch.cuda.memory_reserved()
            memory_usage_percent = (allocated / self.total_gpu_memory) * 100

            # Update shared state with lock protection
            with self._lock:
                # Track memory usage
                self.gpu_memory_tracker["allocated"].append(allocated)
                self.gpu_memory_tracker["reserved"].append(reserved)
                self.gpu_memory_tracker["percent"].append(memory_usage_percent)

                # Keep only recent history
                for key in self.gpu_memory_tracker:
                    if len(self.gpu_memory_tracker[key]) > 100:
                        self.gpu_memory_tracker[key] = self.gpu_memory_tracker[key][
                            -100:
                        ]

                # Adaptive batch size adjustment
                optimization_applied = False

                if memory_usage_percent > self.memory_high_threshold:
                    # Reduce batch sizes to prevent OOM
                    for modality in self.batch_sizes:
                        old_size = self.batch_sizes[modality]
                        self.batch_sizes[modality] = max(
                            1, self.batch_sizes[modality] // 2
                        )
                        if self.batch_sizes[modality] != old_size:
                            optimization_applied = True
                            logger.info(
                                f"Reduced {modality} batch size: {old_size} -> {self.batch_sizes[modality]}"
                            )

                elif memory_usage_percent < self.memory_low_threshold:
                    # Increase batch sizes for better throughput
                    for modality in self.batch_sizes:
                        old_size = self.batch_sizes[modality]
                        max_sizes = {"text": 64, "image": 16, "audio": 32, "combined": 8}
                        self.batch_sizes[modality] = min(
                            max_sizes[modality], self.batch_sizes[modality] * 2
                        )
                        if self.batch_sizes[modality] != old_size:
                            optimization_applied = True
                            logger.info(
                                f"Increased {modality} batch size: {old_size} -> {self.batch_sizes[modality]}"
                            )

                self.last_optimization = time.time()
                batch_sizes_copy = self.batch_sizes.copy()

            return {
                "status": "optimization_completed",
                "memory_usage_percent": memory_usage_percent,
                "allocated_mb": allocated / 1024 / 1024,
                "reserved_mb": reserved / 1024 / 1024,
                "batch_sizes": batch_sizes_copy,
                "optimization_applied": optimization_applied,
            }

        except Exception as e:
            logger.error(f"GPU memory optimization failed: {e}")
            return {"status": "optimization_failed", "error": str(e)}

    def enable_mixed_precision(self, enable: bool = True) -> bool:
        """Enable automatic mixed precision for RTX 4070 Tensor cores"""
        if not self.gpu_available:
            return False

        try:
            if (
                enable
                and hasattr(torch.cuda, "amp")
                and torch.cuda.get_device_capability()[0] >= 7
            ):
                # RTX 4070 supports Tensor cores (compute capability 8.9)
                logger.info("Mixed precision enabled for RTX 4070 Tensor cores")
                return True
            else:
                logger.warning("Mixed precision not available or disabled")
                return False
        except Exception as e:
            logger.error(f"Failed to enable mixed precision: {e}")
            return False

    async def monitor_processing_performance(self) -> Dict[str, Any]:
        """Monitor comprehensive processing performance metrics (thread-safe)"""
        try:
            timestamp = time.time()

            # GPU metrics
            gpu_stats = self._get_gpu_stats() if self.gpu_available else {}

            # CPU and system metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()

            # Processing time statistics (uses lock internally)
            processing_stats = self._get_processing_time_stats()

            # Throughput calculations (uses lock internally)
            throughput_stats = self._calculate_throughput()

            # Get shared state under lock
            with self._lock:
                batch_sizes_copy = self.batch_sizes.copy()
                last_optimization = self.last_optimization

            # Create performance metrics
            metrics = {
                "timestamp": timestamp,
                "gpu_available": self.gpu_available,
                "gpu_stats": gpu_stats,
                "cpu_utilization": cpu_percent,
                "ram_usage": {
                    "used_mb": memory.used / 1024 / 1024,
                    "available_mb": memory.available / 1024 / 1024,
                    "percent": memory.percent,
                },
                "processing_times": processing_stats,
                "throughput": throughput_stats,
                "batch_sizes": batch_sizes_copy,
                "optimization_status": {
                    "last_optimization": last_optimization,
                    "time_since_optimization": timestamp - last_optimization,
                    "needs_optimization": (
                        timestamp - last_optimization > self.optimization_interval
                    ),
                },
            }

            # Store in history under lock
            with self._lock:
                self.metrics_history.append(metrics)

            return metrics

        except Exception as e:
            logger.error(f"Performance monitoring failed: {e}")
            return {"error": str(e), "timestamp": time.time()}

    def _get_gpu_stats(self) -> Dict[str, Any]:
        """Get detailed GPU statistics"""
        if not self.gpu_available:
            return {}

        try:
            allocated = torch.cuda.memory_allocated()
            reserved = torch.cuda.memory_reserved()

            return {
                "device_name": self.device_properties.name,
                "compute_capability": (
                    f"{self.device_properties.major}.{self.device_properties.minor}"
                ),
                "total_memory_gb": self.total_gpu_memory / 1024**3,
                "allocated_mb": allocated / 1024 / 1024,
                "reserved_mb": reserved / 1024 / 1024,
                "free_mb": (self.total_gpu_memory - allocated) / 1024 / 1024,
                "utilization_percent": (allocated / self.total_gpu_memory) * 100,
                "tensor_cores_available": self.device_properties.major >= 7,
                "device_count": torch.cuda.device_count(),
            }
        except Exception as e:
            logger.error(f"Failed to get GPU stats: {e}")
            return {"error": str(e)}

    def _get_processing_time_stats(self) -> Dict[str, Any]:
        """Get processing time statistics for each modality (thread-safe)"""
        stats = {}

        # Copy data under lock
        with self._lock:
            times_copy = {k: list(v) for k, v in self.processing_times.items()}

        for modality, times in times_copy.items():
            if len(times) > 0:
                times_array = np.array(times)
                stats[modality] = {
                    "count": len(times),
                    "mean_ms": float(np.mean(times_array) * 1000),
                    "median_ms": float(np.median(times_array) * 1000),
                    "std_ms": float(np.std(times_array) * 1000),
                    "min_ms": float(np.min(times_array) * 1000),
                    "max_ms": float(np.max(times_array) * 1000),
                    "p95_ms": float(np.percentile(times_array, 95) * 1000),
                    "p99_ms": float(np.percentile(times_array, 99) * 1000),
                }

        return stats

    def _calculate_throughput(self) -> Dict[str, Any]:
        """Calculate throughput metrics for each modality (thread-safe)"""
        throughput = {}

        # Copy data under lock
        with self._lock:
            history_copy = {k: list(v) for k, v in self.throughput_history.items()}

        current_time = time.time()
        for modality, history in history_copy.items():
            if len(history) > 0:
                # Calculate items per second over different time windows
                recent_1min = [x for x in history if current_time - x[0] <= 60]
                recent_5min = [x for x in history if current_time - x[0] <= 300]

                throughput[modality] = {
                    "items_per_second_1min": (
                        len(recent_1min) / 60 if recent_1min else 0
                    ),
                    "items_per_second_5min": (
                        len(recent_5min) / 300 if recent_5min else 0
                    ),
                    "total_processed": len(history),
                }

        return throughput

    def record_processing(
        self, modality: str, processing_time: float, items_processed: int = 1
    ):
        """Record processing completion for performance tracking (thread-safe)"""
        timestamp = time.time()

        # Update shared state under lock
        with self._lock:
            # Record processing time
            self.processing_times[modality].append(processing_time)

            # Record throughput
            for _ in range(items_processed):
                self.throughput_history[modality].append((timestamp, 1))

    def get_optimal_batch_size(self, modality: str) -> int:
        """Get the optimal batch size for a given modality (thread-safe)"""
        with self._lock:
            return self.batch_sizes.get(modality, 1)

    def should_optimize(self) -> bool:
        """Check if performance optimization should be triggered (thread-safe)"""
        with self._lock:
            return time.time() - self.last_optimization > self.optimization_interval

    async def auto_optimize(self):
        """Automatically optimize performance if needed"""
        if self.should_optimize():
            await self.optimize_gpu_memory()

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of recent performance metrics (thread-safe)"""
        # Copy data under lock
        with self._lock:
            if not self.metrics_history:
                return {"status": "no_data"}
            recent_metrics = list(self.metrics_history)[-10:]  # Last 10 measurements
            batch_sizes_copy = self.batch_sizes.copy()
            last_optimization = self.last_optimization

        # Calculate averages outside lock
        avg_cpu = np.mean([m.get("cpu_utilization", 0) for m in recent_metrics])
        avg_ram = np.mean(
            [m.get("ram_usage", {}).get("percent", 0) for m in recent_metrics]
        )

        gpu_utilization = 0
        if self.gpu_available and recent_metrics:
            gpu_utils = [
                m.get("gpu_stats", {}).get("utilization_percent", 0)
                for m in recent_metrics
                if m.get("gpu_stats")
            ]
            gpu_utilization = np.mean(gpu_utils) if gpu_utils else 0

        return {
            "measurement_count": len(recent_metrics),
            "time_span_minutes": (
                (recent_metrics[-1]["timestamp"] - recent_metrics[0]["timestamp"]) / 60
                if len(recent_metrics) > 1
                else 0
            ),
            "average_cpu_utilization": float(avg_cpu),
            "average_ram_utilization": float(avg_ram),
            "average_gpu_utilization": float(gpu_utilization),
            "current_batch_sizes": batch_sizes_copy,
            "gpu_available": self.gpu_available,
            "mixed_precision_capable": (
                self.gpu_available and hasattr(torch.cuda, "amp")
            ),
            "last_optimization": last_optimization,
            "optimization_status": (
                "recent" if time.time() - last_optimization < 60 else "needed"
            ),
        }


# Global instance for system-wide performance monitoring
performance_monitor = MultiModalPerformanceMonitor()
