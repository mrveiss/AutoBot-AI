# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Monitoring Hardware Stub - Placeholder for backward compatibility.

Issue #729: Infrastructure monitoring moved to slm-server.
This module provides stub implementations for local application metrics only.
For infrastructure hardware monitoring, use slm-admin → Monitoring.

Note: This file is kept for backward compatibility with analytics.py and
analytics_controller.py imports. It provides basic local system metrics only.
"""

import logging
import psutil
from typing import Any, Dict

logger = logging.getLogger(__name__)


class HardwareMonitorStub:
    """
    Stub hardware monitor for application-level metrics only.

    Issue #729: Infrastructure monitoring moved to SLM server.
    This stub provides basic local system info for analytics dashboards.
    """

    async def get_system_health(self) -> Dict[str, Any]:
        """Get basic system health metrics (local machine only)."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            return {
                "status": "healthy" if cpu_percent < 90 and memory.percent < 90 else "degraded",
                "cpu_usage": cpu_percent,
                "memory_usage": memory.percent,
                "disk_usage": disk.percent,
                "note": "Local metrics only. Infrastructure monitoring available in SLM Admin.",
            }
        except Exception as e:
            logger.warning("Failed to get system health: %s", e)
            return {
                "status": "unknown",
                "error": str(e),
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
            return {"error": str(e)}

    async def get_gpu_status(self) -> Dict[str, Any]:
        """
        Stub for GPU status - infrastructure monitoring moved to SLM.

        Issue #729: GPU monitoring is now handled by slm-server for infrastructure nodes.
        """
        return {
            "available": False,
            "note": "GPU monitoring moved to SLM Admin. Use slm-admin → Monitoring → Infrastructure.",
        }

    async def get_npu_status(self) -> Dict[str, Any]:
        """
        Stub for NPU status - infrastructure monitoring moved to SLM.

        Issue #729: NPU monitoring is now handled by slm-server for infrastructure nodes.
        """
        return {
            "available": False,
            "note": "NPU monitoring moved to SLM Admin. Use slm-admin → Monitoring → Infrastructure.",
        }


# Global singleton instance for backward compatibility
hardware_monitor = HardwareMonitorStub()
