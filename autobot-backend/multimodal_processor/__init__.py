# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Multimodal Processor Package

Unified multi-modal AI processing with vision, voice, and context modalities.
Features GPU-accelerated models (CLIP, BLIP-2, Whisper, Wav2Vec2) and
attention-based cross-modal fusion.

Part of Issue #381 - God Class Refactoring

Original module: 1,512 lines
New package: ~1,100 lines across focused modules

Usage:
    from multimodal_processor import (
        UnifiedMultiModalProcessor,
        ModalityType,
        ProcessingIntent,
        MultiModalInput,
        ProcessingResult,
        unified_processor,  # Singleton instance
    )

    # Use singleton
    result = await unified_processor.process(input_data)

    # Or create custom instance
    processor = UnifiedMultiModalProcessor()
    result = await processor.process(input_data)
"""

import threading
from typing import Any, Optional

# Base class
from .base import BaseModalProcessor

# Data models
from .models import MultiModalInput, ProcessingResult

# Main processor
from .processor import UnifiedMultiModalProcessor

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


class _LazyUnifiedProcessor:
    """Lazy proxy for UnifiedMultiModalProcessor.

    Defers model loading (CLIP, BLIP-2, Whisper, Wav2Vec2) until first use
    to prevent 5-6 minute startup delays. Issue #940.

    Thread-safe via double-checked locking.
    """

    _instance: Optional["UnifiedMultiModalProcessor"] = None  # noqa: F821
    _lock = threading.Lock()

    def _get_instance(self) -> "UnifiedMultiModalProcessor":  # noqa: F821
        """Return the real processor, creating it on first call."""
        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self.__class__._instance = UnifiedMultiModalProcessor()
        return self._instance  # type: ignore[return-value]

    def __getattr__(self, name: str) -> Any:
        """Delegate all attribute access to the underlying processor."""
        return getattr(self._get_instance(), name)

    def __bool__(self) -> bool:
        """Always truthy — proxy exists even before models are loaded."""
        return True


# Singleton instance — lazy-loaded on first attribute access (Issue #940)
unified_processor = _LazyUnifiedProcessor()

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
    # Main processor
    "UnifiedMultiModalProcessor",
    # Singleton
    "unified_processor",
]
