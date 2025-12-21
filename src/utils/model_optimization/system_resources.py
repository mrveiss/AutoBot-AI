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
        """Get current system resource state."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()

            return SystemResources(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                available_memory_gb=memory.available / (1024**3),
            )
        except Exception as e:
            self._logger.error("Error getting system resources: %s", e)
            # Conservative defaults
            return SystemResources(
                cpu_percent=50.0, memory_percent=50.0, available_memory_gb=8.0
            )
