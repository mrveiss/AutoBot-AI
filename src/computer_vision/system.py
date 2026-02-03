# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Computer Vision System Coordinator

Issue #381: Extracted from computer_vision_system.py god class refactoring.
Contains the main ComputerVisionSystem class that coordinates all components.
"""

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from src.enhanced_memory_manager import EnhancedMemoryManager, TaskPriority
from src.task_execution_tracker import task_tracker

from .screen_analyzer import ScreenAnalyzer
from .types import ScreenState

logger = logging.getLogger(__name__)


class ComputerVisionSystem:
    """Main computer vision system coordinator"""

    def __init__(self, memory_manager: Optional[EnhancedMemoryManager] = None):
        """Initialize vision system with memory manager and screen analyzer."""
        self.memory_manager = memory_manager or EnhancedMemoryManager()
        self.screen_analyzer = ScreenAnalyzer()

        # Analysis history
        self.analysis_history: List[ScreenState] = []
        self.max_history = 10

        logger.info("Computer Vision System initialized")

    async def analyze_and_understand_screen(
        self, session_id: Optional[str] = None, context_audio: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """Comprehensive screen analysis and understanding"""

        async with task_tracker.track_task(
            "Computer Vision Analysis",
            "Complete screen understanding and element detection",
            agent_type="computer_vision_system",
            priority=TaskPriority.HIGH,
            inputs={"session_id": session_id},
        ) as task_context:
            try:
                # Perform comprehensive screen analysis
                screen_state = await self.screen_analyzer.analyze_current_screen(
                    session_id, context_audio
                )

                # Detect changes from previous analysis
                changes = await self.screen_analyzer.detect_screen_changes()

                # Store in history
                self.analysis_history.append(screen_state)
                if len(self.analysis_history) > self.max_history:
                    self.analysis_history = self.analysis_history[-self.max_history :]

                # Prepare comprehensive results (Tell, Don't Ask)
                results = {
                    "screen_analysis": screen_state.get_analysis_summary(),
                    "ui_elements": screen_state.get_element_collection().to_dict_list(),
                    "context_analysis": screen_state.context_analysis,
                    "automation_opportunities": screen_state.automation_opportunities,
                    "change_detection": changes,
                    "recommendations": screen_state.generate_recommendations(),
                }

                task_context.set_outputs(
                    {
                        "elements_detected": len(screen_state.ui_elements),
                        "confidence": screen_state.confidence_score,
                        "opportunities": len(screen_state.automation_opportunities),
                        "changes_detected": changes.get("changes_detected", False),
                    }
                )

                logger.info(
                    "Computer vision analysis completed: %d elements detected",
                    len(screen_state.ui_elements),
                )
                return results

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error("Computer vision analysis failed: %s", e)
                raise

    def get_analysis_summary(self) -> Dict[str, Any]:
        """Get summary of recent computer vision analysis"""
        if not self.analysis_history:
            return {"status": "no_analysis_available"}

        latest_analysis = self.analysis_history[-1]

        return {
            "latest_analysis": {
                "timestamp": latest_analysis.timestamp,
                "elements_detected": len(latest_analysis.ui_elements),
                "confidence": latest_analysis.confidence_score,
                "automation_ready": (
                    latest_analysis.context_analysis.get(
                        "automation_readiness", {}
                    ).get("recommendation")
                    == "ready"
                ),
            },
            "history_count": len(self.analysis_history),
            "trending_confidence": (
                np.mean([a.confidence_score for a in self.analysis_history[-5:]])
                if len(self.analysis_history) >= 5
                else latest_analysis.confidence_score
            ),
        }
