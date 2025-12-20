# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Visual Context Collector

Specialized collector for visual context information from screen analysis.

Part of Issue #381 - God Class Refactoring
"""

import logging
from typing import Any, Dict, List

from ..models import ContextElement
from ..time_provider import TimeProvider
from ..types import ContextType

logger = logging.getLogger(__name__)


class VisualContextCollector:
    """Specialized collector for visual context information."""

    def __init__(self):
        """Initialize visual context collector with time provider."""
        self.time_provider = TimeProvider()

    async def collect(self) -> List[ContextElement]:
        """Collect visual context from screen analysis."""
        try:
            from src.computer_vision_system import computer_vision_system

            screen_analysis = (
                await computer_vision_system.analyze_and_understand_screen()
            )
            visual_elements = []

            # Screen state context
            if screen_analysis.get("screen_analysis"):
                visual_elements.append(
                    self._create_screen_context(screen_analysis["screen_analysis"])
                )

            # UI elements context
            if screen_analysis.get("ui_elements"):
                visual_elements.append(
                    self._create_ui_context(screen_analysis["ui_elements"])
                )

            # Automation opportunities context
            if screen_analysis.get("automation_opportunities"):
                visual_elements.append(
                    self._create_automation_context(
                        screen_analysis["automation_opportunities"]
                    )
                )

            return visual_elements

        except Exception as e:
            logger.debug("Visual context collection failed: %s", e)
            return []

    def _create_screen_context(self, screen_data: Dict[str, Any]) -> ContextElement:
        """Create context element for screen analysis."""
        return ContextElement(
            context_id=f"screen_state_{self.time_provider.current_timestamp_millis()}",
            context_type=ContextType.VISUAL,
            content=screen_data,
            confidence=screen_data.get("confidence_score", 0.8),
            relevance_score=0.9,
            timestamp=self.time_provider.current_timestamp(),
            source="computer_vision_system",
            metadata={"type": "screen_analysis"},
        )

    def _create_ui_context(self, ui_elements: List[Dict[str, Any]]) -> ContextElement:
        """Create context element for UI elements."""
        return ContextElement(
            context_id=f"ui_elements_{self.time_provider.current_timestamp_millis()}",
            context_type=ContextType.VISUAL,
            content=ui_elements,
            confidence=0.8,
            relevance_score=0.85,
            timestamp=self.time_provider.current_timestamp(),
            source="computer_vision_system",
            metadata={"type": "ui_elements", "count": len(ui_elements)},
        )

    def _create_automation_context(
        self, opportunities: List[Dict[str, Any]]
    ) -> ContextElement:
        """Create context element for automation opportunities."""
        return ContextElement(
            context_id=f"automation_ops_{self.time_provider.current_timestamp_millis()}",
            context_type=ContextType.VISUAL,
            content=opportunities,
            confidence=0.75,
            relevance_score=0.9,
            timestamp=self.time_provider.current_timestamp(),
            source="computer_vision_system",
            metadata={"type": "automation_opportunities"},
        )
