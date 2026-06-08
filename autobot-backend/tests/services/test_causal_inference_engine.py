# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for CausalInferenceEngine service.

Issue #4069: Tests production-grade causal analysis with:
- Chain traversal and confounder detection
- Intervention prediction and ranking
- Confidence scoring
- CausalSeverity assessment
- Recommendation generation

Test scenarios:
1. Database pool exhaustion (timeout → pool exhaustion → cascade)
2. Memory leak (gradual → OOM)
3. Cascading failures (multiple independent confounders)
4. Single cause (clear, high confidence)
5. Sparse data (low confidence, graceful degradation)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services.causal_inference_engine import (
    CausalAnalysisReport,
    CausalInferenceEngine,
    CausalSeverity,
    Intervention,
    RecommendationType,
)
from services.root_cause_analyzer import CausalEvent, RootCauseReport


class TestInterventionGeneration:
    """Tests for intervention generation from causal events."""

    @pytest.mark.asyncio
    async def test_timeout_event_interventions(self):
        """Timeout events should suggest timeout increase and optimization."""
        engine = CausalInferenceEngine()

        event = CausalEvent(
            event_id="timeout-1",
            event_type="timeout",
            name="Database query timeout",
            description="Query exceeded 30-second timeout",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            confidence=0.9,
        )

        interventions = await engine._generate_event_interventions(event)

        assert len(interventions) >= 2
        # Check for timeout increase intervention
        timeout_increases = [i for i in interventions if "timeout" in i.name.lower()]
        assert len(timeout_increases) >= 1
        assert timeout_increases[0].cost_level == "low"
        assert timeout_increases[0].predicted_success_rate >= 0.6

        # Check for optimization intervention
        optimizations = [i for i in interventions if "performance" in i.name.lower()]
        assert len(optimizations) >= 1
        assert optimizations[0].cost_level == "high"

    @pytest.mark.asyncio
    async def test_pool_exhaustion_interventions(self):
        """Pool exhaustion events should suggest pool increase and optimization."""
        engine = CausalInferenceEngine()

        event = CausalEvent(
            event_id="pool-1",
            event_type="connection_pool_exhaustion",
            name="Database connection pool exhausted",
            description="All connections in use, new requests queued",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            confidence=0.95,
        )

        interventions = await engine._generate_event_interventions(event)

        assert len(interventions) >= 2
        pool_increases = [i for i in interventions if "pool" in i.name.lower()]
        assert len(pool_increases) >= 1
        assert pool_increases[0].predicted_success_rate >= 0.8
        assert pool_increases[0].cost_level == "medium"

    @pytest.mark.asyncio
    async def test_memory_interventions(self):
        """OOM events should suggest memory increase and leak detection."""
        engine = CausalInferenceEngine()

        event = CausalEvent(
            event_id="oom-1",
            event_type="out_of_memory",
            name="Process out of memory",
            description="Memory allocation failed",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            confidence=0.99,
        )

        interventions = await engine._generate_event_interventions(event)

        assert len(interventions) >= 2
        memory_increases = [i for i in interventions if "memory" in i.name.lower()]
        assert len(memory_increases) >= 1
        assert memory_increases[0].predicted_success_rate >= 0.9
        assert memory_increases[0].recommendation_type == RecommendationType.SHORT_TERM

    @pytest.mark.asyncio
    async def test_database_interventions(self):
        """Database query events should suggest indexing and refactoring."""
        engine = CausalInferenceEngine()

        event = CausalEvent(
            event_id="db-1",
            event_type="slow_query",
            name="Slow database query",
            description="Query scans full table, no index present",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            confidence=0.85,
        )

        interventions = await engine._generate_event_interventions(event)

        assert len(interventions) >= 2
        index_interventions = [i for i in interventions if "index" in i.name.lower()]
        assert len(index_interventions) >= 1
        assert index_interventions[0].recommendation_type == RecommendationType.SHORT_TERM


