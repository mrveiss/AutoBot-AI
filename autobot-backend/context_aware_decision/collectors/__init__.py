# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context Collectors Package

Provides specialized context collectors for the context-aware decision system.

Part of Issue #381 - God Class Refactoring
"""

from .audio import AudioContextCollector
from .main import ContextCollector
from .system import SystemContextCollector
from .visual import VisualContextCollector

__all__ = [
    "VisualContextCollector",
    "AudioContextCollector",
    "SystemContextCollector",
    "ContextCollector",
]
