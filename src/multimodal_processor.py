"""
Multi-Modal Input Processor for AutoBot Phase 9 - Compatibility Layer
This module provides backward compatibility while redirecting to the unified processor
"""

import logging
from typing import Any, Dict

# Import from implementation module for consistency
from src.multimodal_processor_impl import (
    ConfidenceLevel,
    ModalityType,
    MultiModalInput,
    ProcessingIntent,
    ProcessingResult,
    unified_processor,
)

logger = logging.getLogger(__name__)

# Backward compatibility aliases
ModalInput = MultiModalInput  # Alias for old name


class MultiModalProcessor:
    """
    Compatibility class that wraps the unified processor
    """

    def __init__(self):
        self._unified = unified_processor
        logger.info("Using unified multi-modal processor for backward compatibility")

    async def process(self, input_data: MultiModalInput) -> ProcessingResult:
        """Process multi-modal input using unified processor"""
        return await self._unified.process(input_data)

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return self._unified.get_stats()

    def reset_stats(self):
        """Reset processing statistics"""
        self._unified.reset_stats()


# Global instance for backward compatibility
multimodal_processor = MultiModalProcessor()

# Export key components for compatibility
__all__ = [
    "ModalityType",
    "ProcessingIntent",
    "MultiModalInput",
    "ModalInput",  # Alias
    "ProcessingResult",
    "ConfidenceLevel",
    "MultiModalProcessor",
    "multimodal_processor",
    "unified_processor",
]