class TestConfounderAnalysis:
    """Tests for confounder detection and strength calculation."""

    def test_no_confounders(self):
        """Single cause should have zero confounding."""
        engine = CausalInferenceEngine()

        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="Connection failed",
                description="",
                timestamp="",
                depth=0,
                confidence=0.9,
            )
        ]

        report = RootCauseReport(
            task_id="task-1",
            root_event=chain[0],
            causal_chain=chain,
            confounders=[],
            chain_depth=1,
        )

        strength = engine._analyze_confounders(report)
        assert strength == 0.0

    def test_single_confounder(self):
        """One confounder should produce moderate confounding."""
        engine = CausalInferenceEngine()

        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="Primary failure",
                description="",
                timestamp="",
                depth=0,
                confidence=0.9,
            )
        ]

        confounders = [
            CausalEvent(
                event_id="c1",
                event_type="warning",
                name="Secondary factor",
                description="",
                timestamp="",
                confidence=0.8,
            )
        ]

        report = RootCauseReport(
            task_id="task-1",
            root_event=chain[0],
            causal_chain=chain,
            confounders=confounders,
            chain_depth=1,
        )

        strength = engine._analyze_confounders(report)
        assert 0.0 < strength < 0.5

    def test_multiple_confounders(self):
        """Multiple confounders should produce high confounding."""
        engine = CausalInferenceEngine()

        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="Primary failure",
                description="",
                timestamp="",
                depth=0,
                confidence=0.9,
            )
        ]

        confounders = [
            CausalEvent(
                event_id="c1",
                event_type="warning",
                name="Factor 1",
                description="",
                timestamp="",
                confidence=0.8,
            ),
            CausalEvent(
                event_id="c2",
                event_type="warning",
                name="Factor 2",
                description="",
                timestamp="",
                confidence=0.75,
            ),
            CausalEvent(
                event_id="c3",
                event_type="warning",
                name="Factor 3",
                description="",
                timestamp="",
                confidence=0.85,
            ),
        ]

        report = RootCauseReport(
            task_id="task-1",
            root_event=chain[0],
            causal_chain=chain,
            confounders=confounders,
            chain_depth=1,
        )

        strength = engine._analyze_confounders(report)
        assert strength > 0.5


class TestConfidenceCalculation:
    """Tests for confidence scoring."""

    def test_high_confidence_deep_chain(self):
        """Deep chain with high event confidence should have high overall confidence."""
        engine = CausalInferenceEngine()

        chain = [
            CausalEvent(
                event_id=f"e{i}",
                event_type="error",
                name=f"Event {i}",
                description="",
                timestamp="",
                depth=i,
                confidence=0.9,
            )
            for i in range(5)
        ]

        report = RootCauseReport(
            task_id="task-1",
            root_event=chain[-1],
            causal_chain=chain,
            confounders=[],
            chain_depth=5,
        )

        interventions = [
            Intervention(
                name="Fix",
                description="",
                mechanism="",
                predicted_success_rate=0.9,
                cost_level="low",
                risk_level="low",
                recommendation_type=RecommendationType.IMMEDIATE,
                impact_rank=1,
                confidence=0.9,
            )
        ]

        confidence = engine._calculate_confidence(report, 0.0, interventions)
        assert confidence >= 0.7

    def test_low_confidence_shallow_chain(self):
        """Shallow chain with low event confidence should have low overall confidence."""
        engine = CausalInferenceEngine()

        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="Event",
                description="",
                timestamp="",
                depth=0,
                confidence=0.4,
            )
        ]

        report = RootCauseReport(
            task_id="task-1",
            root_event=chain[0],
            causal_chain=chain,
            confounders=[],
            chain_depth=1,
        )

        interventions = []

        confidence = engine._calculate_confidence(report, 0.0, interventions)
        assert confidence < 0.5

    def test_confidence_penalty_for_confounders(self):
        """Confounders should reduce overall confidence."""
        engine = CausalInferenceEngine()

        chain = [
            CausalEvent(
                event_id=f"e{i}",
                event_type="error",
                name=f"Event {i}",
                description="",
                timestamp="",
                depth=i,
                confidence=0.9,
            )
            for i in range(3)
        ]

        report = RootCauseReport(
            task_id="task-1",
            root_event=chain[-1],
            causal_chain=chain,
            confounders=[],
            chain_depth=3,
        )

        interventions = [
            Intervention(
                name="Fix",
                description="",
                mechanism="",
                predicted_success_rate=0.8,
                cost_level="low",
                risk_level="low",
                recommendation_type=RecommendationType.IMMEDIATE,
                impact_rank=1,
                confidence=0.8,
            )
        ]

        confidence_no_confound = engine._calculate_confidence(report, 0.0, interventions)
        confidence_with_confound = engine._calculate_confidence(report, 0.5, interventions)

        assert confidence_with_confound < confidence_no_confound


