# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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


class PersistenceOutcome(str, Enum):
    """What happened to a result's memory write (#16926).

    Four values, not a bool: a tenancy refusal and a transient failure both left
    the result unwritten, and collapsing them hid a data-isolation event behind
    a Redis blip. The API forwards the value, so the caller sees which one.
    """

    STORED = "stored"
    UNOWNED = "unowned"  # no user identity (e.g. a service key): nothing to scope the write to
    REFUSED = "refused"  # the tenancy guard rejected the owner scope
    FAILED = "failed"  # the store raised for any other reason


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
