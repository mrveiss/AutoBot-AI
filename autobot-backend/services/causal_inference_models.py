# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The causal-inference engine's data model: interventions and the analysis report.

Split out of ``causal_inference_engine.py`` (#13422) to keep that file under its size
ceiling; the engine re-exports these names, so importers are unchanged.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List

from autobot_shared.risk_tier import presented_risk_tier_value
from autobot_shared.status_enums import Severity as CausalSeverity
from services.root_cause_analyzer import CausalEvent


class RecommendationType(str, Enum):
    """Recommendation action types and timeframes."""

    IMMEDIATE = "immediate"  # Execute now (low cost, likely to fix)
    SHORT_TERM = "short_term"  # Hours to days (medium cost, prevents root cause)
    LONG_TERM = "long_term"  # Weeks to months (high cost, architectural fix)


@dataclass
class Intervention:
    """A single intervention that could prevent the failure."""

    name: str
    description: str
    mechanism: str  # Why this would fix the issue
    predicted_success_rate: float  # 0.0-1.0 likelihood this fixes it
    cost_level: str  # "low", "medium", "high"
    risk_level: str  # "low", "medium", "high"
    recommendation_type: RecommendationType
    impact_rank: int  # 1-based ranking (1 = highest impact)
    confidence: float  # How confident in this prediction (0.0-1.0)
    evidence: List[str] = field(default_factory=list)  # Why we think this will work


@dataclass
class CausalAnalysisReport:
    """Complete root-cause analysis report with recommendations."""

    task_id: str
    error_description: str
    root_cause: CausalEvent | None = None
    causal_chain: List[CausalEvent] = field(default_factory=list)
    confounders: List[CausalEvent] = field(default_factory=list)
    interventions: List[Intervention] = field(default_factory=list)
    severity: CausalSeverity = CausalSeverity.WARNING
    confidence: float = 0.0
    chain_depth: int = 0
    confounding_strength: float = 0.0  # 0.0-1.0, how much confounders matter
    analysis_duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    analysis_status: str = "success"  # success, partial, failed
    error_message: str | None = None
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert report to dictionary for API serialization."""
        return {
            "task_id": self.task_id,
            "error_description": self.error_description,
            "severity": self.severity.value,
            "root_cause": (self._event_to_dict(self.root_cause) if self.root_cause else None),
            "causal_chain": [self._event_to_dict(e) for e in self.causal_chain],
            "confounders": [self._event_to_dict(c) for c in self.confounders],
            "confounding_strength": round(self.confounding_strength, 3),
            "interventions": [
                {
                    "name": i.name,
                    "description": i.description,
                    "mechanism": i.mechanism,
                    "predicted_success_rate": round(i.predicted_success_rate, 3),
                    "cost_level": i.cost_level,
                    "risk_level": i.risk_level,
                    # #13422: the one ladder the frontend badge renders; None when ungradable
                    "risk_tier": presented_risk_tier_value(i.risk_level),
                    "recommendation_type": i.recommendation_type.value,
                    "impact_rank": i.impact_rank,
                    "confidence": round(i.confidence, 3),
                    "evidence": i.evidence,
                }
                for i in self.interventions
            ],
            "recommendations": self.recommendations,
            "confidence": round(self.confidence, 3),
            "chain_depth": self.chain_depth,
            "timestamp": self.timestamp,
            "analysis_status": self.analysis_status,
            "analysis_duration_ms": round(self.analysis_duration_ms, 1),
            "error_message": self.error_message,
        }

    @staticmethod
    def _event_to_dict(event: CausalEvent | None) -> dict | None:
        """Convert CausalEvent to dictionary."""
        if not event:
            return None
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "name": event.name,
            "description": event.description,
            "timestamp": event.timestamp,
            "confidence": event.confidence,
            "depth": event.depth,
            "participants": event.participants,
        }