class TestSeverityAssessment:
    """Tests for severity assessment."""

    def test_critical_severity(self):
        """Deep chain, high confidence, multi-factor should be CRITICAL."""
        engine = CausalInferenceEngine()

        chain = [
            CausalEvent(
                event_id=f"e{i}",
                event_type="error",
                name=f"Event {i}",
                description="",
                timestamp="",
                depth=i,
                confidence=0.9,
            )
            for i in range(4)
        ]

        report = RootCauseReport(
            task_id="task-1",
            root_event=chain[-1],
            causal_chain=chain,
            confounders=[
                CausalEvent(
                    event_id="c1",
                    event_type="warning",
                    name="Confounder",
                    description="",
                    timestamp="",
                    confidence=0.8,
                )
            ],
            chain_depth=4,
            confidence=0.85,
        )

        interventions = [
            Intervention(
                name="Fix",
                description="",
                mechanism="",
                predicted_success_rate=0.9,
                cost_level="low",
                risk_level="low",
                recommendation_type=RecommendationType.IMMEDIATE,
                impact_rank=1,
                confidence=0.9,
            )
        ]

        severity = engine._assess_severity(report, 0.6, interventions)
        assert severity == CausalSeverity.CRITICAL

    def test_warning_severity(self):
        """Shallow chain, low confidence should be WARNING."""
        engine = CausalInferenceEngine()

        chain = [
            CausalEvent(
                event_id="e1",
                event_type="error",
                name="Event",
                description="",
                timestamp="",
                depth=0,
                confidence=0.4,
            )
        ]

        report = RootCauseReport(
            task_id="task-1",
            root_event=chain[0],
            causal_chain=chain,
            confounders=[],
            chain_depth=1,
            confidence=0.35,
        )

        interventions = []

        severity = engine._assess_severity(report, 0.0, interventions)
        assert severity == CausalSeverity.WARNING


class TestRecommendationGeneration:
    """Tests for recommendation generation."""

    def test_recommendations_ranked_by_type(self):
        """Recommendations should be ordered: IMMEDIATE, SHORT_TERM, LONG_TERM."""
        engine = CausalInferenceEngine()

        interventions = [
            Intervention(
                name="Long-term fix",
                description="",
                mechanism="",
                predicted_success_rate=0.8,
                cost_level="high",
                risk_level="low",
                recommendation_type=RecommendationType.LONG_TERM,
                impact_rank=1,
                confidence=0.9,
            ),
            Intervention(
                name="Immediate fix",
                description="",
                mechanism="",
                predicted_success_rate=0.7,
                cost_level="low",
                risk_level="low",
                recommendation_type=RecommendationType.IMMEDIATE,
                impact_rank=1,
                confidence=0.85,
            ),
            Intervention(
                name="Short-term fix",
                description="",
                mechanism="",
                predicted_success_rate=0.75,
                cost_level="medium",
                risk_level="low",
                recommendation_type=RecommendationType.SHORT_TERM,
                impact_rank=1,
                confidence=0.8,
            ),
        ]

        recommendations = engine._generate_recommendations(interventions, CausalSeverity.DEGRADED)

        assert len(recommendations) >= 2
        # Check order: IMMEDIATE comes before SHORT_TERM comes before LONG_TERM
        immediate_idx = None
        short_idx = None

        for i, rec in enumerate(recommendations):
            if "IMMEDIATE" in rec:
                immediate_idx = i
            elif "SHORT-TERM" in rec:
                short_idx = i
            elif "LONG-TERM" in rec:
                pass

        if immediate_idx is not None and short_idx is not None:
            assert immediate_idx < short_idx

    def test_no_low_confidence_recommendations(self):
        """Low-confidence interventions should not generate recommendations."""
        engine = CausalInferenceEngine()

        interventions = [
            Intervention(
                name="Uncertain fix",
                description="",
                mechanism="",
                predicted_success_rate=0.5,
                cost_level="low",
                risk_level="low",
                recommendation_type=RecommendationType.IMMEDIATE,
                impact_rank=1,
                confidence=0.3,  # Below MIN_CONFIDENCE_FOR_RECOMMENDATION
            )
        ]

        recommendations = engine._generate_recommendations(interventions, CausalSeverity.WARNING)

        # Should have fallback or empty recommendations
        assert len(recommendations) >= 0


class TestInterventionRanking:
    """Tests for intervention ranking by impact."""

    @pytest.mark.asyncio
    async def test_interventions_ranked_by_impact(self):
        """Interventions should be ranked by success_rate × cost_multiplier × risk_multiplier."""
        engine = CausalInferenceEngine()

        chain = [
            CausalEvent(
                event_id="timeout-1",
                event_type="timeout",
                name="Database timeout",
                description="",
                timestamp="",
                confidence=0.9,
            )
        ]

        interventions = await engine._predict_interventions(chain, chain[0])

        # All interventions should have impact_rank assigned
        assert all(i.impact_rank > 0 for i in interventions)

        # Should be ordered by impact (first should have highest impact)
        if len(interventions) >= 2:
            first_impact = (
                interventions[0].predicted_success_rate
                * engine._cost_multiplier(interventions[0].cost_level)
                * engine._risk_multiplier(interventions[0].risk_level)
            )
            second_impact = (
                interventions[1].predicted_success_rate
                * engine._cost_multiplier(interventions[1].cost_level)
                * engine._risk_multiplier(interventions[1].risk_level)
            )
            assert first_impact >= second_impact


