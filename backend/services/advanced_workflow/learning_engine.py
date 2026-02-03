# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Learning Engine

Machine learning component for workflow optimization.
"""

import logging
from datetime import datetime
from typing import List

from backend.type_defs.common import Metadata

from .models import SmartWorkflowStep

logger = logging.getLogger(__name__)


class WorkflowLearningEngine:
    """Machine learning component for workflow optimization"""

    def __init__(self):
        """Initialize learning engine with empty pattern tracking data."""
        self.learning_data = {
            "user_patterns": {},
            "success_rates": {},
            "optimization_effectiveness": {},
            "command_preferences": {},
        }

    async def record_workflow_generation(
        self,
        user_request: str,
        intent_analysis: Metadata,
        generated_steps: List[SmartWorkflowStep],
    ):
        """Record workflow generation for learning"""
        try:
            # Extract learning features
            features = {
                "request_length": len(user_request.split()),
                "intent": intent_analysis.get("primary_intent"),
                "complexity": intent_analysis.get("complexity"),
                "components": intent_analysis.get("components", []),
                "steps_generated": len(generated_steps),
                "ai_optimizations": sum(1 for s in generated_steps if s.ai_generated),
                "timestamp": datetime.now().isoformat(),
            }

            # Store in learning database
            request_hash = str(hash(user_request))
            self.learning_data["user_patterns"][request_hash] = features

            logger.info(
                f"Recorded workflow generation learning data for request: "
                f"{user_request[:50]}"
            )

        except Exception as e:
            logger.error("Failed to record learning data: %s", e)

    async def get_optimization_recommendations(
        self, workflow_id: str, user_feedback: Metadata = None
    ) -> List[str]:
        """Get AI-driven optimization recommendations"""
        recommendations = []

        if user_feedback:
            satisfaction = user_feedback.get("satisfaction_score", 0)
            if satisfaction < 7:
                recommendations.append(
                    "Reduce workflow complexity based on user feedback"
                )

            if user_feedback.get("too_many_confirmations"):
                recommendations.append(
                    "Decrease confirmation requirements for trusted operations"
                )

        return recommendations
