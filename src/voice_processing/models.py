# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Voice Processing Data Models

Dataclasses for voice processing inputs, outputs, and analysis results.
Extracted from voice_processing_system.py as part of Issue #381 god class refactoring.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import numpy as np

from src.enhanced_memory_manager_async import TaskPriority
from src.voice_processing.types import SpeechQuality, VoiceCommand


@dataclass
class AudioInput:
    """Audio input data structure"""

    audio_id: str
    audio_data: Union[bytes, np.ndarray]
    sample_rate: int
    duration: float
    format: str  # 'wav', 'mp3', 'raw', etc.
    channels: int
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class SpeechRecognitionResult:
    """Result of speech recognition processing"""

    audio_id: str
    transcription: str
    confidence: float
    language: str
    alternative_transcriptions: List[Dict[str, Any]]
    speech_segments: List[Dict[str, Any]]
    audio_quality: SpeechQuality
    noise_level: float
    processing_time: float
    metadata: Dict[str, Any]


@dataclass
class VoiceCommandAnalysis:
    """Analysis of voice command intent and parameters"""

    command_id: str
    command_type: VoiceCommand
    intent: str
    entities: Dict[str, Any]
    parameters: Dict[str, Any]
    confidence: float
    suggested_actions: List[str]
    requires_confirmation: bool
    context_needed: bool
    metadata: Optional[Dict[str, Any]] = None  # Added for timestamp support


@dataclass
class SpeechSynthesisRequest:
    """Request for text-to-speech synthesis"""

    text: str
    voice_settings: Dict[str, Any]
    output_format: str
    priority: TaskPriority
    metadata: Dict[str, Any]
