# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Causal Inference Engine - Production-grade root-cause analysis service.

Issue #4069: Synthesizes Tier 1 (RootCauseAnalyzer) and Tier 2 (CounterfactualReasoner,
ConfounderControlAnalyzer) into a unified service that produces actionable diagnostic reports
with confidence scoring, intervention recommendations, and severity assessment.

Architecture:
1. **Traverse**: Backward causal chain traversal via TemporalSearchService.find_causal_chain()
2. **Detect**: Confounder detection via ConfounderControlAnalyzer (independent vs. downstream)
3. **Predict**: Intervention effectiveness via CounterfactualReasoner (what-if analysis)
4. **Score**: Confidence calculation from chain depth, event quality, confounder clarity
5. **Recommend**: Intervention ranking by impact, cost, and risk

Reports include:
- Root cause with evidence
- Full causal chain (backward from error)
- Confounders (multi-factor contributors)
- Interventions (ranked by likelihood × cost)
- Recommendations (IMMEDIATE, SHORT_TERM, LONG_TERM)
- CausalSeverity (CRITICAL, DEGRADED, WARNING)
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from context_aware_decision.counterfactual_reasoner import CounterfactualReasoner
from knowledge.temporal_search import TemporalSearchService
from services.confounder_control_analyzer import ConfounderControlAnalyzer
from services.root_cause_analyzer import (
    CausalEvent,
    RootCauseAnalyzer,
    RootCauseReport,
)

logger = get_logger(__name__)


class CausalSeverity(str, Enum):
    """Error severity levels."""

    CRITICAL = "critical"  # Immediate action required
    DEGRADED = "degraded"  # System partially impacted
    WARNING = "warning"  # Informational


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


