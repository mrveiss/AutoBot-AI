# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Base Media Processor
# Issue #735: Organize media processing into dedicated pipelines

"""Base processor interface for media components."""

from abc import ABC, abstractmethod
from typing import Any

from autobot_shared.logging_manager import get_logger


class MediaProcessor(ABC):
    """
    Abstract base class for media processing components.

    Processors handle specific processing tasks within a pipeline
    (e.g., image enhancement, audio transcription, etc.).
    """

    def __init__(self, processor_name: str):
        """
        Initialize processor.

        Args:
            processor_name: Name identifier for this processor
        """
        self.processor_name = processor_name
        self.logger = get_logger(f"{__name__}.{processor_name}")

    @abstractmethod
    async def process(self, data: Any) -> Any:
        """
        Process data and return result.

        Args:
            data: Input data to process

        Returns:
            Processed output
        """
        raise NotImplementedError

    def calculate_confidence(self, result: Any) -> float:
        """
        Calculate confidence score for result.

        Args:
            result: Processing result to evaluate

        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Default implementation - override in subclasses
        return 0.5
