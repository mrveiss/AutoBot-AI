# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Context-Aware Decision Models

Dataclass definitions for context elements, decision contexts, and decisions.

Part of Issue #381 - God Class Refactoring
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .types import ConfidenceLevel, ContextType, DecisionType


@dataclass
class ContextElement:
    """Individual piece of context information."""

    context_id: str
    context_type: ContextType
    content: Any
    confidence: float
    relevance_score: float
    timestamp: float
    source: str
    metadata: Dict[str, Any]

    def is_low_confidence(self, threshold: float = 0.6) -> bool:
        """Check if this element has low confidence."""
        return self.confidence < threshold

    def get_age_hours(self) -> float:
        """Get age of this context element in hours."""
        return (time.time() - self.timestamp) / 3600

    def apply_relevance_decay(self, decay_factor: float = 0.95) -> None:
        """Apply time-based relevance decay."""
        age_hours = self.get_age_hours()
        self.relevance_score *= decay_factor**age_hours

    def is_type(self, metadata_type: str) -> bool:
        """Check if element matches a specific metadata type."""
        return self.metadata.get("type") == metadata_type

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "context_id": self.context_id,
            "context_type": self.context_type.value,
            "content": self.content,
            "confidence": self.confidence,
            "relevance_score": self.relevance_score,
            "timestamp": self.timestamp,
            "source": self.source,
            "metadata": self.metadata,
        }


@dataclass
class DecisionContext:
    """Complete context for decision making."""

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

    def get_elements_by_type(
        self,
        context_type: ContextType,
    ) -> List[ContextElement]:
        """Get context elements filtered by type."""
        return [ce for ce in self.context_elements if ce.context_type == context_type]

    def get_elements_by_metadata_type(
        self,
        metadata_type: str,
    ) -> List[ContextElement]:
        """Get context elements filtered by metadata type."""
        return [ce for ce in self.context_elements if ce.metadata.get("type") == metadata_type]

    def get_high_risk_factors(self) -> List[Dict[str, Any]]:
        """Get high-severity risk factors."""
        return [rf for rf in self.risk_factors if rf.get("severity") == "high"]

    def has_constraint(self, constraint_type: str) -> bool:
        """Check if a specific constraint type is present."""
        return any(c.get("type") == constraint_type for c in self.constraints)


@dataclass
class InterventionOutcome:
    """Predicted outcome of a decision intervention (counterfactual).

    Used by CounterfactualReasoner to predict what would happen if we took
    a particular decision option without actually executing it.
    """

    option: str
    predicted_success_rate: float
    side_effects: List[Dict[str, Any]]
    confidence: float
    reasoning: str
    prediction_source: str  # "empirical", "causal", or "heuristic"
    supporting_evidence: List[Dict[str, Any]]
    fallback_risk: str | None = None
    estimated_latency_ms: int | None = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert intervention outcome to dictionary representation."""
        return {
            "option": self.option,
            "predicted_success_rate": self.predicted_success_rate,
            "side_effects": self.side_effects,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "prediction_source": self.prediction_source,
            "supporting_evidence": self.supporting_evidence,
            "fallback_risk": self.fallback_risk,
            "estimated_latency_ms": self.estimated_latency_ms,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    def is_high_confidence(self, threshold: float = 0.7) -> bool:
        """Check if outcome prediction has high confidence."""
        return self.confidence >= threshold

    def has_high_risk_side_effects(self) -> bool:
        """Check if any side effects are high severity."""
        return any(effect.get("severity") == "high" for effect in self.side_effects)


@dataclass
class Decision:
    """Decision made by the system."""

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
    fallback_plan: Dict[str, Any] | None
    requires_approval: bool
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary representation."""
        return {
            "decision_id": self.decision_id,
            "decision_type": self.decision_type.value,
            "chosen_action": self.chosen_action,
            "alternative_actions": self.alternative_actions,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "reasoning": self.reasoning,
            "supporting_evidence": self.supporting_evidence,
            "risk_assessment": self.risk_assessment,
            "expected_outcomes": self.expected_outcomes,
            "monitoring_criteria": self.monitoring_criteria,
            "fallback_plan": self.fallback_plan,
            "requires_approval": self.requires_approval,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    def is_high_confidence(self) -> bool:
        """Check if decision has high confidence."""
        return self.confidence >= 0.7

    def get_action_name(self) -> str:
        """Get the name of the chosen action."""
        return self.chosen_action.get("action", "unknown")

    def get_summary(self) -> Dict[str, Any]:
        """Get a brief summary of the decision."""
        return {
            "decision_id": self.decision_id,
            "type": self.decision_type.value,
            "action": self.get_action_name(),
            "confidence": self.confidence,
            "requires_approval": self.requires_approval,
            "timestamp": self.timestamp,
        }
