# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Multimodal Processor Package

Multi-modal AI processing with vision, voice, and context modalities.
Features GPU-accelerated models (CLIP, BLIP-2, Whisper, Wav2Vec2) and
attention-based cross-modal fusion.

Part of Issue #381 - God Class Refactoring
Part of Issue #10666 - Naming consolidation (prefix strip)

Original module: 1,512 lines
New package: ~1,100 lines across focused modules

Usage:
    from multimodal_processor import (
        MultiModalProcessor,
        ModalityType,
        ProcessingIntent,
        MultiModalInput,
        ProcessingResult,
        unified_processor,  # Singleton instance
    )

    # Use singleton
    result = await unified_processor.process(input_data)

    # Or create custom instance
    processor = MultiModalProcessor()
    result = await processor.process(input_data)
"""

from __future__ import annotations

import threading
from typing import Any

# Base class
from .base import BaseModalProcessor

# Data models
from .models import MultiModalInput, ProcessingResult

# Main processor (Issue #10666 — prefix strip)
from .processor import MultiModalProcessor

# Processors
from .processors import (
    AUDIO_MODELS_AVAILABLE,
    VISION_MODELS_AVAILABLE,
    ContextProcessor,
    VisionProcessor,
    VoiceProcessor,
)

# Types and constants
from .types import (
    CLOSE_COMMAND_WORDS,
    EMBEDDING_FIELDS,
    INTERACTION_COMMAND_WORDS,
    LAUNCH_COMMAND_WORDS,
    MEDIA_CONTROL_COMMAND_WORDS,
    NAVIGATION_COMMAND_WORDS,
    QUERY_COMMAND_WORDS,
    SEARCH_COMMAND_WORDS,
    TEXT_INPUT_COMMAND_WORDS,
    VISUAL_MODALITY_TYPES,
    ConfidenceLevel,
    ModalityType,
    ProcessingIntent,
)

# Backward compatibility: module-level constant alias (Issue #380)
_EMBEDDING_FIELDS = EMBEDDING_FIELDS


class _LazyProcessor:
    """Lazy proxy for MultiModalProcessor.

    Defers model loading (CLIP, BLIP-2, Whisper, Wav2Vec2) until first use
    to prevent 5-6 minute startup delays. Issue #940.

    Thread-safe via double-checked locking.
    """

    _instance: "MultiModalProcessor" | None = None
    _lock = threading.Lock()

    def _get_instance(self) -> "MultiModalProcessor":
        """Return the real processor, creating it on first call."""
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self.__class__._instance = MultiModalProcessor()
        return self._instance  # type: ignore[return-value]

    def __getattr__(self, name: str) -> Any:
        """Delegate all attribute access to the underlying processor."""
        return getattr(self._get_instance(), name)

    def __bool__(self) -> bool:
        """Always truthy — proxy exists even before models are loaded."""
        return True


# Singleton instance — lazy-loaded on first attribute access (Issue #940)
unified_processor = _LazyProcessor()

# ---------------------------------------------------------------------------
# Backward-compatibility shim (previously in multimodal_processor.py — Issue #3554)
# The root-level .py file was shadowed by this package; its contents are
# merged here so existing importers continue to work without changes.
# ---------------------------------------------------------------------------

# Alias for old callers that used ModalInput instead of MultiModalInput
ModalInput = MultiModalInput

# Global instance for backward compatibility (Issue #3554)
multimodal_processor = unified_processor

__all__ = [
    # Types and enums
    "ModalityType",
    "ProcessingIntent",
    "ConfidenceLevel",
    # Command word constants
    "LAUNCH_COMMAND_WORDS",
    "CLOSE_COMMAND_WORDS",
    "SEARCH_COMMAND_WORDS",
    "TEXT_INPUT_COMMAND_WORDS",
    "INTERACTION_COMMAND_WORDS",
    "NAVIGATION_COMMAND_WORDS",
    "MEDIA_CONTROL_COMMAND_WORDS",
    "QUERY_COMMAND_WORDS",
    "VISUAL_MODALITY_TYPES",
    "EMBEDDING_FIELDS",
    "_EMBEDDING_FIELDS",  # Backward compatibility
    # Models
    "MultiModalInput",
    "ProcessingResult",
    # Base class
    "BaseModalProcessor",
    # Processors
    "VisionProcessor",
    "VoiceProcessor",
    "ContextProcessor",
    "VISION_MODELS_AVAILABLE",
    "AUDIO_MODELS_AVAILABLE",
    # Main processor (Issue #10666 — prefix strip)
    "MultiModalProcessor",
    # Singletons
    "unified_processor",
    # Backward-compatibility shim (Issue #3554)
    "ModalInput",
    "multimodal_processor",
]
