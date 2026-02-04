# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Main Context Collector

Orchestrates all specialized context collectors and provides comprehensive
context collection for decision making.

Part of Issue #381 - God Class Refactoring
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from src.enhanced_memory_manager_async import TaskPriority
from src.task_execution_tracker import task_tracker

from ..models import ContextElement, DecisionContext
from ..time_provider import TimeProvider
from ..types import DEFAULT_USER_PREFERENCES, ContextType, DecisionType
from .audio import AudioContextCollector
from .system import SystemContextCollector
from .visual import VisualContextCollector

logger = logging.getLogger(__name__)


class ContextCollector:
    """Collects and manages context information from various sources."""

    def __init__(self):
        """Initialize context collector with cache and specialized sub-collectors."""
        self.context_cache: List[ContextElement] = []
        self.max_cache_size = 100
        self.context_relevance_decay = 0.95  # Decay factor per hour
        self.time_provider = TimeProvider()

        # Specialized collectors to reduce Feature Envy
        self.visual_collector = VisualContextCollector()
        self.audio_collector = AudioContextCollector()
        self.system_collector = SystemContextCollector()

        logger.info("Context Collector initialized")

    async def _gather_all_context_elements(
        self, decision_type: DecisionType
    ) -> List[ContextElement]:
        """Issue #665: Extracted from collect_comprehensive_context to reduce function length.

        Collects context from all sources in parallel and combines them.

        Args:
            decision_type: Type of decision being made

        Returns:
            Combined list of all context elements
        """
        visual, audio, system, historical, environmental = await asyncio.gather(
            self.visual_collector.collect(),
            self.audio_collector.collect(),
            self.system_collector.collect(),
            self._collect_historical_context(decision_type),
            self._collect_environmental_context(),
        )
        return [*visual, *audio, *system, *historical, *environmental]

    async def _analyze_context_elements(
        self, decision_type: DecisionType, context_elements: List[ContextElement]
    ) -> Dict[str, Any]:
        """Issue #665: Extracted from collect_comprehensive_context to reduce function length.

        Performs parallel analysis of context elements.

        Args:
            decision_type: Type of decision being made
            context_elements: Collected context elements

        Returns:
            Dict with constraints, available_actions, risk_factors,
            user_preferences, historical_patterns, system_state
        """
        constraints, available_actions, risk_factors = await asyncio.gather(
            self._identify_constraints(decision_type, context_elements),
            self._identify_available_actions(decision_type, context_elements),
            self._assess_risk_factors(context_elements),
        )
        user_preferences, historical_patterns, system_state = await asyncio.gather(
            self._get_user_preferences(decision_type),
            self._analyze_historical_patterns(decision_type),
            self._get_current_system_state(),
        )
        return {
            "constraints": constraints,
            "available_actions": available_actions,
            "risk_factors": risk_factors,
            "user_preferences": user_preferences,
            "historical_patterns": historical_patterns,
            "system_state": system_state,
        }

    async def collect_comprehensive_context(
        self, decision_type: DecisionType, primary_goal: str
    ) -> DecisionContext:
        """Collect comprehensive context for decision making."""
        async with task_tracker.track_task(
            "Context Collection",
            f"Collecting context for {decision_type.value} decision",
            agent_type="context_collector",
            priority=TaskPriority.HIGH,
            inputs={"decision_type": decision_type.value, "goal": primary_goal},
        ) as task_context:
            try:
                decision_id = (
                    f"decision_{self.time_provider.current_timestamp_millis()}"
                )
                context_elements = await self._gather_all_context_elements(
                    decision_type
                )
                analysis = await self._analyze_context_elements(
                    decision_type, context_elements
                )

                decision_context = DecisionContext(
                    decision_id=decision_id,
                    decision_type=decision_type,
                    primary_goal=primary_goal,
                    context_elements=context_elements,
                    timestamp=self.time_provider.current_timestamp(),
                    **analysis,
                )

                self._update_context_cache(context_elements)
                task_context.set_outputs(
                    {
                        "context_elements": len(context_elements),
                        "available_actions": len(analysis["available_actions"]),
                        "constraints": len(analysis["constraints"]),
                        "risk_factors": len(analysis["risk_factors"]),
                    }
                )
                logger.info(
                    f"Context collected: {len(context_elements)} elements for decision {decision_id}"
                )
                return decision_context
            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error("Context collection failed: %s", e)
                raise

    async def _collect_historical_context(
        self, decision_type: DecisionType
    ) -> List[ContextElement]:
        """Collect relevant historical context."""
        try:
            # This would query the enhanced memory system for relevant historical data
            # For now, return placeholder context
            historical_elements = []

            # Recent similar decisions (placeholder)
            recent_decisions = []  # Would query memory system
            if recent_decisions:
                history_context = ContextElement(
                    context_id=f"decision_history_{self.time_provider.current_timestamp_millis()}",
                    context_type=ContextType.HISTORICAL,
                    content=recent_decisions,
                    confidence=0.8,
                    relevance_score=0.7,
                    timestamp=self.time_provider.current_timestamp(),
                    source="enhanced_memory_system",
                    metadata={
                        "type": "decision_history",
                        "decision_type": decision_type.value,
                    },
                )
                historical_elements.append(history_context)

            return historical_elements

        except Exception as e:
            logger.debug("Historical context collection failed: %s", e)
            return []

    async def _collect_environmental_context(self) -> List[ContextElement]:
        """Collect environmental context (time, date, system load, etc.)."""
        try:
            temporal_context = ContextElement(
                context_id=f"temporal_{self.time_provider.current_timestamp_millis()}",
                context_type=ContextType.ENVIRONMENTAL,
                content=self.time_provider.get_temporal_context_data(),
                confidence=1.0,
                relevance_score=0.5,
                timestamp=self.time_provider.current_timestamp(),
                source="system_clock",
                metadata={"type": "temporal_context"},
            )

            return [temporal_context]

        except Exception as e:
            logger.debug("Environmental context collection failed: %s", e)
            return []

    def _check_resource_constraints(
        self, resource_info: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check resource-based constraints (Issue #298 - extracted helper)."""
        constraints = []

        cpu_percent = resource_info.get("cpu_percent", 0)
        if cpu_percent > 80:
            constraints.append(
                {
                    "type": "high_cpu_usage",
                    "description": f"CPU usage at {cpu_percent}%",
                    "severity": "medium",
                    "affects": ["resource_intensive_tasks"],
                }
            )

        memory_percent = resource_info.get("memory_percent", 0)
        if memory_percent > 85:
            constraints.append(
                {
                    "type": "high_memory_usage",
                    "description": f"Memory usage at {memory_percent}%",
                    "severity": "high",
                    "affects": ["memory_intensive_operations"],
                }
            )

        return constraints

    async def _identify_constraints(
        self, decision_type: DecisionType, context_elements: List[ContextElement]
    ) -> List[Dict[str, Any]]:
        """Identify constraints that limit available actions."""
        constraints = []

        # Issue #317: Single-pass grouping of context elements by type (O(n²) → O(n))
        context_by_type: Dict[str, List[ContextElement]] = {}
        for ce in context_elements:
            ctx_type = ce.metadata.get("type")
            if ctx_type:
                if ctx_type not in context_by_type:
                    context_by_type[ctx_type] = []
                context_by_type[ctx_type].append(ce)

        # Check for active takeovers (constraint on autonomous actions)
        if context_by_type.get("active_takeovers"):
            constraints.append(
                {
                    "type": "human_takeover_active",
                    "description": "Human operator has taken control",
                    "severity": "high",
                    "affects": ["automation_action", "navigation_choice"],
                }
            )

        # Check system resources (Issue #298 - uses extracted helper)
        for resource_context in context_by_type.get("resource_usage", []):
            constraints.extend(
                self._check_resource_constraints(resource_context.content)
            )

        # Time-based constraints
        for temporal_context in context_by_type.get("temporal_context", []):
            temporal_info = temporal_context.content
            if not temporal_info.get("is_business_hours", True):
                constraints.append(
                    {
                        "type": "outside_business_hours",
                        "description": "Current time is outside business hours",
                        "severity": "low",
                        "affects": ["external_communications", "user_interactions"],
                    }
                )

        return constraints

    def _get_automation_actions(
        self, context_elements: List[ContextElement]
    ) -> List[Dict[str, Any]]:
        """Get automation actions from context (Issue #298 - extracted helper)."""
        # Issue #317: Single-pass extraction using list comprehension (O(n*m) → O(n+m))
        return [
            {
                "action_type": "automation",
                "action": opportunity.get("automation_action", "unknown"),
                "target": opportunity.get("element_id"),
                "confidence": opportunity.get("confidence", 0.5),
                "description": opportunity.get("description", ""),
            }
            for ce in context_elements
            if ce.metadata.get("type") == "automation_opportunities"
            for opportunity in ce.content
        ]

    def _get_navigation_actions(
        self, context_elements: List[ContextElement]
    ) -> List[Dict[str, Any]]:
        """Get navigation actions from context (Issue #298 - extracted helper)."""
        # Issue #317: Optimized with set conversion for O(1) membership check (O(n*m*k) → O(n*m))
        return [
            {
                "action_type": "navigation",
                "action": "click_element",
                "target": element.get("id"),
                "confidence": element.get("confidence", 0.5),
                "description": f"Click {element.get('text', 'element')}",
            }
            for ce in context_elements
            if ce.metadata.get("type") == "ui_elements"
            for element in ce.content
            if "click" in set(element.get("interactions", []))
        ]

    async def _identify_available_actions(
        self, decision_type: DecisionType, context_elements: List[ContextElement]
    ) -> List[Dict[str, Any]]:
        """Identify actions available based on current context."""
        available_actions = []

        # Route to appropriate action identifier (Issue #298 - uses helpers)
        if decision_type == DecisionType.AUTOMATION_ACTION:
            available_actions.extend(self._get_automation_actions(context_elements))

        elif decision_type == DecisionType.NAVIGATION_CHOICE:
            available_actions.extend(self._get_navigation_actions(context_elements))

        elif decision_type == DecisionType.HUMAN_ESCALATION:
            available_actions.extend(
                [
                    {
                        "action_type": "escalation",
                        "action": "request_takeover",
                        "trigger": "manual_request",
                        "confidence": 1.0,
                        "description": "Request human takeover",
                    },
                    {
                        "action_type": "escalation",
                        "action": "pause_operations",
                        "confidence": 1.0,
                        "description": "Pause autonomous operations",
                    },
                ]
            )

        # Always available: monitoring and logging actions
        available_actions.extend(
            [
                {
                    "action_type": "monitoring",
                    "action": "continue_monitoring",
                    "confidence": 1.0,
                    "description": "Continue monitoring current state",
                },
                {
                    "action_type": "logging",
                    "action": "log_decision",
                    "confidence": 1.0,
                    "description": "Log decision and context",
                },
            ]
        )

        return available_actions

    def _assess_low_confidence_risk(
        self, context_elements: List[ContextElement]
    ) -> Optional[Dict[str, Any]]:
        """Assess risk from low confidence context elements. Issue #620."""
        low_confidence_elements = [ce for ce in context_elements if ce.confidence < 0.6]
        if len(low_confidence_elements) > len(context_elements) * 0.3:
            return {
                "risk_type": "low_context_confidence",
                "severity": "medium",
                "probability": 0.7,
                "description": (
                    f"{len(low_confidence_elements)} context elements have low confidence"
                ),
                "mitigation": (
                    "Gather additional context or request human verification"
                ),
            }
        return None

    def _assess_resource_constraint_risks(
        self, context_elements: List[ContextElement]
    ) -> List[Dict[str, Any]]:
        """Assess risks from system resource constraints. Issue #620."""
        risks = []
        resource_contexts = [
            ce for ce in context_elements if ce.metadata.get("type") == "resource_usage"
        ]
        for resource_context in resource_contexts:
            resource_info = resource_context.content
            if resource_info.get("cpu_percent", 0) > 90:
                risks.append(
                    {
                        "risk_type": "system_overload",
                        "severity": "high",
                        "probability": 0.9,
                        "description": "System CPU usage critically high",
                        "mitigation": "Defer non-critical operations",
                    }
                )
        return risks

    def _assess_information_overload_risk(
        self, context_elements: List[ContextElement]
    ) -> Optional[Dict[str, Any]]:
        """Assess risk from too much conflicting context. Issue #620."""
        if len(context_elements) > 50:
            return {
                "risk_type": "information_overload",
                "severity": "low",
                "probability": 0.4,
                "description": "Large amount of context data may contain conflicts",
                "mitigation": "Prioritize most relevant context elements",
            }
        return None

    async def _assess_risk_factors(
        self, context_elements: List[ContextElement]
    ) -> List[Dict[str, Any]]:
        """Assess risk factors based on context."""
        risk_factors = []

        # Check for low confidence elements
        low_confidence_risk = self._assess_low_confidence_risk(context_elements)
        if low_confidence_risk:
            risk_factors.append(low_confidence_risk)

        # Check for system resource constraints
        risk_factors.extend(self._assess_resource_constraint_risks(context_elements))

        # Check for conflicting context
        overload_risk = self._assess_information_overload_risk(context_elements)
        if overload_risk:
            risk_factors.append(overload_risk)

        return risk_factors

    async def _get_user_preferences(
        self, decision_type: DecisionType
    ) -> Dict[str, Any]:
        """Get user preferences relevant to decision type."""
        # This would query a user preference system
        # For now, return default preferences
        return DEFAULT_USER_PREFERENCES.copy()

    async def _analyze_historical_patterns(
        self, decision_type: DecisionType
    ) -> List[Dict[str, Any]]:
        """Analyze historical patterns for similar decisions."""
        # This would analyze the enhanced memory system
        # For now, return placeholder patterns
        patterns = [
            {
                "pattern_type": "success_rate",
                "decision_type": decision_type.value,
                "success_rate": 0.85,
                "sample_size": 20,
                "timeframe": "last_30_days",
            },
            {
                "pattern_type": "common_failure_modes",
                "failures": ["context_insufficient", "user_intervention_required"],
                "frequency": 0.15,
            },
        ]

        return patterns

    async def _get_current_system_state(self) -> Dict[str, Any]:
        """Get comprehensive current system state."""
        return {
            "autonomous_mode": True,
            "active_sessions": 0,
            "pending_tasks": 0,
            "system_health": "healthy",
            "last_user_interaction": self.time_provider.current_timestamp()
            - 3600,  # 1 hour ago
            "current_focus": "monitoring",
        }

    def _update_context_cache(self, new_elements: List[ContextElement]):
        """Update the context cache with new elements."""
        self.context_cache.extend(new_elements)

        # Remove oldest elements if cache is too large
        if len(self.context_cache) > self.max_cache_size:
            self.context_cache = self.context_cache[-self.max_cache_size :]

        # Decay relevance scores based on age using ContextElement method
        for element in self.context_cache:
            element.apply_relevance_decay(self.context_relevance_decay)

    def get_cached_context(self) -> List[ContextElement]:
        """Get the current context cache."""
        return self.context_cache.copy()

    def clear_cache(self) -> None:
        """Clear the context cache."""
        self.context_cache.clear()
