# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Monitoring package for AutoBot user backend.

This is a stub package to provide metrics compatibility until full
monitoring integration is completed (Issue #781 fallout).
"""

from .prometheus_metrics import get_metrics_manager

__all__ = ["get_metrics_manager"]
