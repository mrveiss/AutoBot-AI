# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Monitoring utility functions for performance calculations and analysis.

This module contains helper functions extracted from monitoring.py (Issue #185).
"""

import csv
import io
import logging
from typing import Dict, List

from backend.type_defs.common import Metadata

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for critical service statuses (Issue #326)
CRITICAL_SERVICE_STATUSES = {"critical", "offline"}


def _calculate_overall_health(dashboard: Metadata) -> str:
    """Calculate overall system health based on dashboard data"""
    try:
        health_factors = []

        # GPU health
        if dashboard.get("gpu"):
            gpu = dashboard["gpu"]
            if gpu.get("thermal_throttling") or gpu.get("power_throttling"):
                health_factors.append("critical")
            elif gpu.get("utilization_percent", 0) < 20:
                health_factors.append("warning")
            else:
                health_factors.append("healthy")

        # System health
        if dashboard.get("system"):
            system = dashboard["system"]
            if system.get("memory_usage_percent", 0) > 90:
                health_factors.append("critical")
            elif system.get("cpu_load_1m", 0) > 20:
                health_factors.append("warning")
            else:
                health_factors.append("healthy")

        # Service health
        if dashboard.get("services"):
            critical_services = any(
                service.get("status") in CRITICAL_SERVICE_STATUSES
                for service in dashboard["services"].values()
            )
            if critical_services:
                health_factors.append("critical")
            else:
                health_factors.append("healthy")

        # Overall assessment
        if "critical" in health_factors:
            return "critical"
        elif "warning" in health_factors:
            return "warning"
        else:
            return "healthy"

    except Exception:
        return "unknown"


def _calculate_performance_score(dashboard: Metadata) -> float:
    """Calculate overall performance score (0-100)"""
    try:
        scores = []

        # GPU performance score
        if dashboard.get("gpu"):
            gpu = dashboard["gpu"]
            gpu_score = min(
                100, gpu.get("utilization_percent", 0) * 1.25
            )  # Favor high utilization
            if gpu.get("thermal_throttling"):
                gpu_score *= 0.5
            scores.append(gpu_score)

        # NPU performance score
        if dashboard.get("npu"):
            npu = dashboard["npu"]
            npu_score = min(
                100, npu.get("acceleration_ratio", 0) * 20
            )  # Target 5x = 100%
            scores.append(npu_score)

        # System performance score
        if dashboard.get("system"):
            system = dashboard["system"]
            cpu_score = max(
                0, 100 - system.get("cpu_load_1m", 0) * 5
            )  # Penalize high load
            memory_score = max(0, 100 - system.get("memory_usage_percent", 0))
            system_score = (cpu_score + memory_score) / 2
            scores.append(system_score)

        return round(sum(scores) / len(scores), 1) if scores else 0.0

    except Exception:
        return 0.0


def _identify_bottlenecks(dashboard: Metadata) -> List[str]:
    """Identify system bottlenecks"""
    bottlenecks = []

    try:
        # GPU bottlenecks
        if dashboard.get("gpu"):
            gpu = dashboard["gpu"]
            if gpu.get("memory_utilization_percent", 0) > 95:
                bottlenecks.append("GPU memory saturation")
            if gpu.get("thermal_throttling"):
                bottlenecks.append("GPU thermal throttling")

        # System bottlenecks
        if dashboard.get("system"):
            system = dashboard["system"]
            if system.get("memory_usage_percent", 0) > 90:
                bottlenecks.append("System memory pressure")
            if system.get("cpu_load_1m", 0) > 20:
                bottlenecks.append("High CPU load")
            if system.get("network_latency_ms", 0) > 100:
                bottlenecks.append("Network latency")

        # Service bottlenecks
        if dashboard.get("services"):
            slow_services = [
                name
                for name, service in dashboard["services"].items()
                if service.get("response_time_ms", 0) > 500
            ]
            if slow_services:
                bottlenecks.append(f"Slow services: {', '.join(slow_services)}")

    except Exception as e:
        logger.debug("Dashboard analysis error: %s", e)

    return bottlenecks


def _analyze_resource_utilization(dashboard: Metadata) -> Dict[str, float]:
    """Analyze resource utilization efficiency"""
    utilization = {}

    try:
        if dashboard.get("gpu"):
            utilization["gpu"] = dashboard["gpu"].get("utilization_percent", 0)

        if dashboard.get("npu"):
            utilization["npu"] = dashboard["npu"].get("utilization_percent", 0)

        if dashboard.get("system"):
            utilization["cpu"] = dashboard["system"].get("cpu_usage_percent", 0)
            utilization["memory"] = dashboard["system"].get("memory_usage_percent", 0)

    except Exception as e:
        logger.debug("Metric extraction error: %s", e)

    return utilization


def _calculate_gpu_efficiency(gpu_metrics) -> float:
    """Calculate GPU efficiency score"""
    try:
        utilization = gpu_metrics.utilization_percent
        memory_util = gpu_metrics.memory_utilization_percent

        # Efficiency based on balanced utilization
        efficiency = (utilization + memory_util) / 2

        # Penalize for throttling
        if gpu_metrics.thermal_throttling:
            efficiency *= 0.7
        if gpu_metrics.power_throttling:
            efficiency *= 0.8

        return round(efficiency, 1)

    except Exception:
        return 0.0


def _calculate_npu_efficiency(npu_metrics) -> float:
    """Calculate NPU efficiency score"""
    try:
        # Base efficiency on acceleration ratio
        efficiency = min(100, npu_metrics.acceleration_ratio * 20)  # 5x = 100%

        # Adjust for thermal state
        if npu_metrics.thermal_state == "throttling":
            efficiency *= 0.7
        elif npu_metrics.thermal_state == "critical":
            efficiency *= 0.5

        return round(efficiency, 1)

    except Exception:
        return 0.0


def _convert_metrics_to_csv(data: Metadata) -> str:
    """Convert metrics data to CSV format"""
    try:
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["timestamp", "category", "metric", "value", "unit"])

        # Write GPU metrics
        for metric in data.get("gpu_metrics", []):
            timestamp = metric["timestamp"]
            for key, value in metric.items():
                if key != "timestamp":
                    writer.writerow([timestamp, "gpu", key, value, ""])

        # Write NPU metrics
        for metric in data.get("npu_metrics", []):
            timestamp = metric["timestamp"]
            for key, value in metric.items():
                if key != "timestamp":
                    writer.writerow([timestamp, "npu", key, value, ""])

        # Write system metrics
        for metric in data.get("system_metrics", []):
            timestamp = metric["timestamp"]
            for key, value in metric.items():
                if key != "timestamp":
                    writer.writerow([timestamp, "system", key, value, ""])

        return output.getvalue()

    except Exception as e:
        logger.error("Error converting to CSV: %s", e)
        return "Error generating CSV"
