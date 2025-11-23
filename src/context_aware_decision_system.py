# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context-Aware Decision Making System for AutoBot
Intelligent decision making that considers multi-modal context, history, and environmental factors
"""

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from src.computer_vision_system import ScreenState, UIElement, computer_vision_system
from src.constants.network_constants import NetworkConstants
from src.enhanced_memory_manager import EnhancedMemoryManager
from src.enhanced_memory_manager_async import (
    TaskPriority,
    get_async_enhanced_memory_manager,
)
from src.multimodal_processor import (
    ModalInput,
    ModalityType,
    ProcessingIntent,
    multimodal_processor,
)
from src.takeover_manager import TakeoverTrigger, takeover_manager
from src.task_execution_tracker import task_tracker
from src.voice_processing_system import (
    VoiceCommand,
    VoiceCommandAnalysis,
    voice_processing_system,
)

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    """Types of decisions the system can make"""

    AUTOMATION_ACTION = "automation_action"
    NAVIGATION_CHOICE = "navigation_choice"
    TASK_PRIORITIZATION = "task_prioritization"
    RISK_ASSESSMENT = "risk_assessment"
    CONTEXT_SWITCHING = "context_switching"
    RESOURCE_ALLOCATION = "resource_allocation"
    HUMAN_ESCALATION = "human_escalation"
    WORKFLOW_OPTIMIZATION = "workflow_optimization"


class ConfidenceLevel(Enum):
    """Confidence levels for decision making"""

    VERY_HIGH = "very_high"  # > 0.9
    HIGH = "high"  # 0.7 - 0.9
    MEDIUM = "medium"  # 0.5 - 0.7
    LOW = "low"  # 0.3 - 0.5
    VERY_LOW = "very_low"  # < 0.3


class ContextType(Enum):
    """Types of context information"""

    VISUAL = "visual"
    AUDIO = "audio"
    TEXTUAL = "textual"
    HISTORICAL = "historical"
    ENVIRONMENTAL = "environmental"
    USER_PREFERENCE = "user_preference"
    SYSTEM_STATE = "system_state"
    TASK_CONTEXT = "task_context"


@dataclass
class ContextElement:
    """Individual piece of context information"""

    context_id: str
    context_type: ContextType
    content: Any
    confidence: float
    relevance_score: float
    timestamp: float
    source: str
    metadata: Dict[str, Any]


@dataclass
class DecisionContext:
    """Complete context for decision making"""

    decision_id: str
    decision_type: DecisionType
    primary_goal: str
    context_elements: List[ContextElement]
    constraints: List[Dict[str, Any]]
    available_actions: List[Dict[str, Any]]
    risk_factors: List[Dict[str, Any]]
    user_preferences: Dict[str, Any]
    system_state: Dict[str, Any]
    historical_patterns: List[Dict[str, Any]]
    timestamp: float


@dataclass
class Decision:
    """Decision made by the system"""

    decision_id: str
    decision_type: DecisionType
    chosen_action: Dict[str, Any]
    alternative_actions: List[Dict[str, Any]]
    confidence: float
    confidence_level: ConfidenceLevel
    reasoning: str
    supporting_evidence: List[Dict[str, Any]]
    risk_assessment: Dict[str, Any]
    expected_outcomes: List[Dict[str, Any]]
    monitoring_criteria: List[str]
    fallback_plan: Optional[Dict[str, Any]]
    requires_approval: bool
    timestamp: float
    metadata: Dict[str, Any]


class ContextCollector:
    """Collects and manages context information from various sources"""

    def __init__(self):
        self.context_cache: List[ContextElement] = []
        self.max_cache_size = 100
        self.context_relevance_decay = 0.95  # Decay factor per hour

        logger.info("Context Collector initialized")

    async def collect_comprehensive_context(
        self, decision_type: DecisionType, primary_goal: str
    ) -> DecisionContext:
        """Collect comprehensive context for decision making"""

        async with task_tracker.track_task(
            "Context Collection",
            f"Collecting context for {decision_type.value} decision",
            agent_type="context_collector",
            priority=TaskPriority.HIGH,
            inputs={"decision_type": decision_type.value, "goal": primary_goal},
        ) as task_context:
            try:
                decision_id = f"decision_{int(time.time() * 1000)}"
                context_elements = []

                # Collect visual context
                visual_context = await self._collect_visual_context()
                context_elements.extend(visual_context)

                # Collect audio/voice context
                audio_context = await self._collect_audio_context()
                context_elements.extend(audio_context)

                # Collect system state context
                system_context = await self._collect_system_context()
                context_elements.extend(system_context)

                # Collect historical context
                historical_context = await self._collect_historical_context(
                    decision_type
                )
                context_elements.extend(historical_context)

                # Collect environmental context
                environmental_context = await self._collect_environmental_context()
                context_elements.extend(environmental_context)

                # Determine constraints and available actions
                constraints = await self._identify_constraints(
                    decision_type, context_elements
                )
                available_actions = await self._identify_available_actions(
                    decision_type, context_elements
                )
                risk_factors = await self._assess_risk_factors(context_elements)

                # Get user preferences and historical patterns
                user_preferences = await self._get_user_preferences(decision_type)
                historical_patterns = await self._analyze_historical_patterns(
                    decision_type
                )

                # Create decision context
                decision_context = DecisionContext(
                    decision_id=decision_id,
                    decision_type=decision_type,
                    primary_goal=primary_goal,
                    context_elements=context_elements,
                    constraints=constraints,
                    available_actions=available_actions,
                    risk_factors=risk_factors,
                    user_preferences=user_preferences,
                    system_state=await self._get_current_system_state(),
                    historical_patterns=historical_patterns,
                    timestamp=time.time(),
                )

                # Update context cache
                self._update_context_cache(context_elements)

                task_context.set_outputs(
                    {
                        "context_elements": len(context_elements),
                        "available_actions": len(available_actions),
                        "constraints": len(constraints),
                        "risk_factors": len(risk_factors),
                    }
                )

                logger.info(
                    f"Context collected: {len(context_elements)} elements for decision {decision_id}"
                )
                return decision_context

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error(f"Context collection failed: {e}")
                raise

    async def _collect_visual_context(self) -> List[ContextElement]:
        """Collect visual context from screen analysis"""
        try:
            # Get latest screen analysis
            screen_analysis = (
                await computer_vision_system.analyze_and_understand_screen()
            )

            visual_elements = []

            # Screen state context
            if screen_analysis.get("screen_analysis"):
                screen_context = ContextElement(
                    context_id=f"screen_state_{int(time.time())}",
                    context_type=ContextType.VISUAL,
                    content=screen_analysis["screen_analysis"],
                    confidence=screen_analysis["screen_analysis"].get(
                        "confidence_score", 0.8
                    ),
                    relevance_score=0.9,
                    timestamp=time.time(),
                    source="computer_vision_system",
                    metadata={"type": "screen_analysis"},
                )
                visual_elements.append(screen_context)

            # UI elements context
            if screen_analysis.get("ui_elements"):
                ui_context = ContextElement(
                    context_id=f"ui_elements_{int(time.time())}",
                    context_type=ContextType.VISUAL,
                    content=screen_analysis["ui_elements"],
                    confidence=0.8,
                    relevance_score=0.85,
                    timestamp=time.time(),
                    source="computer_vision_system",
                    metadata={
                        "type": "ui_elements",
                        "count": len(screen_analysis["ui_elements"]),
                    },
                )
                visual_elements.append(ui_context)

            # Automation opportunities context
            if screen_analysis.get("automation_opportunities"):
                automation_context = ContextElement(
                    context_id=f"automation_ops_{int(time.time())}",
                    context_type=ContextType.VISUAL,
                    content=screen_analysis["automation_opportunities"],
                    confidence=0.75,
                    relevance_score=0.9,
                    timestamp=time.time(),
                    source="computer_vision_system",
                    metadata={"type": "automation_opportunities"},
                )
                visual_elements.append(automation_context)

            return visual_elements

        except Exception as e:
            logger.debug(f"Visual context collection failed: {e}")
            return []

    async def _collect_audio_context(self) -> List[ContextElement]:
        """Collect audio/voice context"""
        try:
            # Get voice processing system status
            voice_status = voice_processing_system.get_system_status()

            audio_elements = []

            # Recent voice commands context
            if voice_status.get("recent_activity"):
                voice_context = ContextElement(
                    context_id=f"voice_activity_{int(time.time())}",
                    context_type=ContextType.AUDIO,
                    content=voice_status["recent_activity"],
                    confidence=0.8,
                    relevance_score=0.7,
                    timestamp=time.time(),
                    source="voice_processing_system",
                    metadata={"type": "voice_activity"},
                )
                audio_elements.append(voice_context)

            # Command history context
            command_history = voice_processing_system.get_command_history(limit=5)
            if command_history:
                history_context = ContextElement(
                    context_id=f"voice_history_{int(time.time())}",
                    context_type=ContextType.HISTORICAL,
                    content=command_history,
                    confidence=0.9,
                    relevance_score=0.6,
                    timestamp=time.time(),
                    source="voice_processing_system",
                    metadata={"type": "command_history", "count": len(command_history)},
                )
                audio_elements.append(history_context)

            return audio_elements

        except Exception as e:
            logger.debug(f"Audio context collection failed: {e}")
            return []

    async def _collect_system_context(self) -> List[ContextElement]:
        """Collect system state context"""
        try:
            system_elements = []

            # Takeover system status
            takeover_status = takeover_manager.get_system_status()
            takeover_context = ContextElement(
                context_id=f"takeover_status_{int(time.time())}",
                context_type=ContextType.SYSTEM_STATE,
                content=takeover_status,
                confidence=1.0,
                relevance_score=0.8,
                timestamp=time.time(),
                source="takeover_manager",
                metadata={"type": "takeover_status"},
            )
            system_elements.append(takeover_context)

            # Active takeovers
            active_takeovers = takeover_manager.get_active_sessions()
            if active_takeovers:
                active_takeover_context = ContextElement(
                    context_id=f"active_takeovers_{int(time.time())}",
                    context_type=ContextType.SYSTEM_STATE,
                    content=active_takeovers,
                    confidence=1.0,
                    relevance_score=0.95,
                    timestamp=time.time(),
                    source="takeover_manager",
                    metadata={
                        "type": "active_takeovers",
                        "count": len(active_takeovers),
                    },
                )
                system_elements.append(active_takeover_context)

            # System resource information
            try:
                import psutil

                resource_info = {
                    "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_usage": psutil.disk_usage("/").percent,
                }

                resource_context = ContextElement(
                    context_id=f"system_resources_{int(time.time())}",
                    context_type=ContextType.ENVIRONMENTAL,
                    content=resource_info,
                    confidence=1.0,
                    relevance_score=0.6,
                    timestamp=time.time(),
                    source="system_monitor",
                    metadata={"type": "resource_usage"},
                )
                system_elements.append(resource_context)

            except ImportError:
                logger.debug("psutil not available for system resource monitoring")

            return system_elements

        except Exception as e:
            logger.debug(f"System context collection failed: {e}")
            return []

    async def _collect_historical_context(
        self, decision_type: DecisionType
    ) -> List[ContextElement]:
        """Collect relevant historical context"""
        try:
            # This would query the enhanced memory system for relevant historical data
            # For now, return placeholder context
            historical_elements = []

            # Recent similar decisions (placeholder)
            recent_decisions = []  # Would query memory system
            if recent_decisions:
                history_context = ContextElement(
                    context_id=f"decision_history_{int(time.time())}",
                    context_type=ContextType.HISTORICAL,
                    content=recent_decisions,
                    confidence=0.8,
                    relevance_score=0.7,
                    timestamp=time.time(),
                    source="enhanced_memory_system",
                    metadata={
                        "type": "decision_history",
                        "decision_type": decision_type.value,
                    },
                )
                historical_elements.append(history_context)

            return historical_elements

        except Exception as e:
            logger.debug(f"Historical context collection failed: {e}")
            return []

    async def _collect_environmental_context(self) -> List[ContextElement]:
        """Collect environmental context (time, date, system load, etc.)"""
        try:
            current_time = datetime.now()

            temporal_context = ContextElement(
                context_id=f"temporal_{int(time.time())}",
                context_type=ContextType.ENVIRONMENTAL,
                content={
                    "timestamp": time.time(),
                    "datetime": current_time.isoformat(),
                    "hour": current_time.hour,
                    "day_of_week": current_time.weekday(),
                    "is_business_hours": 9 <= current_time.hour <= 17,
                    "is_weekend": current_time.weekday() >= 5,
                },
                confidence=1.0,
                relevance_score=0.5,
                timestamp=time.time(),
                source="system_clock",
                metadata={"type": "temporal_context"},
            )

            return [temporal_context]

        except Exception as e:
            logger.debug(f"Environmental context collection failed: {e}")
            return []

    async def _identify_constraints(
        self, decision_type: DecisionType, context_elements: List[ContextElement]
    ) -> List[Dict[str, Any]]:
        """Identify constraints that limit available actions"""
        constraints = []

        # Check for active takeovers (constraint on autonomous actions)
        active_takeovers = [
            ce
            for ce in context_elements
            if ce.metadata.get("type") == "active_takeovers"
        ]
        if active_takeovers:
            constraints.append(
                {
                    "type": "human_takeover_active",
                    "description": "Human operator has taken control",
                    "severity": "high",
                    "affects": ["automation_action", "navigation_choice"],
                }
            )

        # Check system resources (constraint on resource-intensive actions)
        resource_contexts = [
            ce for ce in context_elements if ce.metadata.get("type") == "resource_usage"
        ]
        for resource_context in resource_contexts:
            resource_info = resource_context.content
            if resource_info.get("cpu_percent", 0) > 80:
                constraints.append(
                    {
                        "type": "high_cpu_usage",
                        "description": f"CPU usage at {resource_info['cpu_percent']}%",
                        "severity": "medium",
                        "affects": ["resource_intensive_tasks"],
                    }
                )

            if resource_info.get("memory_percent", 0) > 85:
                constraints.append(
                    {
                        "type": "high_memory_usage",
                        "description": (
                            f"Memory usage at {resource_info['memory_percent']}%"
                        ),
                        "severity": "high",
                        "affects": ["memory_intensive_operations"],
                    }
                )

        # Time-based constraints
        temporal_contexts = [
            ce
            for ce in context_elements
            if ce.metadata.get("type") == "temporal_context"
        ]
        for temporal_context in temporal_contexts:
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

    async def _identify_available_actions(
        self, decision_type: DecisionType, context_elements: List[ContextElement]
    ) -> List[Dict[str, Any]]:
        """Identify actions available based on current context"""
        available_actions = []

        if decision_type == DecisionType.AUTOMATION_ACTION:
            # Check for automation opportunities
            automation_contexts = [
                ce
                for ce in context_elements
                if ce.metadata.get("type") == "automation_opportunities"
            ]
            for auto_context in automation_contexts:
                opportunities = auto_context.content
                for opportunity in opportunities:
                    available_actions.append(
                        {
                            "action_type": "automation",
                            "action": opportunity.get("automation_action", "unknown"),
                            "target": opportunity.get("element_id"),
                            "confidence": opportunity.get("confidence", 0.5),
                            "description": opportunity.get("description", ""),
                        }
                    )

        elif decision_type == DecisionType.NAVIGATION_CHOICE:
            # Check for navigation options
            ui_contexts = [
                ce
                for ce in context_elements
                if ce.metadata.get("type") == "ui_elements"
            ]
            for ui_context in ui_contexts:
                ui_elements = ui_context.content
                for element in ui_elements:
                    if "click" in element.get("interactions", []):
                        available_actions.append(
                            {
                                "action_type": "navigation",
                                "action": "click_element",
                                "target": element.get("id"),
                                "confidence": element.get("confidence", 0.5),
                                "description": (
                                    f"Click {element.get('text', 'element')}"
                                ),
                            }
                        )

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

    async def _assess_risk_factors(
        self, context_elements: List[ContextElement]
    ) -> List[Dict[str, Any]]:
        """Assess risk factors based on context"""
        risk_factors = []

        # Check for low confidence elements
        low_confidence_elements = [ce for ce in context_elements if ce.confidence < 0.6]
        if (
            len(low_confidence_elements) > len(context_elements) * 0.3
        ):  # More than 30% low confidence
            risk_factors.append(
                {
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
            )

        # Check for system resource constraints
        resource_contexts = [
            ce for ce in context_elements if ce.metadata.get("type") == "resource_usage"
        ]
        for resource_context in resource_contexts:
            resource_info = resource_context.content
            if resource_info.get("cpu_percent", 0) > 90:
                risk_factors.append(
                    {
                        "risk_type": "system_overload",
                        "severity": "high",
                        "probability": 0.9,
                        "description": "System CPU usage critically high",
                        "mitigation": "Defer non-critical operations",
                    }
                )

        # Check for conflicting context
        # (This would be more sophisticated in a real implementation)
        if len(context_elements) > 50:  # Too much context might be conflicting
            risk_factors.append(
                {
                    "risk_type": "information_overload",
                    "severity": "low",
                    "probability": 0.4,
                    "description": "Large amount of context data may contain conflicts",
                    "mitigation": "Prioritize most relevant context elements",
                }
            )

        return risk_factors

    async def _get_user_preferences(
        self, decision_type: DecisionType
    ) -> Dict[str, Any]:
        """Get user preferences relevant to decision type"""
        # This would query a user preference system
        # For now, return default preferences
        default_preferences = {
            "automation_level": "high",
            "confirmation_required": False,
            "risk_tolerance": "medium",
            "preferred_interaction_mode": "autonomous",
            "response_time_priority": "speed",
            "accuracy_vs_speed": "balanced",
        }

        return default_preferences

    async def _analyze_historical_patterns(
        self, decision_type: DecisionType
    ) -> List[Dict[str, Any]]:
        """Analyze historical patterns for similar decisions"""
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
        """Get comprehensive current system state"""
        return {
            "autonomous_mode": True,
            "active_sessions": 0,
            "pending_tasks": 0,
            "system_health": "healthy",
            "last_user_interaction": time.time() - 3600,  # 1 hour ago
            "current_focus": "monitoring",
        }

    def _update_context_cache(self, new_elements: List[ContextElement]):
        """Update the context cache with new elements"""
        self.context_cache.extend(new_elements)

        # Remove oldest elements if cache is too large
        if len(self.context_cache) > self.max_cache_size:
            self.context_cache = self.context_cache[-self.max_cache_size :]

        # Decay relevance scores based on age
        current_time = time.time()
        for element in self.context_cache:
            age_hours = (current_time - element.timestamp) / 3600
            element.relevance_score *= self.context_relevance_decay**age_hours


class DecisionEngine:
    """Core decision making engine"""

    def __init__(self):
        self.decision_algorithms = {
            DecisionType.AUTOMATION_ACTION: self._decide_automation_action,
            DecisionType.NAVIGATION_CHOICE: self._decide_navigation_choice,
            DecisionType.TASK_PRIORITIZATION: self._decide_task_prioritization,
            DecisionType.RISK_ASSESSMENT: self._decide_risk_assessment,
            DecisionType.HUMAN_ESCALATION: self._decide_human_escalation,
            DecisionType.WORKFLOW_OPTIMIZATION: self._decide_workflow_optimization,
        }

        logger.info("Decision Engine initialized")

    async def make_decision(self, decision_context: DecisionContext) -> Decision:
        """Make a decision based on provided context"""

        async with task_tracker.track_task(
            "Decision Making",
            f"Making {decision_context.decision_type.value} decision",
            agent_type="decision_engine",
            priority=TaskPriority.HIGH,
            inputs={
                "decision_type": decision_context.decision_type.value,
                "context_elements": len(decision_context.context_elements),
                "available_actions": len(decision_context.available_actions),
            },
        ) as task_context:
            try:
                # Route to appropriate decision algorithm
                decision_algorithm = self.decision_algorithms.get(
                    decision_context.decision_type, self._decide_default
                )

                # Make the decision
                decision = await decision_algorithm(decision_context)

                # Validate decision
                validated_decision = await self._validate_decision(
                    decision, decision_context
                )

                task_context.set_outputs(
                    {
                        "chosen_action": validated_decision.chosen_action.get(
                            "action", "unknown"
                        ),
                        "confidence": validated_decision.confidence,
                        "confidence_level": validated_decision.confidence_level.value,
                        "requires_approval": validated_decision.requires_approval,
                    }
                )

                logger.info(
                    f"Decision made: {validated_decision.chosen_action.get('action')} (confidence: {validated_decision.confidence:.2f})"
                )
                return validated_decision

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error(f"Decision making failed: {e}")
                raise

    async def _decide_automation_action(self, context: DecisionContext) -> Decision:
        """Decide on automation actions"""

        # Find automation opportunities in context
        automation_actions = [
            action
            for action in context.available_actions
            if action.get("action_type") == "automation"
        ]

        if not automation_actions:
            return await self._create_no_action_decision(
                context, "No automation opportunities available"
            )

        # Score actions based on confidence and context
        scored_actions = []
        for action in automation_actions:
            score = await self._score_automation_action(action, context)
            scored_actions.append((score, action))

        # Sort by score and select best action
        scored_actions.sort(key=lambda x: x[0], reverse=True)
        best_score, best_action = scored_actions[0]

        # Determine confidence level
        confidence = min(best_score, 1.0)
        confidence_level = self._determine_confidence_level(confidence)

        # Assess if approval is required
        requires_approval = await self._requires_approval(
            best_action, context, confidence
        )

        # Generate reasoning
        reasoning = f"Selected {best_action['action']} based on confidence score {best_score:.2f}"
        if requires_approval:
            reasoning += " - requires approval due to low confidence or high risk"

        return Decision(
            decision_id=context.decision_id,
            decision_type=context.decision_type,
            chosen_action=best_action,
            alternative_actions=[
                action for _, action in scored_actions[1:3]
            ],  # Top 2 alternatives
            confidence=confidence,
            confidence_level=confidence_level,
            reasoning=reasoning,
            supporting_evidence=[{"type": "context_analysis", "score": best_score}],
            risk_assessment=await self._assess_action_risk(best_action, context),
            expected_outcomes=[
                {"outcome": "action_completed", "probability": confidence}
            ],
            monitoring_criteria=["action_execution_status", "target_element_response"],
            fallback_plan=(
                {"action": "request_human_takeover"} if confidence < 0.6 else None
            ),
            requires_approval=requires_approval,
            timestamp=time.time(),
            metadata={
                "algorithm": "automation_scoring",
                "total_actions_considered": len(automation_actions),
            },
        )

    async def _score_automation_action(
        self, action: Dict[str, Any], context: DecisionContext
    ) -> float:
        """Score an automation action based on context"""
        base_confidence = action.get("confidence", 0.5)

        # Boost score based on context factors
        score_multipliers = []

        # User preference alignment
        user_prefs = context.user_preferences
        if user_prefs.get("automation_level") == "high":
            score_multipliers.append(1.2)

        # Risk factors penalty
        high_risk_factors = [
            rf for rf in context.risk_factors if rf.get("severity") == "high"
        ]
        if high_risk_factors:
            score_multipliers.append(0.7)

        # Historical success rate
        historical_patterns = context.historical_patterns
        success_pattern = next(
            (p for p in historical_patterns if p.get("pattern_type") == "success_rate"),
            None,
        )
        if success_pattern:
            success_rate = success_pattern.get("success_rate", 0.8)
            score_multipliers.append(success_rate)

        # Apply multipliers
        final_score = base_confidence
        for multiplier in score_multipliers:
            final_score *= multiplier

        return min(final_score, 1.0)  # Cap at 1.0

    async def _decide_navigation_choice(self, context: DecisionContext) -> Decision:
        """Decide on navigation choices"""
        navigation_actions = [
            action
            for action in context.available_actions
            if action.get("action_type") == "navigation"
        ]

        if not navigation_actions:
            return await self._create_no_action_decision(
                context, "No navigation options available"
            )

        # For navigation, prioritize by element text relevance to primary goal
        best_action = navigation_actions[0]  # Simplified selection
        confidence = best_action.get("confidence", 0.7)

        return Decision(
            decision_id=context.decision_id,
            decision_type=context.decision_type,
            chosen_action=best_action,
            alternative_actions=navigation_actions[1:3],
            confidence=confidence,
            confidence_level=self._determine_confidence_level(confidence),
            reasoning="Selected navigation action based on element availability and relevance",
            supporting_evidence=[],
            risk_assessment={"risk_level": "low", "factors": []},
            expected_outcomes=[
                {"outcome": "navigation_completed", "probability": confidence}
            ],
            monitoring_criteria=["navigation_success", "page_load_status"],
            fallback_plan=None,
            requires_approval=False,
            timestamp=time.time(),
            metadata={"algorithm": "navigation_selection"},
        )

    async def _decide_task_prioritization(self, context: DecisionContext) -> Decision:
        """Decide on task prioritization"""
        # This would implement sophisticated task prioritization logic
        # For now, return a placeholder decision
        return await self._create_placeholder_decision(
            context, "Task prioritization algorithm not fully implemented"
        )

    async def _decide_risk_assessment(self, context: DecisionContext) -> Decision:
        """Decide on risk assessment actions"""
        risk_factors = context.risk_factors
        high_risk_factors = [rf for rf in risk_factors if rf.get("severity") == "high"]

        if high_risk_factors:
            # High risk detected - recommend escalation
            escalation_action = {
                "action_type": "escalation",
                "action": "request_human_review",
                "reason": "high_risk_factors_detected",
                "confidence": 0.9,
            }

            return Decision(
                decision_id=context.decision_id,
                decision_type=context.decision_type,
                chosen_action=escalation_action,
                alternative_actions=[],
                confidence=0.9,
                confidence_level=ConfidenceLevel.HIGH,
                reasoning=f"High risk factors detected: {[rf['risk_type'] for rf in high_risk_factors]}",
                supporting_evidence=[
                    {"type": "risk_analysis", "high_risk_count": len(high_risk_factors)}
                ],
                risk_assessment={"risk_level": "high", "factors": high_risk_factors},
                expected_outcomes=[
                    {"outcome": "human_review_requested", "probability": 0.9}
                ],
                monitoring_criteria=["human_response", "risk_mitigation_status"],
                fallback_plan=None,
                requires_approval=False,
                timestamp=time.time(),
                metadata={"algorithm": "risk_assessment"},
            )
        else:
            # Low/medium risk - continue normal operations
            continue_action = {
                "action_type": "monitoring",
                "action": "continue_operations",
                "confidence": 0.8,
            }

            return Decision(
                decision_id=context.decision_id,
                decision_type=context.decision_type,
                chosen_action=continue_action,
                alternative_actions=[],
                confidence=0.8,
                confidence_level=ConfidenceLevel.HIGH,
                reasoning="Risk factors within acceptable limits",
                supporting_evidence=[
                    {"type": "risk_analysis", "risk_level": "acceptable"}
                ],
                risk_assessment={"risk_level": "low", "factors": risk_factors},
                expected_outcomes=[
                    {"outcome": "continued_operation", "probability": 0.8}
                ],
                monitoring_criteria=["risk_factor_changes", "system_performance"],
                fallback_plan=None,
                requires_approval=False,
                timestamp=time.time(),
                metadata={"algorithm": "risk_assessment"},
            )

    async def _decide_human_escalation(self, context: DecisionContext) -> Decision:
        """Decide whether to escalate to human"""
        escalation_actions = [
            action
            for action in context.available_actions
            if action.get("action_type") == "escalation"
        ]

        # Analyze context to determine escalation urgency
        urgency_factors = []

        # Check for active takeovers
        if any(
            "takeover" in ce.metadata.get("type", "") for ce in context.context_elements
        ):
            urgency_factors.append("existing_takeover")

        # Check for high risk factors
        high_risk_factors = [
            rf for rf in context.risk_factors if rf.get("severity") == "high"
        ]
        if high_risk_factors:
            urgency_factors.append("high_risk_detected")

        # Check for low confidence context
        low_confidence_elements = [
            ce for ce in context.context_elements if ce.confidence < 0.5
        ]
        if len(low_confidence_elements) > len(context.context_elements) * 0.4:
            urgency_factors.append("low_confidence_context")

        if urgency_factors:
            # Escalate immediately
            escalation_action = {
                "action_type": "escalation",
                "action": "request_immediate_takeover",
                "trigger": "critical_decision_point",
                "urgency_factors": urgency_factors,
                "confidence": 0.95,
            }

            return Decision(
                decision_id=context.decision_id,
                decision_type=context.decision_type,
                chosen_action=escalation_action,
                alternative_actions=[],
                confidence=0.95,
                confidence_level=ConfidenceLevel.VERY_HIGH,
                reasoning=f"Immediate escalation required due to: {', '.join(urgency_factors)}",
                supporting_evidence=[
                    {"type": "urgency_analysis", "factors": urgency_factors}
                ],
                risk_assessment={
                    "risk_level": "high",
                    "immediate_action_required": True,
                },
                expected_outcomes=[
                    {"outcome": "human_takeover_initiated", "probability": 0.95}
                ],
                monitoring_criteria=[
                    "takeover_response_time",
                    "human_operator_availability",
                ],
                fallback_plan={"action": "pause_all_operations"},
                requires_approval=False,  # Emergency escalation doesn't require approval
                timestamp=time.time(),
                metadata={"algorithm": "escalation_urgency_analysis"},
            )
        else:
            # No immediate escalation needed
            continue_action = {
                "action_type": "monitoring",
                "action": "continue_autonomous_operation",
                "confidence": 0.8,
            }

            return Decision(
                decision_id=context.decision_id,
                decision_type=context.decision_type,
                chosen_action=continue_action,
                alternative_actions=escalation_actions,
                confidence=0.8,
                confidence_level=ConfidenceLevel.HIGH,
                reasoning="No immediate escalation factors detected",
                supporting_evidence=[
                    {"type": "escalation_analysis", "urgency_factors": []}
                ],
                risk_assessment={"risk_level": "low", "escalation_needed": False},
                expected_outcomes=[
                    {"outcome": "continued_autonomous_operation", "probability": 0.8}
                ],
                monitoring_criteria=["context_changes", "risk_factor_evolution"],
                fallback_plan={"action": "request_human_review"},
                requires_approval=False,
                timestamp=time.time(),
                metadata={"algorithm": "escalation_analysis"},
            )

    async def _decide_workflow_optimization(self, context: DecisionContext) -> Decision:
        """Decide on workflow optimization actions"""
        return await self._create_placeholder_decision(
            context, "Workflow optimization algorithm not fully implemented"
        )

    async def _decide_default(self, context: DecisionContext) -> Decision:
        """Default decision algorithm for unhandled decision types"""
        return await self._create_no_action_decision(
            context, f"No algorithm available for {context.decision_type.value}"
        )

    async def _create_no_action_decision(
        self, context: DecisionContext, reason: str
    ) -> Decision:
        """Create a decision to take no action"""
        no_action = {
            "action_type": "none",
            "action": "no_action",
            "reason": reason,
            "confidence": 1.0,
        }

        return Decision(
            decision_id=context.decision_id,
            decision_type=context.decision_type,
            chosen_action=no_action,
            alternative_actions=[],
            confidence=1.0,
            confidence_level=ConfidenceLevel.VERY_HIGH,
            reasoning=reason,
            supporting_evidence=[],
            risk_assessment={"risk_level": "none", "factors": []},
            expected_outcomes=[{"outcome": "no_change", "probability": 1.0}],
            monitoring_criteria=[],
            fallback_plan=None,
            requires_approval=False,
            timestamp=time.time(),
            metadata={"algorithm": "no_action"},
        )

    async def _create_placeholder_decision(
        self, context: DecisionContext, reason: str
    ) -> Decision:
        """Create a placeholder decision for unimplemented algorithms"""
        placeholder_action = {
            "action_type": "placeholder",
            "action": "algorithm_not_implemented",
            "reason": reason,
            "confidence": 0.5,
        }

        return Decision(
            decision_id=context.decision_id,
            decision_type=context.decision_type,
            chosen_action=placeholder_action,
            alternative_actions=[],
            confidence=0.5,
            confidence_level=ConfidenceLevel.MEDIUM,
            reasoning=reason,
            supporting_evidence=[],
            risk_assessment={"risk_level": "unknown", "factors": []},
            expected_outcomes=[],
            monitoring_criteria=[],
            fallback_plan={"action": "request_human_guidance"},
            requires_approval=True,  # Placeholder decisions should be reviewed
            timestamp=time.time(),
            metadata={"algorithm": "placeholder"},
        )

    async def _validate_decision(
        self, decision: Decision, context: DecisionContext
    ) -> Decision:
        """Validate and potentially modify decision before returning"""

        # Check for constraint violations
        violated_constraints = []
        for constraint in context.constraints:
            if await self._violates_constraint(decision.chosen_action, constraint):
                violated_constraints.append(constraint)

        if violated_constraints:
            # Modify decision to account for constraint violations
            decision.confidence *= 0.7  # Reduce confidence
            decision.confidence_level = self._determine_confidence_level(
                decision.confidence
            )
            decision.requires_approval = True
            decision.reasoning += f" - Modified due to constraint violations: {[c['type'] for c in violated_constraints]}"

            # Add fallback plan if not present
            if not decision.fallback_plan:
                decision.fallback_plan = {"action": "request_constraint_resolution"}

        return decision

    async def _violates_constraint(
        self, action: Dict[str, Any], constraint: Dict[str, Any]
    ) -> bool:
        """Check if an action violates a constraint"""
        constraint_type = constraint.get("type")
        action_type = action.get("action_type")

        # Check constraint affects
        affects = constraint.get("affects", [])
        if action_type in affects:
            return True

        # Specific constraint checks
        if constraint_type == "human_takeover_active" and action_type == "automation":
            return True

        if constraint_type in ["high_cpu_usage", "high_memory_usage"] and action.get(
            "resource_intensive", False
        ):
            return True

        return False

    async def _requires_approval(
        self, action: Dict[str, Any], context: DecisionContext, confidence: float
    ) -> bool:
        """Determine if an action requires human approval"""

        # Low confidence requires approval
        if confidence < 0.6:
            return True

        # High risk actions require approval
        if any(rf.get("severity") == "high" for rf in context.risk_factors):
            return True

        # User preference for confirmations
        if context.user_preferences.get("confirmation_required", False):
            return True

        # Specific action types that require approval
        high_risk_actions = [
            "shutdown",
            "delete",
            "uninstall",
            "modify_system_settings",
        ]
        if action.get("action") in high_risk_actions:
            return True

        return False

    async def _assess_action_risk(
        self, action: Dict[str, Any], context: DecisionContext
    ) -> Dict[str, Any]:
        """Assess risk of executing an action"""
        risk_level = "low"
        risk_factors = []

        # Check action confidence
        if action.get("confidence", 1.0) < 0.5:
            risk_level = "medium"
            risk_factors.append("low_action_confidence")

        # Check context risks
        high_context_risks = [
            rf for rf in context.risk_factors if rf.get("severity") == "high"
        ]
        if high_context_risks:
            risk_level = "high"
            risk_factors.extend([rf["risk_type"] for rf in high_context_risks])

        return {
            "risk_level": risk_level,
            "factors": risk_factors,
            "mitigation_required": risk_level in ["medium", "high"],
        }

    def _determine_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Convert numeric confidence to confidence level enum"""
        if confidence >= 0.9:
            return ConfidenceLevel.VERY_HIGH
        elif confidence >= 0.7:
            return ConfidenceLevel.HIGH
        elif confidence >= 0.5:
            return ConfidenceLevel.MEDIUM
        elif confidence >= 0.3:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW


