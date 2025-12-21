# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hardware Monitor - GPU/NPU/System Status Compatibility Layer.

This module provides hardware monitoring compatibility for analytics integration.
Extracted from monitoring.py for better maintainability (Issue #185, #213).

Classes:
- HardwareMonitor: Compatibility layer for hardware status reporting

Related Issues:
- #185 (Split)
- #213 (API file split)
- #471 (Prometheus metrics integration)
"""

import logging
import time

from src.monitoring.prometheus_metrics import get_metrics_manager
from src.utils.performance_monitor import get_phase9_performance_dashboard

logger = logging.getLogger(__name__)

# Issue #471: Get metrics manager for Prometheus integration
_metrics = get_metrics_manager()


class HardwareMonitor:
    """Hardware monitor compatibility layer for analytics integration"""

    @staticmethod
    def get_gpu_status():
        """Get GPU status for analytics.

        Issue #471: Now also emits Prometheus metrics for GPU status.
        """
        try:
            dashboard = get_phase9_performance_dashboard()
            gpu_data = dashboard.get("gpu", {})
            hw_accel = dashboard.get("hardware_acceleration", {})

            available = hw_accel.get("gpu_available", False)
            utilization = gpu_data.get("utilization_percent", 0)
            memory_utilization = gpu_data.get("memory_utilization_percent", 0)
            temperature = gpu_data.get("temperature_celsius", 0)
            power_watts = gpu_data.get("power_watts", 0)

            # Issue #471: Emit Prometheus metrics
            _metrics.set_gpu_available(available)
            if available:
                _metrics.update_gpu_metrics(
                    gpu_id="0",
                    gpu_name=gpu_data.get("name", "Unknown GPU"),
                    utilization=utilization,
                    memory_utilization=memory_utilization,
                    temperature=temperature,
                    power_watts=power_watts,
                )

            return {
                "available": available,
                "utilization_percent": utilization,
                "memory_used_mb": gpu_data.get("memory_used_mb", 0),
                "memory_total_mb": gpu_data.get("memory_total_mb", 0),
                "temperature_celsius": temperature,
                "status": "healthy" if utilization > 0 else "idle",
            }
        except Exception as e:
            logger.error("Error getting GPU status: %s", e)
            _metrics.set_gpu_available(False)
            return {"available": False, "status": "error", "error": str(e)}

    @staticmethod
    def get_npu_status():
        """Get NPU status for analytics.

        Issue #471: Now also emits Prometheus metrics for NPU status.
        """
        try:
            dashboard = get_phase9_performance_dashboard()
            npu_data = dashboard.get("npu", {})
            hw_accel = dashboard.get("hardware_acceleration", {})

            available = hw_accel.get("npu_available", False)
            utilization = npu_data.get("utilization_percent", 0)
            acceleration_ratio = npu_data.get("acceleration_ratio", 0)
            wsl_limited = npu_data.get("wsl_limitation", False)

            # Issue #471: Emit Prometheus metrics
            _metrics.set_npu_available(available)
            _metrics.set_npu_wsl_limitation(wsl_limited)
            if available:
                _metrics.update_npu_metrics(utilization, acceleration_ratio)

            return {
                "available": available,
                "utilization_percent": utilization,
                "acceleration_ratio": acceleration_ratio,
                "inference_count": npu_data.get("inference_count", 0),
                "status": "healthy" if utilization > 0 else "idle",
            }
        except Exception as e:
            logger.error("Error getting NPU status: %s", e)
            _metrics.set_npu_available(False)
            return {"available": False, "status": "error", "error": str(e)}

    @staticmethod
    async def get_system_health():
        """Get system health for analytics.

        Issue #471: Now also emits Prometheus metrics for system health.
        """
        try:
            dashboard = get_phase9_performance_dashboard()
            system_data = dashboard.get("system", {})

            cpu_usage = system_data.get("cpu_usage_percent", 0)
            memory_usage = system_data.get("memory_usage_percent", 0)
            disk_usage = system_data.get("disk_usage_percent", 0)

            # Issue #471: Emit Prometheus metrics
            _metrics.update_system_cpu(cpu_usage)
            _metrics.update_system_memory(memory_usage)
            _metrics.update_system_disk("/", disk_usage)

            return {
                "status": "healthy",
                "cpu_usage_percent": cpu_usage,
                "memory_usage_percent": memory_usage,
                "disk_usage_percent": disk_usage,
                "load_average": system_data.get("cpu_load_1m", 0),
                "uptime_hours": 24,  # Placeholder
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error("Error getting system health: %s", e)
            return {"status": "error", "error": str(e)}

    @staticmethod
    def get_system_resources():
        """Get system resources for analytics.

        Issue #471: Now also emits Prometheus metrics for system resources.
        """
        try:
            dashboard = get_phase9_performance_dashboard()
            system_data = dashboard.get("system", {})

            cpu_usage = system_data.get("cpu_usage_percent", 0)
            memory_usage = system_data.get("memory_usage_percent", 0)
            disk_usage = system_data.get("disk_usage_percent", 0)

            # Issue #471: Emit Prometheus metrics
            _metrics.update_system_cpu(cpu_usage)
            _metrics.update_system_memory(memory_usage)
            _metrics.update_system_disk("/", disk_usage)

            return {
                "cpu": {
                    "usage_percent": cpu_usage,
                    "cores_physical": system_data.get("cpu_cores_physical", 0),
                    "cores_logical": system_data.get("cpu_cores_logical", 0),
                    "frequency_mhz": system_data.get("cpu_frequency_mhz", 0),
                    "load_1m": system_data.get("cpu_load_1m", 0),
                    "load_5m": system_data.get("cpu_load_5m", 0),
                    "load_15m": system_data.get("cpu_load_15m", 0),
                },
                "memory": {
                    "total_gb": system_data.get("memory_total_gb", 0),
                    "used_gb": system_data.get("memory_used_gb", 0),
                    "available_gb": system_data.get("memory_available_gb", 0),
                    "usage_percent": memory_usage,
                },
                "disk": {
                    "usage_percent": disk_usage,
                    "read_mb_s": system_data.get("disk_read_mb_s", 0),
                    "write_mb_s": system_data.get("disk_write_mb_s", 0),
                },
                "network": {
                    "upload_mb_s": system_data.get("network_upload_mb_s", 0),
                    "download_mb_s": system_data.get("network_download_mb_s", 0),
                    "latency_ms": system_data.get("network_latency_ms", 0),
                },
            }
        except Exception as e:
            logger.error("Error getting system resources: %s", e)
            return {"error": str(e)}


# Create global hardware monitor instance for import compatibility
hardware_monitor = HardwareMonitor()
