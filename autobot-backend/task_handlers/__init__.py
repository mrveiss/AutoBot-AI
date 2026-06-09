# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Task Handler Framework

This module provides a Strategy Pattern-based architecture for handling
different task types in the worker node, reducing deep nesting and improving
maintainability.
"""

from .base import TaskHandler
from .executor import TaskExecutor

__all__ = ["TaskHandler", "TaskExecutor"]