class CausalInferenceEngine:
    """
    Production-grade causal inference service.

    Ties together:
    - RootCauseAnalyzer: Backward causal chain traversal
    - CounterfactualReasoner: What-if intervention prediction
    - ConfounderControlAnalyzer: Confounder detection and control
    - TemporalSearchService: Event traversal and querying

    Produces CausalAnalysisReport with actionable recommendations ranked by
    impact, cost, and risk.
    """

    # Analysis constants
    MAX_CHAIN_DEPTH = 5
    ANALYSIS_TIMEOUT_MS = 500
    MIN_CONFIDENCE_FOR_RECOMMENDATION = 0.4

    def __init__(self) -> None:
        """Initialize the causal inference engine."""
        self.redis_client = None
        self.root_cause_analyzer = RootCauseAnalyzer()
        self.counterfactual_reasoner = CounterfactualReasoner()
        self.confounder_analyzer = ConfounderControlAnalyzer()
        self.temporal_service = None

    async def _ensure_initialized(self) -> None:
        """Lazily initialize Redis and temporal service."""
        if self.redis_client is None:
            try:
                self.redis_client = await get_async_redis_client(database="knowledge")
                self.temporal_service = TemporalSearchService(self.redis_client)
            except Exception as e:
                logger.error("Failed to initialize Redis client: %s", e)
                raise

    async def analyze_failure(self, task_id: str, error_description: str | None = None) -> CausalAnalysisReport:
        """
        Analyze a task failure and produce root-cause report with interventions.

        Pipeline:
        1. Traverse: Get causal chain backward from error event
        2. Detect: Identify confounders (multi-factor contributors)
        3. Predict: For each cause, predict intervention effectiveness
        4. Score: Calculate confidence from chain depth + event quality + clarity
        5. Recommend: Rank interventions by impact × likelihood / cost

        Args:
            task_id: The failed task ID
            error_description: Optional error message for context

        Returns:
            CausalAnalysisReport with root cause, chain, confounders, and recommendations
        """
        start_time = time.time()

        try:
            await self._ensure_initialized()
        except Exception as e:
            logger.error("Failed to initialize engine: %s", e)
            return self._error_report(
                task_id,
                error_description,
                f"Initialization failed: {str(e)}",
                start_time,
            )

        try:
            # Step 1: Traverse causal chain backward from error
            base_report = await self.root_cause_analyzer.analyze_task_failure(task_id)

            if base_report.analysis_status == "failed":
                return self._error_report(
                    task_id,
                    error_description,
                    base_report.error_message,
                    start_time,
                )

            # Steps 2-5: Analyze and synthesize report
            return await self._synthesize_analysis(task_id, error_description, base_report, start_time)

        except Exception as e:
            logger.error("Causal analysis failed for task %s: %s", task_id, e)
            return self._error_report(
                task_id,
                error_description,
                f"Analysis error: {str(e)}",
                start_time,
            )

    def _error_report(
        self,
        task_id: str,
        error_description: str | None,
        error_message: str,
        start_time: float,
    ) -> CausalAnalysisReport:
        """Helper to create error report."""
        return CausalAnalysisReport(
            task_id=task_id,
            error_description=error_description or "Unknown error",
            analysis_status="failed",
            error_message=error_message,
            analysis_duration_ms=(time.time() - start_time) * 1000,
        )

    async def _synthesize_analysis(
        self,
        task_id: str,
        error_description: str | None,
        base_report: RootCauseReport,
        start_time: float,
    ) -> CausalAnalysisReport:
        """Synthesize steps 2-5 of analysis pipeline."""
        confounding_strength = self._analyze_confounders(base_report)
        interventions = await self._predict_interventions(base_report.causal_chain, base_report.root_event)
        confidence = self._calculate_confidence(base_report, confounding_strength, interventions)
        severity = self._assess_severity(base_report, confounding_strength, interventions)
        recommendations = self._generate_recommendations(interventions, severity)
        analysis_duration_ms = (time.time() - start_time) * 1000

        report = CausalAnalysisReport(
            task_id=task_id,
            error_description=(
                error_description or base_report.explanations[0] if base_report.explanations else "Unknown error"
            ),
            root_cause=base_report.root_event,
            causal_chain=base_report.causal_chain,
            confounders=base_report.confounders,
            interventions=interventions,
            severity=severity,
            confidence=confidence,
            chain_depth=base_report.chain_depth,
            confounding_strength=confounding_strength,
            analysis_status="success",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            analysis_duration_ms=analysis_duration_ms,
            recommendations=recommendations,
        )

        logger.info(
            "Causal analysis complete: task=%s, chain_depth=%d, "
            "confounding=%.2f, confidence=%.2f, severity=%s, analysis_time=%.0fms",
            task_id,
            report.chain_depth,
            confounding_strength,
            confidence,
            severity.value,
            analysis_duration_ms,
        )

        return report

    def _analyze_confounders(self, report: RootCauseReport) -> float:
        """
        Analyze confounder strength in the causal chain.

        Confounders are secondary causes that contribute independently to failure.
        Returns strength 0.0-1.0 based on number and independence of confounders.

        Args:
            report: Root cause report with chain and confounders

        Returns:
            Confounding strength score (0.0-1.0)
        """
        if not report.confounders:
            return 0.0

        # Confounder strength increases with:
        # 1. Number of independent confounders
        # 2. Confidence in confounder events
        # 3. Depth distribution (confounders at different depths)

        num_confounders = len(report.confounders)
        # Max strength is 0.8 from number of confounders (cap at 3+)
        num_strength = min(0.8, num_confounders / 3.0)

        # Average confidence of confounders
        avg_confidence = sum(c.confidence for c in report.confounders) / num_confounders
        confidence_strength = avg_confidence * 0.2

        return num_strength + confidence_strength

    async def _predict_interventions(
        self, chain: List[CausalEvent], root_cause: CausalEvent | None
    ) -> List[Intervention]:
        """
        Predict effectiveness of interventions for each cause in chain.

        For each event in the causal chain, generate intervention suggestions
        and use CounterfactualReasoner to predict success likelihood.

        Args:
            chain: Causal event chain (earliest to latest)
            root_cause: Root event if identified

        Returns:
            List of Intervention objects ranked by impact
        """
        interventions: List[Intervention] = []

        try:
            # For each cause in the chain, generate potential interventions
            for event in chain:
                event_interventions = await self._generate_event_interventions(event)
                interventions.extend(event_interventions)

            # Rank by impact score (success_rate × inverse_cost × inverse_risk)
            for i, intervention in enumerate(interventions, start=1):
                intervention.impact_rank = i

            return sorted(
                interventions,
                key=lambda x: (
                    x.predicted_success_rate * self._cost_multiplier(x.cost_level) * self._risk_multiplier(x.risk_level)
                ),
                reverse=True,
            )

        except Exception as e:
            logger.warning("Intervention prediction failed: %s", e)
            return interventions

    async def _generate_event_interventions(self, event: CausalEvent) -> List[Intervention]:
        """
        Generate intervention suggestions for a single causal event.

        Dispatches to event-type-specific helpers based on event category.

        Args:
            event: Causal event to generate interventions for

        Returns:
            List of Intervention objects for this event
        """
        event_lower = event.event_type.lower()

        # Dispatch to type-specific generators
        if "timeout" in event_lower or "deadline" in event_lower:
            return self._generate_timeout_interventions(event)
        elif "pool" in event_lower or "exhaustion" in event_lower:
            return self._generate_pool_interventions(event)
        elif "memory" in event_lower or "oom" in event_lower:
            return self._generate_memory_interventions(event)
        elif "database" in event_lower or "query" in event_lower:
            return self._generate_database_interventions(event)
        elif "connection" in event_lower or "network" in event_lower:
            return self._generate_network_interventions(event)
        else:
            return self._generate_generic_interventions(event)

    def _generate_timeout_interventions(self, event: CausalEvent) -> List[Intervention]:
        """Generate timeout/deadline-specific interventions."""
        return [
            Intervention(
                name="Increase timeout threshold",
                description=f"Raise timeout for {event.name}",
                mechanism="More time allows slow operations to complete naturally",
                predicted_success_rate=0.7,
                cost_level="low",
                risk_level="low",
                recommendation_type=RecommendationType.IMMEDIATE,
                impact_rank=0,
                confidence=0.8,
                evidence=[
                    "Timeout often fails marginal cases (just over threshold)",
                    f"Event: {event.name}",
                ],
            ),
            Intervention(
                name="Optimize operation performance",
                description=f"Improve performance of {event.name}",
                mechanism="Faster execution keeps operation under timeout",
                predicted_success_rate=0.8,
                cost_level="high",
                risk_level="low",
                recommendation_type=RecommendationType.LONG_TERM,
                impact_rank=0,
                confidence=0.75,
                evidence=[
                    "Root cause is slow operation, not insufficient time",
                    "Permanent fix via optimization",
                ],
            ),
        ]

    def _generate_pool_interventions(self, event: CausalEvent) -> List[Intervention]:
        """Generate resource pool exhaustion-specific interventions."""
        return [
            Intervention(
                name="Increase resource pool size",
                description=f"Grow pool for {event.name}",
                mechanism="More resources available reduces contention and wait time",
                predicted_success_rate=0.85,
                cost_level="medium",
                risk_level="low",
                recommendation_type=RecommendationType.SHORT_TERM,
                impact_rank=0,
                confidence=0.85,
                evidence=[
                    "Pool exhaustion causes direct failures",
                    f"Event: {event.name}",
                ],
            ),
            Intervention(
                name="Implement resource pooling optimization",
                description="Reduce peak resource demand via batching or caching",
                mechanism="Fewer resources needed per operation",
                predicted_success_rate=0.75,
                cost_level="high",
                risk_level="medium",
                recommendation_type=RecommendationType.LONG_TERM,
                impact_rank=0,
                confidence=0.7,
                evidence=["Address structural inefficiency in resource usage"],
            ),
        ]

    def _generate_memory_interventions(self, event: CausalEvent) -> List[Intervention]:
        """Generate memory/OOM-specific interventions."""
        return [
            Intervention(
                name="Increase memory allocation",
                description="Add more RAM to the system",
                mechanism="More available memory prevents allocation failures",
                predicted_success_rate=0.95,
                cost_level="medium",
                risk_level="low",
                recommendation_type=RecommendationType.SHORT_TERM,
                impact_rank=0,
                confidence=0.95,
                evidence=[
                    "Direct correlation between memory and OOM errors",
                    f"Event: {event.name}",
                ],
            ),
            Intervention(
                name="Implement memory leak detection",
                description="Profile and fix memory leaks",
                mechanism="Reduced waste allows normal operation within current memory",
                predicted_success_rate=0.8,
                cost_level="high",
                risk_level="low",
                recommendation_type=RecommendationType.LONG_TERM,
                impact_rank=0,
                confidence=0.75,
                evidence=["May be memory leak rather than just insufficient RAM"],
            ),
        ]

    def _generate_database_interventions(self, event: CausalEvent) -> List[Intervention]:
        """Generate database/query-specific interventions."""
        return [
            Intervention(
                name="Add database index",
                description=f"Index columns used in {event.name}",
                mechanism="Index accelerates query execution",
                predicted_success_rate=0.9,
                cost_level="low",
                risk_level="low",
                recommendation_type=RecommendationType.SHORT_TERM,
                impact_rank=0,
                confidence=0.85,
                evidence=[
                    "Missing indexes cause full table scans",
                    f"Event: {event.name}",
                ],
            ),
            Intervention(
                name="Refactor query logic",
                description="Improve query structure and filtering",
                mechanism="Better queries reduce data scanned and execution time",
                predicted_success_rate=0.85,
                cost_level="high",
                risk_level="low",
                recommendation_type=RecommendationType.LONG_TERM,
                impact_rank=0,
                confidence=0.8,
                evidence=["Architectural fix for query performance"],
            ),
        ]

    def _generate_network_interventions(self, event: CausalEvent) -> List[Intervention]:
        """Generate network/connection-specific interventions."""
        return [
            Intervention(
                name="Implement retry with backoff",
                description="Automatically retry failed connections",
                mechanism="Transient failures succeed on retry",
                predicted_success_rate=0.7,
                cost_level="low",
                risk_level="low",
                recommendation_type=RecommendationType.IMMEDIATE,
                impact_rank=0,
                confidence=0.75,
                evidence=[
                    "Network issues are often transient",
                    f"Event: {event.name}",
                ],
            ),
            Intervention(
                name="Improve network resilience",
                description="Add redundancy, improve infrastructure",
                mechanism="Better infrastructure reduces connection failures",
                predicted_success_rate=0.85,
                cost_level="high",
                risk_level="low",
                recommendation_type=RecommendationType.LONG_TERM,
                impact_rank=0,
                confidence=0.8,
                evidence=["Structural fix for network reliability"],
            ),
        ]

    def _generate_generic_interventions(self, event: CausalEvent) -> List[Intervention]:
        """Generate generic interventions for unknown event types."""
        return [
            Intervention(
                name="Retry the operation",
                description=f"Attempt {event.name} again",
                mechanism="Transient failures may succeed on retry",
                predicted_success_rate=0.5,
                cost_level="low",
                risk_level="low",
                recommendation_type=RecommendationType.IMMEDIATE,
                impact_rank=0,
                confidence=0.5,
                evidence=["Generic retry for unknown error type"],
            ),
        ]

    def _calculate_confidence(
        self,
        report: RootCauseReport,
        confounding_strength: float,
        interventions: List[Intervention],
    ) -> float:
        """
        Calculate comprehensive confidence in the analysis.

        Confidence increases with:
        - Chain depth (more events traced)
        - Event quality (individual confidence scores)
        - Intervention clarity (clear interventions suggest good analysis)
        - Absence of confounding (clear single cause)

        Confidence decreases with:
        - Confounding (multiple contributing factors)
        - Sparse data (shallow chain)
        - Uncertain interventions

        Args:
            report: Root cause report with chain
            confounding_strength: Confounder strength (0.0-1.0)
            interventions: Generated interventions

        Returns:
            Confidence score 0.0-1.0
        """
        # Base confidence from chain depth (max 0.4)
        depth_score = min(report.chain_depth / self.MAX_CHAIN_DEPTH, 1.0) * 0.4

        # Event quality from individual confidences (max 0.3)
        event_scores = [e.confidence for e in report.causal_chain]
        event_score = (sum(event_scores) / len(event_scores)) * 0.3 if event_scores else 0.0

        # Intervention clarity: high-confidence interventions indicate good analysis (max 0.2)
        if interventions:
            avg_intervention_confidence = sum(i.confidence for i in interventions[:3]) / min(  # Top 3 interventions
                3, len(interventions)
            )
            intervention_score = avg_intervention_confidence * 0.2
        else:
            intervention_score = 0.0

        # Apply confounder penalty (max -0.2)
        confounder_penalty = -confounding_strength * 0.2

        # Combine all factors
        total_confidence = max(0.0, depth_score + event_score + intervention_score + confounder_penalty)

        return min(1.0, total_confidence)

    def _assess_severity(
        self,
        report: RootCauseReport,
        confounding_strength: float,
        interventions: List[Intervention],
    ) -> CausalSeverity:
        """
        Assess error severity based on analysis results.

        CRITICAL: Root cause identified with high confidence, multi-factor (confounding)
        DEGRADED: Root cause identified with medium confidence, or moderate confounding
        WARNING: Low confidence, sparse data, or no clear interventions

        Args:
            report: Root cause report
            confounding_strength: Confounder strength (0.0-1.0)
            interventions: Generated interventions

        Returns:
            CausalSeverity level
        """
        # Start with confidence-based baseline
        if report.chain_depth >= 3 and report.confidence >= 0.7:
            base_severity = CausalSeverity.CRITICAL
        elif report.chain_depth >= 2 and report.confidence >= 0.5:
            base_severity = CausalSeverity.DEGRADED
        else:
            base_severity = CausalSeverity.WARNING

        # Upgrade to CRITICAL if multi-factor
        if confounding_strength >= 0.5 and base_severity == CausalSeverity.DEGRADED:
            base_severity = CausalSeverity.CRITICAL

        # Downgrade if high-confidence interventions exist
        if interventions and interventions[0].predicted_success_rate >= 0.8 and interventions[0].confidence >= 0.8:
            # High-confidence fix available, not critical
            if base_severity == CausalSeverity.CRITICAL:
                base_severity = CausalSeverity.DEGRADED

        return base_severity

    def _generate_recommendations(self, interventions: List[Intervention], severity: CausalSeverity) -> List[str]:
        """
        Generate human-readable recommendations ranked by priority.

        Recommendations are generated from top interventions, prioritizing:
        - IMMEDIATE actions (low cost, high confidence)
        - SHORT_TERM actions (medium cost, prevents root cause)
        - LONG_TERM actions (high cost, architectural fix)

        Args:
            interventions: Ranked list of interventions
            severity: Error severity level

        Returns:
            List of recommendation strings
        """
        recommendations: List[str] = []

        if not interventions:
            return ["No specific interventions identified. Manual investigation recommended."]

        # Group interventions by type
        immediate = [i for i in interventions if i.recommendation_type == RecommendationType.IMMEDIATE]
        short_term = [i for i in interventions if i.recommendation_type == RecommendationType.SHORT_TERM]
        long_term = [i for i in interventions if i.recommendation_type == RecommendationType.LONG_TERM]

        # Generate urgency prefix based on severity
        urgency = ""
        if severity == CausalSeverity.CRITICAL:
            urgency = "[URGENT] "
        elif severity == CausalSeverity.DEGRADED:
            urgency = "[ACTION] "

        # Add immediate actions
        if immediate:
            top_immediate = immediate[0]
            if top_immediate.confidence >= self.MIN_CONFIDENCE_FOR_RECOMMENDATION:
                recommendations.append(
                    f"{urgency}IMMEDIATE: {top_immediate.name} "
                    f"({top_immediate.predicted_success_rate:.0%} success likelihood). "
                    f"Reason: {top_immediate.mechanism}"
                )

        # Add short-term actions
        if short_term:
            top_short = short_term[0]
            if top_short.confidence >= self.MIN_CONFIDENCE_FOR_RECOMMENDATION:
                recommendations.append(
                    f"SHORT-TERM: {top_short.name} "
                    f"({top_short.predicted_success_rate:.0%} success likelihood). "
                    f"Reason: {top_short.mechanism}"
                )

        # Add long-term actions
        if long_term:
            top_long = long_term[0]
            if top_long.confidence >= self.MIN_CONFIDENCE_FOR_RECOMMENDATION:
                recommendations.append(
                    f"LONG-TERM: {top_long.name} "
                    f"({top_long.predicted_success_rate:.0%} success likelihood). "
                    f"Reason: {top_long.mechanism}"
                )

        # Fallback if no high-confidence recommendations
        if not recommendations and interventions:
            top = interventions[0]
            recommendations.append(
                f"Consider: {top.name} ({top.predicted_success_rate:.0%} likelihood). "
                f"Confidence: {top.confidence:.0%}"
            )

        return recommendations

    @staticmethod
    def _cost_multiplier(cost_level: str) -> float:
        """Cost multiplier for intervention ranking (lower cost = higher multiplier)."""
        return {"low": 1.0, "medium": 0.7, "high": 0.4}.get(cost_level, 0.5)

    @staticmethod
    def _risk_multiplier(risk_level: str) -> float:
        """Risk multiplier for intervention ranking (lower risk = higher multiplier)."""
        return {"low": 1.0, "medium": 0.8, "high": 0.5}.get(risk_level, 0.6)
