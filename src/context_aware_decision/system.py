# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context-Aware Decision System

Main entry point for the context-aware decision making system.
Coordinates context collection and decision making.

Part of Issue #381 - God Class Refactoring
"""

import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import numpy as np

from src.enhanced_memory_manager import EnhancedMemoryManager
from src.enhanced_memory_manager_async import TaskPriority
from src.task_execution_tracker import task_tracker

from .collectors import ContextCollector
from .decision_engine import DecisionEngine
from .models import Decision, DecisionContext
from .time_provider import TimeProvider
from .types import DecisionType

logger = logging.getLogger(__name__)


class ContextAwareDecisionSystem:
    """Main context-aware decision making system."""

    def __init__(self, memory_manager: Optional[EnhancedMemoryManager] = None):
        """Initialize decision system with memory manager, collector, and engine."""
        self.memory_manager = memory_manager or EnhancedMemoryManager()
        self.context_collector = ContextCollector()
        self.decision_engine = DecisionEngine()
        self.time_provider = TimeProvider()

        # Decision history
        self.decision_history: List[Decision] = []
        self.max_history = 50

        logger.info("Context-Aware Decision System initialized")

    async def make_contextual_decision(
        self, decision_type: DecisionType, primary_goal: str
    ) -> Decision:
        """Make a decision considering comprehensive context."""

        async with task_tracker.track_task(
            "Contextual Decision Making",
            f"Making contextual {decision_type.value} decision: {primary_goal}",
            agent_type="context_aware_decision_system",
            priority=TaskPriority.HIGH,
            inputs={"decision_type": decision_type.value, "primary_goal": primary_goal},
        ) as task_context:
            try:
                # Collect comprehensive context
                decision_context = (
                    await self.context_collector.collect_comprehensive_context(
                        decision_type, primary_goal
                    )
                )

                # Make decision based on context
                decision = await self.decision_engine.make_decision(decision_context)

                # Update decision history
                self._update_history(decision)

                # Store in memory system
                await self._store_decision_in_memory(decision, decision_context)

                task_context.set_outputs(
                    {
                        "decision_id": decision.decision_id,
                        "chosen_action": decision.chosen_action.get(
                            "action", "unknown"
                        ),
                        "confidence": decision.confidence,
                        "requires_approval": decision.requires_approval,
                    }
                )

                logger.info(
                    f"Contextual decision made: {decision.chosen_action.get('action')} "
                    f"(confidence: {decision.confidence:.2f})"
                )
                return decision

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error("Contextual decision making failed: %s", e)
                raise

    def _update_history(self, decision: Decision) -> None:
        """Update decision history with new decision."""
        self.decision_history.append(decision)
        if len(self.decision_history) > self.max_history:
            self.decision_history = self.decision_history[-self.max_history:]

    async def _store_decision_in_memory(
        self, decision: Decision, context: DecisionContext
    ) -> None:
        """Store decision and context in enhanced memory system."""
        try:
            # Create memory task record for the decision
            task_id = self.memory_manager.create_task_record(
                task_name=f"Decision: {decision.decision_type.value}",
                description=(
                    f"Contextual decision making: "
                    f"{decision.chosen_action.get('action', 'unknown')}"
                ),
                priority=TaskPriority.MEDIUM,
                agent_type="context_aware_decision_system",
                inputs={
                    "decision_type": decision.decision_type.value,
                    "primary_goal": context.primary_goal,
                    "context_elements_count": len(context.context_elements),
                },
                metadata={
                    "decision_data": asdict(decision),
                    "context_summary": {
                        "elements_count": len(context.context_elements),
                        "constraints_count": len(context.constraints),
                        "actions_count": len(context.available_actions),
                        "risk_factors_count": len(context.risk_factors),
                    },
                },
            )

            # Mark task as started and completed
            self.memory_manager.start_task(task_id)
            self.memory_manager.complete_task(
                task_id,
                outputs={
                    "chosen_action": decision.chosen_action,
                    "confidence": decision.confidence,
                    "requires_approval": decision.requires_approval,
                },
            )

        except Exception as e:
            logger.error("Failed to store decision in memory: %s", e)

    def get_decision_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get recent decision history."""
        history = self.decision_history
        if limit:
            history = history[-limit:]

        return [decision.get_summary() for decision in history]

    def get_system_status(self) -> Dict[str, Any]:
        """Get decision system status."""
        recent_decisions = self.decision_history[-10:] if self.decision_history else []

        return {
            "total_decisions": len(self.decision_history),
            "recent_decisions_count": len(recent_decisions),
            "average_confidence": (
                float(np.mean([d.confidence for d in recent_decisions]))
                if recent_decisions
                else 0.0
            ),
            "approval_required_rate": (
                float(np.mean([d.requires_approval for d in recent_decisions]))
                if recent_decisions
                else 0.0
            ),
            "most_common_decision_type": (
                max(
                    [d.decision_type for d in recent_decisions],
                    key=[d.decision_type for d in recent_decisions].count,
                ).value
                if recent_decisions
                else "none"
            ),
            "context_collection_status": "active",
            "decision_engine_status": "active",
        }

    def clear_history(self) -> None:
        """Clear decision history."""
        self.decision_history.clear()

    def get_context_cache(self) -> List[Dict[str, Any]]:
        """Get current context cache."""
        return [ce.to_dict() for ce in self.context_collector.get_cached_context()]
