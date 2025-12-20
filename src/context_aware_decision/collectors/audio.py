# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Audio Context Collector

Specialized collector for audio/voice context information.

Part of Issue #381 - God Class Refactoring
"""

import logging
from typing import Any, Dict, List

from ..models import ContextElement
from ..time_provider import TimeProvider
from ..types import ContextType

logger = logging.getLogger(__name__)


class AudioContextCollector:
    """Specialized collector for audio/voice context information."""

    def __init__(self):
        """Initialize audio context collector with time provider."""
        self.time_provider = TimeProvider()

    async def collect(self) -> List[ContextElement]:
        """Collect audio/voice context."""
        try:
            from src.voice_processing_system import voice_processing_system

            voice_status = voice_processing_system.get_system_status()
            audio_elements = []

            # Recent voice commands context
            if voice_status.get("recent_activity"):
                audio_elements.append(
                    self._create_voice_activity_context(voice_status["recent_activity"])
                )

            # Command history context
            command_history = voice_processing_system.get_command_history(limit=5)
            if command_history:
                audio_elements.append(
                    self._create_command_history_context(command_history)
                )

            return audio_elements

        except Exception as e:
            logger.debug("Audio context collection failed: %s", e)
            return []

    def _create_voice_activity_context(
        self, recent_activity: Dict[str, Any]
    ) -> ContextElement:
        """Create context element for voice activity."""
        return ContextElement(
            context_id=f"voice_activity_{self.time_provider.current_timestamp_millis()}",
            context_type=ContextType.AUDIO,
            content=recent_activity,
            confidence=0.8,
            relevance_score=0.7,
            timestamp=self.time_provider.current_timestamp(),
            source="voice_processing_system",
            metadata={"type": "voice_activity"},
        )

    def _create_command_history_context(
        self, command_history: List[Dict[str, Any]]
    ) -> ContextElement:
        """Create context element for command history."""
        return ContextElement(
            context_id=f"voice_history_{self.time_provider.current_timestamp_millis()}",
            context_type=ContextType.HISTORICAL,
            content=command_history,
            confidence=0.9,
            relevance_score=0.6,
            timestamp=self.time_provider.current_timestamp(),
            source="voice_processing_system",
            metadata={"type": "command_history", "count": len(command_history)},
        )
