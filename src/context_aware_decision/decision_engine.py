# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Decision Engine

Core decision making engine for the context-aware decision system.
Routes to appropriate decision algorithms based on decision type.

Part of Issue #381 - God Class Refactoring
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List

from src.enhanced_memory_manager_async import TaskPriority
from src.task_execution_tracker import task_tracker

from .models import Decision, DecisionContext
from .time_provider import TimeProvider
from .types import (
    ConfidenceLevel,
    DecisionType,
    HIGH_RESOURCE_CONSTRAINT_TYPES,
    HIGH_RISK_ACTIONS,
    MITIGATION_REQUIRED_RISK_LEVELS,
)

logger = logging.getLogger(__name__)


class DecisionEngine:
    """Core decision making engine."""

    def __init__(self):
        """Initialize decision engine with algorithm registry and time provider."""
        self.time_provider = TimeProvider()
        self.decision_algorithms: Dict[
            DecisionType, Callable[[DecisionContext], Decision]
        ] = {
            DecisionType.AUTOMATION_ACTION: self._decide_automation_action,
            DecisionType.NAVIGATION_CHOICE: self._decide_navigation_choice,
            DecisionType.TASK_PRIORITIZATION: self._decide_task_prioritization,
            DecisionType.RISK_ASSESSMENT: self._decide_risk_assessment,
            DecisionType.HUMAN_ESCALATION: self._decide_human_escalation,
            DecisionType.WORKFLOW_OPTIMIZATION: self._decide_workflow_optimization,
        }

        logger.info("Decision Engine initialized")

    async def make_decision(self, decision_context: DecisionContext) -> Decision:
        """Make a decision based on provided context."""

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
                    f"Decision made: {validated_decision.chosen_action.get('action')} "
                    f"(confidence: {validated_decision.confidence:.2f})"
                )
                return validated_decision

            except Exception as e:
                task_context.set_outputs({"error": str(e)})
                logger.error("Decision making failed: %s", e)
                raise

    async def _score_and_sort_automation_actions(
        self, automation_actions: List[Dict[str, Any]], context: DecisionContext
    ) -> List[tuple]:
        """Issue #665: Extracted from _decide_automation_action to reduce function length.

        Scores automation actions in parallel and returns sorted list.

        Args:
            automation_actions: List of automation action dictionaries.
            context: Decision context for scoring.

        Returns:
            List of (score, action) tuples sorted by score descending.
        """
        scores = await asyncio.gather(
            *[self._score_automation_action(action, context) for action in automation_actions],
            return_exceptions=True,
        )
        scored_actions = [
            (score, action)
            for score, action in zip(scores, automation_actions)
            if not isinstance(score, Exception)
        ]
        scored_actions.sort(key=lambda x: x[0], reverse=True)
        return scored_actions

    async def _build_automation_decision(
        self,
        context: DecisionContext,
        best_score: float,
        best_action: Dict[str, Any],
        scored_actions: List[tuple],
        action_count: int,
    ) -> Decision:
        """Issue #665: Extracted from _decide_automation_action to reduce function length.

        Builds the Decision object for automation actions.
        """
        confidence = min(best_score, 1.0)
        confidence_level = self._determine_confidence_level(confidence)
        requires_approval = await self._requires_approval(best_action, context, confidence)

        reasoning = f"Selected {best_action['action']} based on confidence score {best_score:.2f}"
        if requires_approval:
            reasoning += " - requires approval due to low confidence or high risk"

        return Decision(
            decision_id=context.decision_id,
            decision_type=context.decision_type,
            chosen_action=best_action,
            alternative_actions=[action for _, action in scored_actions[1:3]],
            confidence=confidence,
            confidence_level=confidence_level,
            reasoning=reasoning,
            supporting_evidence=[{"type": "context_analysis", "score": best_score}],
            risk_assessment=await self._assess_action_risk(best_action, context),
            expected_outcomes=[{"outcome": "action_completed", "probability": confidence}],
            monitoring_criteria=["action_execution_status", "target_element_response"],
            fallback_plan={"action": "request_human_takeover"} if confidence < 0.6 else None,
            requires_approval=requires_approval,
            timestamp=self.time_provider.current_timestamp(),
            metadata={"algorithm": "automation_scoring", "total_actions_considered": action_count},
        )

    async def _decide_automation_action(self, context: DecisionContext) -> Decision:
        """Decide on automation actions."""
        automation_actions = [
            action
            for action in context.available_actions
            if action.get("action_type") == "automation"
        ]

        if not automation_actions:
            return await self._create_no_action_decision(
                context, "No automation opportunities available"
            )

        # Issue #370: Score actions in parallel instead of sequentially
        scored_actions = await self._score_and_sort_automation_actions(
            automation_actions, context
        )

        if not scored_actions:
            return await self._create_no_action_decision(
                context, "Failed to score automation actions"
            )

        best_score, best_action = scored_actions[0]

        return await self._build_automation_decision(
            context, best_score, best_action, scored_actions, len(automation_actions)
        )

    async def _score_automation_action(
        self, action: Dict[str, Any], context: DecisionContext
    ) -> float:
        """Score an automation action based on context."""
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
        """Decide on navigation choices."""
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
            timestamp=self.time_provider.current_timestamp(),
            metadata={"algorithm": "navigation_selection"},
        )

    def _score_task_for_prioritization(self, task: Dict[str, Any]) -> float:
        """Issue #665: Extracted from _decide_task_prioritization to reduce function length.

        Scores a task based on urgency, importance, and dependencies.

        Args:
            task: Task dictionary containing urgency, importance, and dependencies info.

        Returns:
            Float score between 0.1 and 1.0 indicating task priority.
        """
        score = 0.5  # Base score

        # Urgency factors
        if task.get("urgent", False):
            score += 0.3
        if task.get("deadline"):
            score += 0.2

        # Importance factors
        importance = task.get("importance", "medium")
        if importance == "high":
            score += 0.2
        elif importance == "critical":
            score += 0.4

        # Dependencies - tasks with fewer blockers get priority
        dependencies = task.get("dependencies", [])
        if len(dependencies) == 0:
            score += 0.1

        return min(score, 1.0)

    def _build_task_prioritization_decision(
        self,
        context: DecisionContext,
        best_score: float,
        prioritized_task: Dict[str, Any],
        scored_tasks: List[tuple],
        task_count: int,
    ) -> Decision:
        """Issue #665: Extracted from _decide_task_prioritization to reduce function length.

        Builds the Decision object for task prioritization.
        """
        confidence = best_score
        confidence_level = self._determine_confidence_level(confidence)

        return Decision(
            decision_id=context.decision_id,
            decision_type=context.decision_type,
            chosen_action={
                "action_type": "prioritization",
                "action": "prioritize_task",
                "task": prioritized_task,
                "priority_score": best_score,
                "confidence": confidence,
            },
            alternative_actions=[task for _, task in scored_tasks[1:3]],
            confidence=confidence,
            confidence_level=confidence_level,
            reasoning=f"Prioritized based on urgency, importance, and dependencies (score: {best_score:.2f})",
            supporting_evidence=[
                {"type": "prioritization_analysis", "tasks_considered": task_count}
            ],
            risk_assessment={"risk_level": "low", "factors": []},
            expected_outcomes=[
                {"outcome": "task_prioritized", "probability": confidence}
            ],
            monitoring_criteria=["task_execution_progress", "deadline_adherence"],
            fallback_plan=None,
            requires_approval=False,
            timestamp=self.time_provider.current_timestamp(),
            metadata={
                "algorithm": "task_prioritization",
                "total_tasks": task_count,
            },
        )

    async def _decide_task_prioritization(self, context: DecisionContext) -> Decision:
        """Decide on task prioritization based on context elements and constraints."""
        # Find tasks to prioritize in available actions
        task_actions = [
            action
            for action in context.available_actions
            if action.get("action_type") in ("task", "prioritization", "scheduling")
        ]

        if not task_actions:
            return await self._create_no_action_decision(
                context, "No tasks available for prioritization"
            )

        # Score tasks based on urgency, importance, and context
        scored_tasks = [
            (self._score_task_for_prioritization(task), task) for task in task_actions
        ]

        # Sort by score (highest first)
        scored_tasks.sort(key=lambda x: x[0], reverse=True)
        best_score, prioritized_task = scored_tasks[0]

        return self._build_task_prioritization_decision(
            context, best_score, prioritized_task, scored_tasks, len(task_actions)
        )

    async def _decide_risk_assessment(self, context: DecisionContext) -> Decision:
        """Decide on risk assessment actions."""
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
                reasoning=(
                    f"High risk factors detected: "
                    f"{[rf['risk_type'] for rf in high_risk_factors]}"
                ),
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
                timestamp=self.time_provider.current_timestamp(),
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
                timestamp=self.time_provider.current_timestamp(),
                metadata={"algorithm": "risk_assessment"},
            )

    def _analyze_escalation_urgency(self, context: DecisionContext) -> List[str]:
        """Analyze context elements to determine escalation urgency factors (Issue #398: extracted).

        Returns:
            List of urgency factor strings that triggered escalation need
        """
        urgency_factors = []

        # Check for active takeovers
        if any("takeover" in ce.metadata.get("type", "") for ce in context.context_elements):
            urgency_factors.append("existing_takeover")

        # Check for high risk factors
        if any(rf.get("severity") == "high" for rf in context.risk_factors):
            urgency_factors.append("high_risk_detected")

        # Check for low confidence context (>40% of elements have low confidence)
        low_confidence_count = sum(1 for ce in context.context_elements if ce.confidence < 0.5)
        if context.context_elements and low_confidence_count > len(context.context_elements) * 0.4:
            urgency_factors.append("low_confidence_context")

        return urgency_factors

    def _create_escalation_decision(self, context: DecisionContext, urgency_factors: List[str]) -> Decision:
        """Create decision for immediate escalation (Issue #398: extracted)."""
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
            supporting_evidence=[{"type": "urgency_analysis", "factors": urgency_factors}],
            risk_assessment={"risk_level": "high", "immediate_action_required": True},
            expected_outcomes=[{"outcome": "human_takeover_initiated", "probability": 0.95}],
            monitoring_criteria=["takeover_response_time", "human_operator_availability"],
            fallback_plan={"action": "pause_all_operations"},
            requires_approval=False,
            timestamp=self.time_provider.current_timestamp(),
            metadata={"algorithm": "escalation_urgency_analysis"},
        )

    def _create_continue_autonomous_decision(self, context: DecisionContext,
                                             escalation_actions: List[Dict]) -> Decision:
        """Create decision to continue autonomous operation (Issue #398: extracted)."""
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
            supporting_evidence=[{"type": "escalation_analysis", "urgency_factors": []}],
            risk_assessment={"risk_level": "low", "escalation_needed": False},
            expected_outcomes=[{"outcome": "continued_autonomous_operation", "probability": 0.8}],
            monitoring_criteria=["context_changes", "risk_factor_evolution"],
            fallback_plan={"action": "request_human_review"},
            requires_approval=False,
            timestamp=self.time_provider.current_timestamp(),
            metadata={"algorithm": "escalation_analysis"},
        )

    async def _decide_human_escalation(self, context: DecisionContext) -> Decision:
        """Decide whether to escalate to human (Issue #398: refactored to use helpers)."""
        escalation_actions = [
            action for action in context.available_actions
            if action.get("action_type") == "escalation"
        ]

        urgency_factors = self._analyze_escalation_urgency(context)

        if urgency_factors:
            return self._create_escalation_decision(context, urgency_factors)
        else:
            return self._create_continue_autonomous_decision(context, escalation_actions)

    def _score_optimization_action(self, opt: Dict[str, Any]) -> float:
        """Issue #665: Extracted from _decide_workflow_optimization to reduce function length.

        Scores an optimization action based on efficiency gain, risk level, and complexity.

        Args:
            opt: Optimization action dictionary.

        Returns:
            Float score between 0.1 and 1.0 indicating optimization priority.
        """
        score = 0.5  # Base score

        # Efficiency impact
        efficiency_gain = opt.get("efficiency_gain", 0)
        score += min(efficiency_gain / 100, 0.3)

        # Risk level - lower risk = higher score
        risk = opt.get("risk_level", "medium")
        if risk == "low":
            score += 0.2
        elif risk == "high":
            score -= 0.1

        # Implementation complexity - simpler = higher score
        complexity = opt.get("complexity", "medium")
        if complexity == "low":
            score += 0.1
        elif complexity == "high":
            score -= 0.1

        return min(max(score, 0.1), 1.0)

    def _build_workflow_optimization_decision(
        self,
        context: DecisionContext,
        best_score: float,
        best_optimization: Dict[str, Any],
        scored_optimizations: List[tuple],
        optimization_count: int,
    ) -> Decision:
        """Issue #665: Extracted from _decide_workflow_optimization to reduce function length.

        Builds the Decision object for workflow optimization.
        """
        confidence = best_score
        confidence_level = self._determine_confidence_level(confidence)

        return Decision(
            decision_id=context.decision_id,
            decision_type=context.decision_type,
            chosen_action={
                "action_type": "optimization",
                "action": "apply_workflow_optimization",
                "optimization": best_optimization,
                "optimization_score": best_score,
                "confidence": confidence,
            },
            alternative_actions=[opt for _, opt in scored_optimizations[1:3]],
            confidence=confidence,
            confidence_level=confidence_level,
            reasoning=f"Selected workflow optimization based on efficiency, risk, and complexity analysis (score: {best_score:.2f})",
            supporting_evidence=[
                {"type": "workflow_analysis", "optimizations_found": optimization_count}
            ],
            risk_assessment={"risk_level": best_optimization.get("risk_level", "low"), "factors": []},
            expected_outcomes=[
                {"outcome": "workflow_optimized", "probability": confidence},
                {"outcome": "efficiency_improved", "probability": confidence * 0.8},
            ],
            monitoring_criteria=["workflow_performance", "efficiency_metrics"],
            fallback_plan={"action": "revert_optimization"} if best_score < 0.6 else None,
            requires_approval=best_score < 0.7,  # Low confidence optimizations need approval
            timestamp=self.time_provider.current_timestamp(),
            metadata={
                "algorithm": "workflow_optimization",
                "optimizations_considered": optimization_count,
            },
        )

    async def _decide_workflow_optimization(self, context: DecisionContext) -> Decision:
        """Decide on workflow optimization actions based on context analysis."""
        # Find optimization opportunities in available actions
        optimization_actions = [
            action
            for action in context.available_actions
            if action.get("action_type") in ("optimization", "workflow", "efficiency")
        ]

        if not optimization_actions:
            # Analyze context for implicit optimization opportunities
            optimization_suggestions = self._analyze_workflow_for_optimization(context)
            if not optimization_suggestions:
                return await self._create_no_action_decision(
                    context, "No workflow optimization opportunities identified"
                )
            optimization_actions = optimization_suggestions

        # Score optimization actions
        scored_optimizations = [
            (self._score_optimization_action(opt), opt) for opt in optimization_actions
        ]

        # Sort by score
        scored_optimizations.sort(key=lambda x: x[0], reverse=True)
        best_score, best_optimization = scored_optimizations[0]

        return self._build_workflow_optimization_decision(
            context, best_score, best_optimization, scored_optimizations, len(optimization_actions)
        )

    def _analyze_workflow_for_optimization(
        self, context: DecisionContext
    ) -> List[Dict[str, Any]]:
        """Analyze context to find implicit optimization opportunities."""
        opportunities = []

        # Check for bottleneck patterns
        context_elements = context.context_elements
        for element in context_elements:
            if element.element_type.value == "performance":
                data = element.data
                if data.get("bottleneck_detected"):
                    opportunities.append({
                        "action_type": "optimization",
                        "action": "resolve_bottleneck",
                        "target": data.get("bottleneck_location"),
                        "efficiency_gain": 20,
                        "risk_level": "medium",
                        "complexity": "medium",
                    })

        # Check for parallel execution opportunities
        for element in context_elements:
            if element.element_type.value == "workflow":
                data = element.data
                if data.get("sequential_steps", 0) > 3:
                    opportunities.append({
                        "action_type": "optimization",
                        "action": "parallelize_steps",
                        "efficiency_gain": 30,
                        "risk_level": "low",
                        "complexity": "medium",
                    })

        return opportunities

    async def _decide_default(self, context: DecisionContext) -> Decision:
        """Default decision algorithm for unhandled decision types."""
        return await self._create_no_action_decision(
            context, f"No algorithm available for {context.decision_type.value}"
        )

    async def _create_no_action_decision(
        self, context: DecisionContext, reason: str
    ) -> Decision:
        """Create a decision to take no action."""
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
            timestamp=self.time_provider.current_timestamp(),
            metadata={"algorithm": "no_action"},
        )

    async def _validate_decision(
        self, decision: Decision, context: DecisionContext
    ) -> Decision:
        """Validate and potentially modify decision before returning."""

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
            decision.reasoning += (
                f" - Modified due to constraint violations: "
                f"{[c['type'] for c in violated_constraints]}"
            )

            # Add fallback plan if not present
            if not decision.fallback_plan:
                decision.fallback_plan = {"action": "request_constraint_resolution"}

        return decision

    async def _violates_constraint(
        self, action: Dict[str, Any], constraint: Dict[str, Any]
    ) -> bool:
        """Check if an action violates a constraint."""
        constraint_type = constraint.get("type")
        action_type = action.get("action_type")

        # Check constraint affects
        affects = constraint.get("affects", [])
        if action_type in affects:
            return True

        # Specific constraint checks
        if constraint_type == "human_takeover_active" and action_type == "automation":
            return True

        # O(1) lookup (Issue #326)
        if constraint_type in HIGH_RESOURCE_CONSTRAINT_TYPES and action.get(
            "resource_intensive", False
        ):
            return True

        return False

    async def _requires_approval(
        self, action: Dict[str, Any], context: DecisionContext, confidence: float
    ) -> bool:
        """Determine if an action requires human approval."""

        # Low confidence requires approval
        if confidence < 0.6:
            return True

        # High risk actions require approval
        if any(rf.get("severity") == "high" for rf in context.risk_factors):
            return True

        # User preference for confirmations
        if context.user_preferences.get("confirmation_required", False):
            return True

        # Specific action types that require approval (O(1) lookup)
        if action.get("action") in HIGH_RISK_ACTIONS:
            return True

        return False

    async def _assess_action_risk(
        self, action: Dict[str, Any], context: DecisionContext
    ) -> Dict[str, Any]:
        """Assess risk of executing an action."""
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
            # O(1) lookup (Issue #326)
            "mitigation_required": risk_level in MITIGATION_REQUIRED_RISK_LEVELS,
        }

    def _determine_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """Convert numeric confidence to confidence level enum."""
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
