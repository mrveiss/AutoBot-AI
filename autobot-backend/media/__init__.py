# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Media Processing Pipelines
# Issue #735: Organize media processing into dedicated pipelines

"""
Media processing pipelines for various content types.

This module provides a unified architecture for processing different media types
(images, audio, video, documents, links) through dedicated pipeline implementations.
"""

from media.core.pipeline import MediaPipeline
from media.core.processor import MediaProcessor
from media.core.types import MediaType, ProcessingResult

__all__ = [
    "MediaPipeline",
    "MediaProcessor",
    "MediaType",
    "ProcessingResult",
]
