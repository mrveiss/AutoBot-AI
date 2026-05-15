# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Multimodal Processor Types and Constants

Enums and constants for the unified multimodal processing system.

Part of Issue #381 - God Class Refactoring
"""

from enum import Enum


class ModalityType(Enum):
    """Types of input modalities supported"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    COMBINED = "combined"


class ProcessingIntent(Enum):
    """Types of processing intents"""

    SCREEN_ANALYSIS = "screen_analysis"
    VOICE_COMMAND = "voice_command"
    VISUAL_QA = "visual_qa"
    AUTOMATION_TASK = "automation_task"
    CONTENT_GENERATION = "content_generation"
    DECISION_MAKING = "decision_making"


class ConfidenceLevel(Enum):
    """Confidence levels for processing results"""

    VERY_HIGH = 0.9
    HIGH = 0.8
    MEDIUM = 0.6
    LOW = 0.4
    VERY_LOW = 0.2


# Issue #380: Module-level tuple for embedding field names in result extraction
EMBEDDING_FIELDS = ("clip_features", "audio_embedding", "embeddings")

# Performance optimization: O(1) lookup for command classification (Issue #326)
LAUNCH_COMMAND_WORDS = {"open", "launch", "start", "run"}
CLOSE_COMMAND_WORDS = {"close", "quit", "exit", "stop"}
SEARCH_COMMAND_WORDS = {"search", "find", "look for"}
TEXT_INPUT_COMMAND_WORDS = {"type", "write", "input"}
INTERACTION_COMMAND_WORDS = {"click", "press", "select"}
NAVIGATION_COMMAND_WORDS = {"navigate", "go to", "browse"}
MEDIA_CONTROL_COMMAND_WORDS = {"play", "pause", "volume"}
QUERY_COMMAND_WORDS = {"help", "what", "how", "explain"}

# Modality types for visual processing (Issue #326)
VISUAL_MODALITY_TYPES = {ModalityType.IMAGE, ModalityType.VIDEO}
