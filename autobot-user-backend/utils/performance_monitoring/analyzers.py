# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Analyzers Module

Contains classes for analyzing metrics and generating alerts/recommendations:
- AlertAnalyzer: Analyzes metrics and generates performance alerts
- RecommendationGenerator: Generates optimization recommendations

Extracted from performance_monitor.py as part of Issue #381 refactoring.
"""

import logging
import time
from typing import Any, Dict, List

from backend.utils.performance_monitoring.types import (
    CRITICAL_SERVICE_STATUSES,
    DEFAULT_PERFORMANCE_BASELINES,
)

logger = logging.getLogger(__name__)


class AlertAnalyzer:
    """Analyzes performance metrics and generates alerts."""

    def __init__(self, baselines: Dict[str, float] = None):
        """Initialize alert analyzer with performance baselines."""
        self.baselines = baselines or DEFAULT_PERFORMANCE_BASELINES

    def analyze_gpu(self, gpu: Dict, alerts: List[Dict]) -> None:
        """Analyze GPU metrics and generate alerts."""
        if not gpu:
            return

        if gpu["utilization_percent"] < self.baselines["gpu_utilization_target"]:
            alerts.append(
                {
                    "category": "gpu",
                    "severity": "warning",
                    "message": (
                        f"GPU utilization below target: {gpu['utilization_percent']:.1f}% < "
                        f"{self.baselines['gpu_utilization_target']}%"
                    ),
                    "recommendation": "Verify AI workloads are GPU-accelerated",
                    "timestamp": time.time(),
                }
            )

        if gpu.get("thermal_throttling"):
            alerts.append(
                {
                    "category": "gpu",
                    "severity": "critical",
                    "message": f"GPU thermal throttling active at {gpu['temperature_celsius']}°C",
                    "recommendation": "Check cooling and reduce workload",
                    "timestamp": time.time(),
                }
            )

    def analyze_npu(self, npu: Dict, alerts: List[Dict]) -> None:
        """Analyze NPU metrics and generate alerts."""
        if not npu:
            return

        if npu["acceleration_ratio"] < self.baselines["npu_acceleration_target"]:
            alerts.append(
                {
                    "category": "npu",
                    "severity": "warning",
                    "message": (
                        f"NPU acceleration ratio below target: {npu['acceleration_ratio']:.1f}x < "
                        f"{self.baselines['npu_acceleration_target']}x"
                    ),
                    "recommendation": "Optimize NPU utilization or check driver status",
                    "timestamp": time.time(),
                }
            )

    def analyze_system(self, system: Dict, alerts: List[Dict]) -> None:
        """Analyze system metrics and generate alerts."""
        if not system:
            return

        if system["memory_usage_percent"] > self.baselines["memory_usage_warning"]:
            alerts.append(
                {
                    "category": "memory",
                    "severity": "warning",
                    "message": f"High memory usage: {system['memory_usage_percent']:.1f}%",
                    "recommendation": "Enable aggressive cleanup or check for memory leaks",
                    "timestamp": time.time(),
                }
            )

        if system["cpu_load_1m"] > self.baselines["cpu_load_warning"]:
            alerts.append(
                {
                    "category": "cpu",
                    "severity": "warning",
                    "message": (
                        f"High CPU load: {system['cpu_load_1m']:.1f} "
                        f"on {system['cpu_cores_logical']}-core system"
                    ),
                    "recommendation": "Check for CPU-intensive processes",
                    "timestamp": time.time(),
                }
            )

    def analyze_service(self, service: Dict, alerts: List[Dict]) -> None:
        """Analyze service metrics and generate alerts."""
        if not service:
            return

        if service["status"] in CRITICAL_SERVICE_STATUSES:
            alerts.append(
                {
                    "category": "service",
                    "severity": "critical",
                    "message": f"Service {service['service_name']} is {service['status']}",
                    "recommendation": "Check service health and restart if necessary",
                    "timestamp": time.time(),
                }
            )

        if (
            service["response_time_ms"]
            > self.baselines["api_response_time_threshold"]
        ):
            alerts.append(
                {
                    "category": "performance",
                    "severity": "warning",
                    "message": f"{service['service_name']} slow response: {service['response_time_ms']:.0f}ms",
                    "recommendation": "Investigate service performance bottlenecks",
                    "timestamp": time.time(),
                }
            )

    def analyze_all(self, metrics: Dict[str, Any]) -> List[Dict]:
        """Analyze all metrics and generate alerts."""
        alerts = []

        if metrics.get("gpu"):
            self.analyze_gpu(metrics["gpu"], alerts)

        if metrics.get("npu"):
            self.analyze_npu(metrics["npu"], alerts)

        if metrics.get("system"):
            self.analyze_system(metrics["system"], alerts)

        for service in metrics.get("services", []):
            self.analyze_service(service, alerts)

        return alerts


class RecommendationGenerator:
    """Generates performance optimization recommendations."""

    def get_gpu_recommendations(self, latest_gpu) -> List[Dict[str, Any]]:
        """Generate GPU optimization recommendations."""
        recommendations = []
        if not latest_gpu:
            return recommendations

        utilization = getattr(latest_gpu, "utilization_percent", 0)
        memory_util = getattr(latest_gpu, "memory_utilization_percent", 0)

        if utilization < 50:
            recommendations.append(
                {
                    "category": "gpu",
                    "priority": "medium",
                    "recommendation": "GPU underutilized - verify AI workloads use GPU acceleration",
                    "action": "Check CUDA availability and batch sizes in semantic chunking",
                    "expected_improvement": "2-3x performance increase for AI tasks",
                }
            )

        if memory_util > 90:
            recommendations.append(
                {
                    "category": "gpu",
                    "priority": "high",
                    "recommendation": "GPU memory near capacity - optimize memory usage",
                    "action": "Reduce batch sizes or implement gradient checkpointing",
                    "expected_improvement": "Prevent out-of-memory errors",
                }
            )
        return recommendations

    def get_npu_recommendations(self, latest_npu) -> List[Dict[str, Any]]:
        """Generate NPU optimization recommendations."""
        if not latest_npu:
            return []

        acceleration_ratio = getattr(latest_npu, "acceleration_ratio", 0)

        if acceleration_ratio < 3.0:
            return [
                {
                    "category": "npu",
                    "priority": "medium",
                    "recommendation": "NPU acceleration below optimal - check model optimization",
                    "action": "Verify OpenVINO model optimization and NPU driver status",
                    "expected_improvement": "Up to 5x speedup for inference tasks",
                }
            ]
        return []

    def get_system_recommendations(self, latest_system) -> List[Dict[str, Any]]:
        """Generate system/memory optimization recommendations."""
        recommendations = []
        if not latest_system:
            return recommendations

        memory_usage = getattr(latest_system, "memory_usage_percent", 0)
        cpu_load = getattr(latest_system, "cpu_load_1m", 0)

        if memory_usage > 85:
            recommendations.append(
                {
                    "category": "memory",
                    "priority": "high",
                    "recommendation": "High memory usage detected",
                    "action": "Enable aggressive cleanup in chat history and conversation managers",
                    "expected_improvement": "Prevent system slowdown and swapping",
                }
            )

        if cpu_load > 20:  # High for 22-core system
            recommendations.append(
                {
                    "category": "cpu",
                    "priority": "medium",
                    "recommendation": "High CPU load detected",
                    "action": "Optimize parallel processing and check for CPU-intensive tasks",
                    "expected_improvement": "Better system responsiveness",
                }
            )
        return recommendations

    def generate_all(
        self, gpu_metrics=None, npu_metrics=None, system_metrics=None
    ) -> List[Dict[str, Any]]:
        """Generate all optimization recommendations."""
        recommendations = []
        recommendations.extend(self.get_gpu_recommendations(gpu_metrics))
        recommendations.extend(self.get_npu_recommendations(npu_metrics))
        recommendations.extend(self.get_system_recommendations(system_metrics))
        return recommendations
