# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Metrics Recorder

Metrics for GPU/NPU hardware acceleration and performance monitoring.
Created as part of Issue #469 - Prometheus/Grafana consolidation.

Covers:
- GPU metrics (utilization, memory, temperature, power)
- NPU metrics (utilization, acceleration ratio, inference count)
- Performance score and health metrics
- Bottleneck tracking
"""

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class PerformanceMetricsRecorder(BaseMetricsRecorder):
    """Recorder for GPU/NPU performance and hardware acceleration metrics."""

    def _init_metrics(self) -> None:
        """Initialize performance metrics by delegating to category-specific helpers."""
        self._init_gpu_metrics()
        self._init_npu_metrics()
        self._init_npu_worker_metrics()
        self._init_performance_score_metrics()
        self._init_alert_metrics()
        self._init_multimodal_metrics()

    def _init_gpu_metrics(self) -> None:
        """
        Initialize GPU-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.gpu_utilization = Gauge(
            "autobot_gpu_utilization_percent",
            "GPU utilization percentage",
            ["gpu_id", "gpu_name"],
            registry=self.registry,
        )

        self.gpu_memory_utilization = Gauge(
            "autobot_gpu_memory_utilization_percent",
            "GPU memory utilization percentage",
            ["gpu_id", "gpu_name"],
            registry=self.registry,
        )

        self.gpu_temperature = Gauge(
            "autobot_gpu_temperature_celsius",
            "GPU temperature in Celsius",
            ["gpu_id", "gpu_name"],
            registry=self.registry,
        )

        self.gpu_power_watts = Gauge(
            "autobot_gpu_power_watts",
            "GPU power consumption in watts",
            ["gpu_id", "gpu_name"],
            registry=self.registry,
        )

        self.gpu_available = Gauge(
            "autobot_gpu_available",
            "GPU availability (1=available, 0=unavailable)",
            registry=self.registry,
        )

        self.gpu_throttling = Counter(
            "autobot_gpu_throttling_events_total",
            "Total GPU throttling events",
            ["gpu_id", "throttle_type"],  # thermal, power, etc.
            registry=self.registry,
        )

    def _init_npu_metrics(self) -> None:
        """
        Initialize NPU-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.npu_utilization = Gauge(
            "autobot_npu_utilization_percent",
            "NPU utilization percentage",
            registry=self.registry,
        )

        self.npu_acceleration_ratio = Gauge(
            "autobot_npu_acceleration_ratio",
            "NPU acceleration ratio (speedup factor)",
            registry=self.registry,
        )

        self.npu_inference_total = Counter(
            "autobot_npu_inference_total",
            "Total NPU inference operations",
            ["model_type"],
            registry=self.registry,
        )

        self.npu_available = Gauge(
            "autobot_npu_available",
            "NPU availability (1=available, 0=unavailable)",
            registry=self.registry,
        )

        self.npu_wsl_limitation = Gauge(
            "autobot_npu_wsl_limitation",
            "NPU WSL limitation active (1=limited, 0=full support)",
            registry=self.registry,
        )

    def _init_npu_worker_metrics(self) -> None:
        """
        Initialize per-worker NPU metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        Issue #68: Per-worker NPU metrics for distributed NPU processing.
        """
        self.npu_worker_status = Gauge(
            "autobot_npu_worker_status",
            "NPU worker status (1=online, 0=offline)",
            ["worker_id", "platform"],
            registry=self.registry,
        )

        self.npu_worker_load = Gauge(
            "autobot_npu_worker_load",
            "Current load on NPU worker",
            ["worker_id"],
            registry=self.registry,
        )

        self.npu_worker_tasks_completed = Counter(
            "autobot_npu_worker_tasks_completed_total",
            "Total tasks completed by NPU worker",
            ["worker_id"],
            registry=self.registry,
        )

        self.npu_worker_tasks_failed = Counter(
            "autobot_npu_worker_tasks_failed_total",
            "Total tasks failed on NPU worker",
            ["worker_id"],
            registry=self.registry,
        )

        self.npu_worker_uptime = Gauge(
            "autobot_npu_worker_uptime_seconds",
            "NPU worker uptime in seconds",
            ["worker_id"],
            registry=self.registry,
        )

        self.npu_worker_response_time = Histogram(
            "autobot_npu_worker_response_time_seconds",
            "NPU worker response time in seconds",
            ["worker_id"],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=self.registry,
        )

        self.npu_worker_heartbeat_timestamp = Gauge(
            "autobot_npu_worker_last_heartbeat_timestamp",
            "Unix timestamp of last heartbeat from NPU worker",
            ["worker_id"],
            registry=self.registry,
        )

    def _init_performance_score_metrics(self) -> None:
        """
        Initialize performance score and bottleneck metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.performance_score = Gauge(
            "autobot_performance_score",
            "Overall performance score (0-100)",
            registry=self.registry,
        )

        self.health_score = Gauge(
            "autobot_health_score",
            "System health score (0-100)",
            registry=self.registry,
        )

        self.bottleneck_detected = Gauge(
            "autobot_bottleneck_detected",
            "Bottleneck detection status by category",
            ["category"],  # cpu, memory, gpu, network, disk
            registry=self.registry,
        )

        self.optimization_recommendations = Counter(
            "autobot_optimization_recommendations_total",
            "Total optimization recommendations generated",
            ["category", "priority"],  # priority: high, medium, low
            registry=self.registry,
        )

    def _init_alert_metrics(self) -> None:
        """
        Initialize performance alert metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.performance_alerts = Counter(
            "autobot_performance_alerts_total",
            "Total performance alerts generated",
            ["category", "severity"],  # severity: info, warning, critical
            registry=self.registry,
        )

        self.active_alerts = Gauge(
            "autobot_active_alerts_count",
            "Number of currently active alerts",
            ["severity"],
            registry=self.registry,
        )

    def _init_multimodal_metrics(self) -> None:
        """
        Initialize multi-modal processing metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.multimodal_processing_time = Histogram(
            "autobot_multimodal_processing_seconds",
            "Multi-modal processing time in seconds",
            ["modality"],  # vision, audio, text
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry,
        )

        self.multimodal_operations = Counter(
            "autobot_multimodal_operations_total",
            "Total multi-modal operations",
            ["modality", "status"],  # status: success, failure
            registry=self.registry,
        )

    # =========================================================================
    # GPU Methods
    # =========================================================================

    def update_gpu_metrics(
        self,
        gpu_id: str,
        gpu_name: str,
        utilization: float,
        memory_utilization: float,
        temperature: float,
        power_watts: float,
    ) -> None:
        """Update all GPU metrics at once."""
        self.gpu_utilization.labels(gpu_id=gpu_id, gpu_name=gpu_name).set(utilization)
        self.gpu_memory_utilization.labels(gpu_id=gpu_id, gpu_name=gpu_name).set(
            memory_utilization
        )
        self.gpu_temperature.labels(gpu_id=gpu_id, gpu_name=gpu_name).set(temperature)
        self.gpu_power_watts.labels(gpu_id=gpu_id, gpu_name=gpu_name).set(power_watts)

    def set_gpu_available(self, available: bool) -> None:
        """Set GPU availability status."""
        self.gpu_available.set(1 if available else 0)

    def record_gpu_throttling(self, gpu_id: str, throttle_type: str) -> None:
        """Record a GPU throttling event."""
        self.gpu_throttling.labels(gpu_id=gpu_id, throttle_type=throttle_type).inc()

    # =========================================================================
    # NPU Methods
    # =========================================================================

    def update_npu_metrics(
        self,
        utilization: float,
        acceleration_ratio: float,
    ) -> None:
        """Update NPU utilization and acceleration metrics."""
        self.npu_utilization.set(utilization)
        self.npu_acceleration_ratio.set(acceleration_ratio)

    def set_npu_available(self, available: bool) -> None:
        """Set NPU availability status."""
        self.npu_available.set(1 if available else 0)

    def set_npu_wsl_limitation(self, limited: bool) -> None:
        """Set NPU WSL limitation status."""
        self.npu_wsl_limitation.set(1 if limited else 0)

    def record_npu_inference(self, model_type: str) -> None:
        """Record an NPU inference operation."""
        self.npu_inference_total.labels(model_type=model_type).inc()

    # =========================================================================
    # Per-Worker NPU Methods (Issue #68)
    # =========================================================================

    def update_npu_worker_status(
        self,
        worker_id: str,
        platform: str,
        online: bool,
    ) -> None:
        """Update NPU worker status."""
        self.npu_worker_status.labels(worker_id=worker_id, platform=platform).set(
            1 if online else 0
        )

    def update_npu_worker_metrics(
        self,
        worker_id: str,
        current_load: int,
        uptime_seconds: float,
    ) -> None:
        """Update NPU worker load and uptime metrics."""
        self.npu_worker_load.labels(worker_id=worker_id).set(current_load)
        self.npu_worker_uptime.labels(worker_id=worker_id).set(uptime_seconds)

    def record_npu_worker_task_completed(self, worker_id: str) -> None:
        """Record a completed task on NPU worker."""
        self.npu_worker_tasks_completed.labels(worker_id=worker_id).inc()

    def record_npu_worker_task_failed(self, worker_id: str) -> None:
        """Record a failed task on NPU worker."""
        self.npu_worker_tasks_failed.labels(worker_id=worker_id).inc()

    def record_npu_worker_response_time(
        self, worker_id: str, duration_seconds: float
    ) -> None:
        """Record NPU worker response time."""
        self.npu_worker_response_time.labels(worker_id=worker_id).observe(
            duration_seconds
        )

    def update_npu_worker_heartbeat(self, worker_id: str, timestamp: float) -> None:
        """Update last heartbeat timestamp for NPU worker."""
        self.npu_worker_heartbeat_timestamp.labels(worker_id=worker_id).set(timestamp)

    # =========================================================================
    # Performance Score Methods
    # =========================================================================

    def update_performance_score(self, score: float) -> None:
        """Update overall performance score (0-100)."""
        self.performance_score.set(score)

    def update_health_score(self, score: float) -> None:
        """Update system health score (0-100)."""
        self.health_score.set(score)

    def set_bottleneck(self, category: str, detected: bool) -> None:
        """Set bottleneck detection status for a category."""
        self.bottleneck_detected.labels(category=category).set(1 if detected else 0)

    def record_optimization_recommendation(
        self, category: str, priority: str
    ) -> None:
        """Record an optimization recommendation."""
        self.optimization_recommendations.labels(
            category=category, priority=priority
        ).inc()

    # =========================================================================
    # Alert Methods
    # =========================================================================

    def record_performance_alert(self, category: str, severity: str) -> None:
        """Record a performance alert."""
        self.performance_alerts.labels(category=category, severity=severity).inc()

    def update_active_alerts(self, severity: str, count: int) -> None:
        """Update active alert count for a severity level."""
        self.active_alerts.labels(severity=severity).set(count)

    # =========================================================================
    # Multi-modal Methods
    # =========================================================================

    def record_multimodal_processing(
        self, modality: str, duration_seconds: float, success: bool
    ) -> None:
        """Record a multi-modal processing operation."""
        self.multimodal_processing_time.labels(modality=modality).observe(
            duration_seconds
        )
        status = "success" if success else "failure"
        self.multimodal_operations.labels(modality=modality, status=status).inc()


__all__ = ["PerformanceMetricsRecorder"]
