# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Media Type Definitions
# Issue #735: Organize media processing into dedicated pipelines

"""Type definitions for media processing."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class MediaType(Enum):
    """Supported media types for processing."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    LINK = "link"
    TEXT = "text"
    COMBINED = "combined"


class ProcessingIntent(Enum):
    """Intent types for media processing."""

    ANALYSIS = "analysis"
    EXTRACTION = "extraction"
    TRANSCRIPTION = "transcription"
    CONVERSION = "conversion"
    ENHANCEMENT = "enhancement"
    AUTOMATION = "automation"
    DECISION_MAKING = "decision_making"


@dataclass
class MediaInput:
    """Input data for media processing."""

    media_id: str
    media_type: MediaType
    intent: ProcessingIntent
    data: Any  # Flexible field for any media data (bytes, path, URL, etc.)
    metadata: Dict[str, Any] = field(default_factory=dict)
    mime_type: Optional[str] = None


@dataclass
class ProcessingResult:
    """Result of media processing operation."""

    result_id: str
    media_id: str
    media_type: MediaType
    intent: ProcessingIntent
    success: bool
    confidence: float
    result_data: Any
    processing_time: float
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineMetrics:
    """Metrics for pipeline performance."""

    total_processed: int = 0
    successful: int = 0
    failed: int = 0
    average_time: float = 0.0
    average_confidence: float = 0.0