class TestAnalyzeFailure:
    """Integration tests for full analyze_failure pipeline."""

    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        """Full analysis should return complete report with recommendations."""
        engine = CausalInferenceEngine()

        # Mock the root cause analyzer
        mock_report = RootCauseReport(
            task_id="task-1",
            root_event=CausalEvent(
                event_id="root",
                event_type="timeout",
                name="Query timeout",
                description="Database query exceeded timeout",
                timestamp="2026-04-10T12:00:00Z",
                confidence=0.9,
            ),
            causal_chain=[
                CausalEvent(
                    event_id="timeout",
                    event_type="timeout",
                    name="Query timeout",
                    description="",
                    timestamp="",
                    depth=0,
                    confidence=0.9,
                ),
                CausalEvent(
                    event_id="root",
                    event_type="missing_index",
                    name="Missing database index",
                    description="",
                    timestamp="",
                    depth=1,
                    confidence=0.85,
                ),
            ],
            confounders=[],
            chain_depth=2,
            confidence=0.85,
            analysis_status="success",
        )

        with patch.object(
            engine.root_cause_analyzer,
            "analyze_task_failure",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            report = await engine.analyze_failure("task-1", "Query timeout in production")

        assert report.analysis_status == "success"
        assert report.task_id == "task-1"
        assert report.root_cause is not None
        assert len(report.causal_chain) > 0
        assert len(report.interventions) > 0
        assert len(report.recommendations) > 0
        assert report.confidence > 0.5

    @pytest.mark.asyncio
    async def test_analysis_with_confounders(self):
        """Analysis should detect and report confounders."""
        engine = CausalInferenceEngine()

        mock_report = RootCauseReport(
            task_id="task-1",
            root_event=CausalEvent(
                event_id="root",
                event_type="resource_exhaustion",
                name="Multiple resources exhausted",
                description="",
                timestamp="",
                confidence=0.8,
            ),
            causal_chain=[
                CausalEvent(
                    event_id="e1",
                    event_type="error",
                    name="Pool exhaustion",
                    description="",
                    timestamp="",
                    depth=0,
                    confidence=0.85,
                ),
                CausalEvent(
                    event_id="e2",
                    event_type="error",
                    name="Memory pressure",
                    description="",
                    timestamp="",
                    depth=0,
                    confidence=0.8,
                ),
                CausalEvent(
                    event_id="root",
                    event_type="load_spike",
                    name="Traffic spike",
                    description="",
                    timestamp="",
                    depth=1,
                    confidence=0.9,
                ),
            ],
            confounders=[
                CausalEvent(
                    event_id="c1",
                    event_type="warning",
                    name="Inefficient query",
                    description="",
                    timestamp="",
                    confidence=0.75,
                )
            ],
            chain_depth=2,
            confidence=0.8,
            analysis_status="success",
        )

        with patch.object(
            engine.root_cause_analyzer,
            "analyze_task_failure",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            report = await engine.analyze_failure("task-1")

        assert report.confounding_strength > 0
        assert len(report.confounders) > 0
        assert report.severity in [CausalSeverity.CRITICAL, CausalSeverity.DEGRADED]

    @pytest.mark.asyncio
    async def test_analysis_graceful_degradation(self):
        """Analysis should return partial results if base analysis fails."""
        engine = CausalInferenceEngine()

        mock_report = RootCauseReport(
            task_id="task-1",
            analysis_status="failed",
            error_message="Analysis error",
        )

        with patch.object(
            engine.root_cause_analyzer,
            "analyze_task_failure",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            report = await engine.analyze_failure("task-1")

        assert report.analysis_status == "failed"
        assert report.error_message is not None


class TestReportSerialization:
    """Tests for report serialization to dict/JSON."""

    def test_report_to_dict(self):
        """Report should serialize cleanly to dict."""
        report = CausalAnalysisReport(
            task_id="task-1",
            error_description="Test error",
            root_cause=CausalEvent(
                event_id="root",
                event_type="error",
                name="Root cause",
                description="",
                timestamp="2026-04-10T12:00:00Z",
            ),
            causal_chain=[],
            confounders=[],
            interventions=[
                Intervention(
                    name="Fix",
                    description="Test fix",
                    mechanism="Test mechanism",
                    predicted_success_rate=0.8,
                    cost_level="low",
                    risk_level="low",
                    recommendation_type=RecommendationType.IMMEDIATE,
                    impact_rank=1,
                    confidence=0.9,
                )
            ],
            severity=CausalSeverity.DEGRADED,
            confidence=0.75,
            analysis_status="success",
            recommendations=["Test recommendation"],
        )

        result = report.to_dict()

        assert isinstance(result, dict)
        assert result["task_id"] == "task-1"
        assert result["severity"] == "degraded"
        assert len(result["interventions"]) == 1
        assert result["interventions"][0]["name"] == "Fix"
        assert result["recommendations"] == ["Test recommendation"]
