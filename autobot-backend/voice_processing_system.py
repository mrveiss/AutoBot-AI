# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Processing System Facade - Backward compatibility layer.

This module provides backward compatibility for existing imports while
delegating to the refactored voice_processing package.

Refactored as part of Issue #381 god class refactoring.
Original: 1,257 lines → Facade: ~80 lines (94% reduction)

For new code, import directly from voice_processing:
    from voice_processing import VoiceProcessingSystem, VoiceCommand, AudioInput
"""

# Re-export everything from the refactored package
from voice_processing import (  # Types; Models; Constants; Engines; Main system
    APP_PATTERNS_RE,
    AUTOMATION_INTENT_PATTERNS,
    CONTEXT_DEPENDENT_INTENTS,
    DIRECTION_RE,
    HIGH_RISK_COMMAND_TYPES,
    HIGH_RISK_INTENTS,
    NAVIGATION_INTENT_PATTERNS,
    NUMBER_RE,
    QUERY_INTENT_PATTERNS,
    QUOTED_TEXT_RE,
    SCREEN_STATE_INTENTS,
    URL_RE,
    AudioInput,
    NaturalLanguageProcessor,
    SpeechQuality,
    SpeechRecognitionEngine,
    SpeechRecognitionResult,
    SpeechSynthesisRequest,
    TextToSpeechEngine,
    VoiceCommand,
    VoiceCommandAnalysis,
    VoiceProcessingSystem,
    match_intent_from_patterns,
)

# Backward compatibility aliases for private constant names
_AUTOMATION_INTENT_PATTERNS = AUTOMATION_INTENT_PATTERNS
_NAVIGATION_INTENT_PATTERNS = NAVIGATION_INTENT_PATTERNS
_QUERY_INTENT_PATTERNS = QUERY_INTENT_PATTERNS
_HIGH_RISK_INTENTS = HIGH_RISK_INTENTS
_CONTEXT_DEPENDENT_INTENTS = CONTEXT_DEPENDENT_INTENTS
_SCREEN_STATE_INTENTS = SCREEN_STATE_INTENTS
_HIGH_RISK_COMMAND_TYPES = HIGH_RISK_COMMAND_TYPES
_NUMBER_RE = NUMBER_RE
_QUOTED_TEXT_RE = QUOTED_TEXT_RE
_URL_RE = URL_RE
_DIRECTION_RE = DIRECTION_RE
_APP_PATTERNS_RE = APP_PATTERNS_RE
_match_intent_from_patterns = match_intent_from_patterns

# Global instance for backward compatibility
voice_processing_system = VoiceProcessingSystem()

# Logging
import logging

logger = logging.getLogger(__name__)

__all__ = [
    # Types
    "VoiceCommand",
    "SpeechQuality",
    # Models
    "AudioInput",
    "SpeechRecognitionResult",
    "VoiceCommandAnalysis",
    "SpeechSynthesisRequest",
    # Constants (public names)
    "AUTOMATION_INTENT_PATTERNS",
    "NAVIGATION_INTENT_PATTERNS",
    "QUERY_INTENT_PATTERNS",
    "HIGH_RISK_INTENTS",
    "CONTEXT_DEPENDENT_INTENTS",
    "SCREEN_STATE_INTENTS",
    "HIGH_RISK_COMMAND_TYPES",
    "NUMBER_RE",
    "QUOTED_TEXT_RE",
    "URL_RE",
    "DIRECTION_RE",
    "APP_PATTERNS_RE",
    "match_intent_from_patterns",
    # Engines
    "SpeechRecognitionEngine",
    "NaturalLanguageProcessor",
    "TextToSpeechEngine",
    # Main system
    "VoiceProcessingSystem",
    # Global instance
    "voice_processing_system",
]
