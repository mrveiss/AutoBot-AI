# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hardware Monitor - GPU/NPU/System Status Compatibility Layer.

This module provides hardware monitoring compatibility for analytics integration.
Extracted from monitoring.py for better maintainability (Issue #185, #213).

Classes:
- HardwareMonitor: Compatibility layer for hardware status reporting

Related Issues: #185 (Split), #213 (API file split)
"""

import logging
import time

from src.utils.performance_monitor import get_phase9_performance_dashboard

logger = logging.getLogger(__name__)


class HardwareMonitor:
    """Hardware monitor compatibility layer for analytics integration"""

    @staticmethod
    def get_gpu_status():
        """Get GPU status for analytics"""
        try:
            dashboard = get_phase9_performance_dashboard()
            gpu_data = dashboard.get("gpu", {})

            return {
                "available": (
                    dashboard.get("hardware_acceleration", {}).get(
                        "gpu_available", False
                    )
                ),
                "utilization_percent": gpu_data.get("utilization_percent", 0),
                "memory_used_mb": gpu_data.get("memory_used_mb", 0),
                "memory_total_mb": gpu_data.get("memory_total_mb", 0),
                "temperature_celsius": gpu_data.get("temperature_celsius", 0),
                "status": (
                    "healthy" if gpu_data.get("utilization_percent", 0) > 0 else "idle"
                ),
            }
        except Exception as e:
            logger.error(f"Error getting GPU status: {e}")
            return {"available": False, "status": "error", "error": str(e)}

    @staticmethod
    def get_npu_status():
        """Get NPU status for analytics"""
        try:
            dashboard = get_phase9_performance_dashboard()
            npu_data = dashboard.get("npu", {})

            return {
                "available": (
                    dashboard.get("hardware_acceleration", {}).get(
                        "npu_available", False
                    )
                ),
                "utilization_percent": npu_data.get("utilization_percent", 0),
                "acceleration_ratio": npu_data.get("acceleration_ratio", 0),
                "inference_count": npu_data.get("inference_count", 0),
                "status": (
                    "healthy" if npu_data.get("utilization_percent", 0) > 0 else "idle"
                ),
            }
        except Exception as e:
            logger.error(f"Error getting NPU status: {e}")
            return {"available": False, "status": "error", "error": str(e)}

    @staticmethod
    async def get_system_health():
        """Get system health for analytics"""
        try:
            dashboard = get_phase9_performance_dashboard()
            system_data = dashboard.get("system", {})

            return {
                "status": "healthy",
                "cpu_usage_percent": system_data.get("cpu_usage_percent", 0),
                "memory_usage_percent": system_data.get("memory_usage_percent", 0),
                "disk_usage_percent": system_data.get("disk_usage_percent", 0),
                "load_average": system_data.get("cpu_load_1m", 0),
                "uptime_hours": 24,  # Placeholder
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return {"status": "error", "error": str(e)}

    @staticmethod
    def get_system_resources():
        """Get system resources for analytics"""
        try:
            dashboard = get_phase9_performance_dashboard()
            system_data = dashboard.get("system", {})

            return {
                "cpu": {
                    "usage_percent": system_data.get("cpu_usage_percent", 0),
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
                    "usage_percent": system_data.get("memory_usage_percent", 0),
                },
                "disk": {
                    "usage_percent": system_data.get("disk_usage_percent", 0),
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
            logger.error(f"Error getting system resources: {e}")
            return {"error": str(e)}


# Create global hardware monitor instance for import compatibility
hardware_monitor = HardwareMonitor()
