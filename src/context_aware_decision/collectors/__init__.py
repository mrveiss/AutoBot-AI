# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context Collectors Package

Provides specialized context collectors for the context-aware decision system.

Part of Issue #381 - God Class Refactoring
"""

from .visual import VisualContextCollector
from .audio import AudioContextCollector
from .system import SystemContextCollector
from .main import ContextCollector

__all__ = [
    "VisualContextCollector",
    "AudioContextCollector",
    "SystemContextCollector",
    "ContextCollector",
]
