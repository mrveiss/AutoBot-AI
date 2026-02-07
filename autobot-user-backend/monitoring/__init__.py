# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Monitoring package for AutoBot user backend.

This is a stub package to provide metrics compatibility until full
monitoring integration is completed (Issue #781 fallout).
"""

from .prometheus_metrics import get_metrics_manager

__all__ = ["get_metrics_manager"]
