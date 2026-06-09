# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
System Resources Module

Issue #381: Extracted from model_optimizer.py god class refactoring.
Contains system resource analysis for model selection.
Issue #2032: Multi-GPU VRAM detection — sums free VRAM across all GPUs.
"""

from typing import List, Tuple

import psutil

from autobot_shared.logging_manager import get_logger

from .types import SystemResources

logger = get_logger(__name__)


class SystemResourceAnalyzer:
    """Analyzes system resources for model selection (Tell Don't Ask)."""

    def __init__(self, logger_instance=None):
        """Initialize analyzer with logger for error reporting."""
        self._logger = logger_instance or logger

    def get_current_resources(self) -> SystemResources:
        """Get current system resource state including GPU VRAM (#1966, #2032)."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            total_vram_gb, per_gpu_vram_gb = self._get_gpu_vram_all()

            return SystemResources(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                available_memory_gb=memory.available / (1024**3),
                gpu_vram_gb=total_vram_gb,
                per_gpu_vram_gb=per_gpu_vram_gb,
            )
        except Exception as e:
            self._logger.error("Error getting system resources: %s", e)
            return SystemResources(
                cpu_percent=50.0,
                memory_percent=50.0,
                available_memory_gb=8.0,
                gpu_vram_gb=0.0,
                per_gpu_vram_gb=[],
            )

    def _get_gpu_vram_all(self) -> Tuple[float, List[float]]:
        """Query free VRAM across all GPUs (#2032).

        Returns a tuple of (total_free_gb, per_gpu_free_gb_list).
        Both values are 0.0 / [] when pynvml is unavailable or no GPU is found.
        """
        try:
            import pynvml

            pynvml.nvmlInit()
            try:
                device_count = pynvml.nvmlDeviceGetCount()
                if device_count == 0:
                    self._logger.debug("pynvml: no GPUs detected")
                    return 0.0, []

                per_gpu: List[float] = []
                for idx in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    free_gb = mem_info.free / (1024**3)
                    per_gpu.append(free_gb)
                    self._logger.debug("GPU %d free VRAM: %.2f GB", idx, free_gb)

                total = sum(per_gpu)
                self._logger.debug("Total free VRAM across %d GPU(s): %.2f GB", device_count, total)
                return total, per_gpu
            finally:
                pynvml.nvmlShutdown()
        except Exception as exc:
            self._logger.debug("pynvml unavailable or error querying VRAM: %s", exc)
        return 0.0, []
