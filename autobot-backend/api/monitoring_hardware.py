# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Monitoring Hardware - Local hardware detection for analytics dashboards.

Issue #729: Infrastructure monitoring moved to slm-server.
Issue #10717: Replace static stubs with real local GPU/NPU detection.

GPU and NPU status are detected on the local machine using the existing
HardwareAccelerationManager (hardware_acceleration.py), which probes
nvidia-smi/rocm-smi/lspci for GPU and OpenVINO/lspci/device-files for NPU.
Detection runs in a thread pool to avoid blocking the async event loop.

For fleet-wide infrastructure monitoring, use SLM Admin → Monitoring.
"""

import asyncio
from typing import Any, Dict

import psutil

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _detect_gpu_sync() -> Dict[str, Any]:
    """Run GPU detection synchronously (called via asyncio.to_thread).

    Reuses HardwareAccelerationManager which already handles NVIDIA/AMD/Intel
    detection with graceful fallback on each tool being absent.
    """
    try:
        from hardware_acceleration import AccelerationType, get_hardware_acceleration_manager

        mgr = get_hardware_acceleration_manager()
        if mgr.gpu_available:
            info = mgr.available_devices.get(AccelerationType.GPU) or mgr._get_gpu_info()
            return {
                "available": True,
                "vendor": info.get("vendor", "Unknown"),
                "devices": info.get("devices", []),
            }
        return {"available": False}
    except Exception as exc:
        logger.warning("GPU detection error: %s", exc)
        return {"available": False, "error": "Detection failed"}


def _detect_npu_sync() -> Dict[str, Any]:
    """Run NPU detection synchronously (called via asyncio.to_thread).

    Reuses HardwareAccelerationManager which checks /dev/intel_npu*, lspci,
    and OpenVINO device enumeration.
    """
    try:
        from hardware_acceleration import AccelerationType, get_hardware_acceleration_manager

        mgr = get_hardware_acceleration_manager()
        if mgr.npu_available:
            info = mgr.available_devices.get(AccelerationType.NPU) or mgr._get_npu_info()
            return {
                "available": True,
                "devices": info.get("devices", []),
                "openvino_support": info.get("openvino_support", False),
            }
        return {"available": False}
    except Exception as exc:
        logger.warning("NPU detection error: %s", exc)
        return {"available": False, "error": "Detection failed"}


class HardwareMonitorStub:
    """
    Hardware monitor providing local GPU/NPU detection for analytics dashboards.

    Issue #729: Fleet infrastructure monitoring lives in the SLM server.
    Issue #10717: get_gpu_status / get_npu_status now detect real local hardware
    via HardwareAccelerationManager instead of returning a hardcoded stub.
    """

    async def get_system_health(self) -> Dict[str, Any]:
        """Get basic system health metrics (local machine only)."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return {
                "status": ("healthy" if cpu_percent < 90 and memory.percent < 90 else "degraded"),
                "cpu_usage": cpu_percent,
                "memory_usage": memory.percent,
                "disk_usage": disk.percent,
                "note": "Local metrics only. Infrastructure monitoring available in SLM Admin.",
            }
        except Exception as e:
            logger.warning("Failed to get system health: %s", e)
            return {
                "status": "unknown",
                "error": "Internal server error",
                "note": "Infrastructure monitoring available in SLM Admin.",
            }

    async def get_system_resources(self) -> Dict[str, Any]:
        """Get basic system resource metrics (local machine only)."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return {
                "cpu": {
                    "usage_percent": cpu_percent,
                    "cores": psutil.cpu_count(),
                },
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "used": memory.used,
                    "percent": memory.percent,
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent,
                },
                "note": "Local metrics only. Infrastructure monitoring available in SLM Admin.",
            }
        except Exception as e:
            logger.warning("Failed to get system resources: %s", e)
            return {"error": "Internal server error"}

    async def get_gpu_status(self) -> Dict[str, Any]:
        """Detect local GPU availability via HardwareAccelerationManager (#10717).

        Returns real detection results (available, vendor, devices) when a GPU
        is found via nvidia-smi, rocm-smi, or lspci. Falls back to
        available=False on any error — never raises.
        """
        try:
            return await asyncio.to_thread(_detect_gpu_sync)
        except Exception as exc:
            logger.warning("GPU status detection failed: %s", exc)
            return {"available": False, "error": "Detection failed"}

    async def get_npu_status(self) -> Dict[str, Any]:
        """Detect local NPU availability via HardwareAccelerationManager (#10717).

        Returns real detection results (available, devices, openvino_support)
        when an Intel NPU is found via /dev, lspci, or OpenVINO. Falls back to
        available=False on any error — never raises.
        """
        try:
            return await asyncio.to_thread(_detect_npu_sync)
        except Exception as exc:
            logger.warning("NPU status detection failed: %s", exc)
            return {"available": False, "error": "Detection failed"}


# Global singleton instance for backward compatibility
hardware_monitor = HardwareMonitorStub()
