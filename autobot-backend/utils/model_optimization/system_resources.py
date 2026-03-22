# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
System Resources Module

Issue #381: Extracted from model_optimizer.py god class refactoring.
Contains system resource analysis for model selection.
"""

import logging

import psutil

from .types import SystemResources

logger = logging.getLogger(__name__)


class SystemResourceAnalyzer:
    """Analyzes system resources for model selection (Tell Don't Ask)."""

    def __init__(self, logger_instance=None):
        """Initialize analyzer with logger for error reporting."""
        self._logger = logger_instance or logger

    def get_current_resources(self) -> SystemResources:
        """Get current system resource state including GPU VRAM (#1966)."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            gpu_vram = self._get_gpu_vram()

            return SystemResources(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                available_memory_gb=memory.available / (1024**3),
                gpu_vram_gb=gpu_vram,
            )
        except Exception as e:
            self._logger.error("Error getting system resources: %s", e)
            return SystemResources(
                cpu_percent=50.0,
                memory_percent=50.0,
                available_memory_gb=8.0,
                gpu_vram_gb=0.0,
            )

    def _get_gpu_vram(self) -> float:
        """Query available GPU VRAM in GB. Returns 0.0 if unavailable (#1966)."""
        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            pynvml.nvmlShutdown()
            return mem_info.free / (1024**3)
        except Exception:
            pass
        return 0.0
