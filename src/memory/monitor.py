# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Memory Monitor - System memory usage monitoring
"""

import logging
from typing import Any, Dict, Optional

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available - memory monitoring disabled")

logger = logging.getLogger(__name__)


class MemoryMonitor:
    """
    System memory monitoring component

    Responsibility: Monitor system memory usage (requires psutil)
    """

    def __init__(self):
        """Initialize memory monitor with psutil availability check."""
        self.enabled = PSUTIL_AVAILABLE
        if not self.enabled:
            logger.warning("Memory monitoring disabled (psutil not available)")

    def get_usage(self) -> Optional[Dict[str, Any]]:
        """Get current system memory usage"""
        if not self.enabled:
            return None

        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            system_memory = psutil.virtual_memory()

            return {
                "process_rss_mb": memory_info.rss / (1024 * 1024),
                "process_vms_mb": memory_info.vms / (1024 * 1024),
                "system_percent": system_memory.percent,
                "system_available_mb": system_memory.available / (1024 * 1024),
            }
        except Exception as e:
            logger.error("Failed to get memory usage: %s", e)
            return None

    def should_cleanup(self, threshold: float = 0.8) -> bool:
        """Check if cleanup is needed based on memory threshold"""
        if not self.enabled:
            return False

        usage = self.get_usage()
        if usage:
            return usage["system_percent"] > (threshold * 100)

        return False


__all__ = ["MemoryMonitor"]
