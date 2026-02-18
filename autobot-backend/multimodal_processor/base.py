# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Modal Processor

Abstract base class for modal-specific processors.

Part of Issue #381 - God Class Refactoring
"""

import logging
from typing import Any

from enhanced_memory_manager_async import get_async_enhanced_memory_manager

from .models import MultiModalInput, ProcessingResult


class BaseModalProcessor:
    """Base class for modal-specific processors"""

    def __init__(self, processor_type: str):
        """Initialize base processor with type-specific logger and memory manager."""
        self.processor_type = processor_type
        self.logger = logging.getLogger(f"{__name__}.{processor_type}")
        self.memory_manager = get_async_enhanced_memory_manager()

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process input and return result"""
        raise NotImplementedError

    def calculate_confidence(self, processing_data: Any) -> float:
        """Calculate confidence score for processing result"""
        # Base implementation - override in subclasses
        return 0.5
