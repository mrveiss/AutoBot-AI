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

# Constants (commonly used pattern constants)
from .constants import (
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
    match_intent_from_patterns,
)

# Models
from .models import (
    AudioInput,
    SpeechRecognitionResult,
    SpeechSynthesisRequest,
    VoiceCommandAnalysis,
)
from .nlp_processor import NaturalLanguageProcessor

# Engines
from .speech_recognition import SpeechRecognitionEngine

# Main system coordinator
from .system import VoiceProcessingSystem
from .tts_engine import TextToSpeechEngine

# Types
from .types import SpeechQuality, VoiceCommand

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