class ContextAwareDecisionSystem:
    """Main context-aware decision making system"""

    def __init__(self, memory_manager: Optional[EnhancedMemoryManager] = None):
        self.memory_manager = memory_manager or EnhancedMemoryManager()
        self.context_collector = ContextCollector()
        self.decision_engine = DecisionEngine()

        # Decision history
        self.decision_history: List[Decision] = []
        self.max_history = 50

        logger.info("Context-Aware Decision System initialized")

    async def make_contextual_decision(
        self, decision_type: DecisionType, primary_goal: str
    ) -> Decision:
        """Make a decision considering comprehensive context"""

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
                self.decision_history.append(decision)
                if len(self.decision_history) > self.max_history:
                    self.decision_history = self.decision_history[-self.max_history :]

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
                    f"Contextual decision made: {decision.chosen_action.get('action')} (confidence: {decision.confidence:.2f})"
                )
                return decision

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error(f"Contextual decision making failed: {e}")
                raise

    async def _store_decision_in_memory(
        self, decision: Decision, context: DecisionContext
    ):
        """Store decision and context in enhanced memory system"""
        try:
            # Create memory task record for the decision
            task_id = self.memory_manager.create_task_record(
                task_name=f"Decision: {decision.decision_type.value}",
                description=f"Contextual decision making: {decision.chosen_action.get('action', 'unknown')}",
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
            logger.error(f"Failed to store decision in memory: {e}")

    def get_decision_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get recent decision history"""
        history = self.decision_history
        if limit:
            history = history[-limit:]

        return [
            {
                "decision_id": decision.decision_id,
                "type": decision.decision_type.value,
                "action": decision.chosen_action.get("action", "unknown"),
                "confidence": decision.confidence,
                "timestamp": decision.timestamp,
                "requires_approval": decision.requires_approval,
            }
            for decision in history
        ]

    def get_system_status(self) -> Dict[str, Any]:
        """Get decision system status"""
        recent_decisions = self.decision_history[-10:] if self.decision_history else []

        return {
            "total_decisions": len(self.decision_history),
            "recent_decisions_count": len(recent_decisions),
            "average_confidence": (
                np.mean([d.confidence for d in recent_decisions])
                if recent_decisions
                else 0.0
            ),
            "approval_required_rate": (
                np.mean([d.requires_approval for d in recent_decisions])
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


# Global instance
context_aware_decision_system = ContextAwareDecisionSystem()
