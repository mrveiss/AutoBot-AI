# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Multimodal Processors Package

Contains modal-specific processor implementations.

Part of Issue #381 - God Class Refactoring
"""

from .context import ContextProcessor
from .vision import VISION_MODELS_AVAILABLE, VisionProcessor
from .voice import AUDIO_MODELS_AVAILABLE, VoiceProcessor

__all__ = [
    "VisionProcessor",
    "VoiceProcessor",
    "ContextProcessor",
    "VISION_MODELS_AVAILABLE",
    "AUDIO_MODELS_AVAILABLE",
]
