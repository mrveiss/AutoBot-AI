# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
