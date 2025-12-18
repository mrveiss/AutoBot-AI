# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Processing Package - Advanced voice command recognition and synthesis.

Extracted from voice_processing_system.py as part of Issue #381 god class refactoring.
This package provides a modular, maintainable structure for voice processing operations.

Package Structure:
    types.py           - Enums (VoiceCommand, SpeechQuality)
    models.py          - Dataclasses (AudioInput, SpeechRecognitionResult, etc.)
    constants.py       - Patterns, regex, and constant definitions
    speech_recognition.py - Speech-to-text engine
    nlp_processor.py   - Natural language processing for commands
    tts_engine.py      - Text-to-speech synthesis
    system.py          - Main VoiceProcessingSystem coordinator
"""

# Types
from .types import (
    VoiceCommand,
    SpeechQuality,
)

# Models
from .models import (
    AudioInput,
    SpeechRecognitionResult,
    VoiceCommandAnalysis,
    SpeechSynthesisRequest,
)

# Constants (commonly used pattern constants)
from .constants import (
    AUTOMATION_INTENT_PATTERNS,
    NAVIGATION_INTENT_PATTERNS,
    QUERY_INTENT_PATTERNS,
    HIGH_RISK_INTENTS,
    CONTEXT_DEPENDENT_INTENTS,
    SCREEN_STATE_INTENTS,
    HIGH_RISK_COMMAND_TYPES,
    NUMBER_RE,
    QUOTED_TEXT_RE,
    URL_RE,
    DIRECTION_RE,
    APP_PATTERNS_RE,
    match_intent_from_patterns,
)

# Engines
from .speech_recognition import SpeechRecognitionEngine
from .nlp_processor import NaturalLanguageProcessor
from .tts_engine import TextToSpeechEngine

# Main system coordinator
from .system import VoiceProcessingSystem

__all__ = [
    # Types
    "VoiceCommand",
    "SpeechQuality",
    # Models
    "AudioInput",
    "SpeechRecognitionResult",
    "VoiceCommandAnalysis",
    "SpeechSynthesisRequest",
    # Constants
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
    # System
    "VoiceProcessingSystem",
]
