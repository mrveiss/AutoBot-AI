# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for stratified agent comparison with confounder control.

Tests stratification logic, confounding detection, and true effect estimation
for fair agent performance comparison.
"""

import json
from unittest.mock import patch

import pytest

from autobot_shared.time_utils import utc_timestamp
from services.confounder_control_analyzer import (
    ConfounderControlAnalyzer,
    StratifiedComparison,
    StratumMetrics,
)


@pytest.fixture
def analyzer():
    """Create a ConfounderControlAnalyzer instance for testing."""
    return ConfounderControlAnalyzer()


def _create_task_record(
    agent_id: str,
    task_id: str,
    status: str = "completed",
    duration_ms: float = 1000,
    query_complexity: int = 1,
    knowledge_base_size: int = 5000,
    network_latency_ms: int = 100,
    system_load: float = 0.5,
    task_priority: int = 2,
) -> dict:
    """Helper to create mock task records with metadata."""
    return {
        "agent_id": agent_id,
        "agent_type": "test_agent",
        "task_id": task_id,
        "task_name": f"task_{task_id}",
        "status": status,
        "started_at": utc_timestamp(),
        "completed_at": utc_timestamp(),
        "duration_ms": duration_ms,
        "input_size": 100,
        "output_size": 200,
        "tokens_used": 1000,
        "error_message": None,
        "metadata": {
            "query_complexity": query_complexity,
            "knowledge_base_size": knowledge_base_size,
            "network_latency_ms": network_latency_ms,
            "system_load": system_load,
            "task_priority": task_priority,
        },
    }


class TestStratificationByConfounder:
    """Tests for task stratification by confounder values."""

    @pytest.mark.asyncio
    async def test_stratify_by_query_complexity(self, analyzer):
        """Verify tasks are correctly binned by query complexity."""
        tasks = [
            _create_task_record("agent_a", "t1", query_complexity=1),  # low
            _create_task_record("agent_a", "t2", query_complexity=1),  # low
            _create_task_record("agent_a", "t3", query_complexity=2),  # medium
            _create_task_record("agent_a", "t4", query_complexity=3),  # high
            _create_task_record("agent_a", "t5", query_complexity=4),  # high
        ]

        strata_result = await analyzer.stratify_by_confounder(tasks, "query_complexity")
        assert "low" in strata_result
        assert "medium" in strata_result
        assert "high" in strata_result
        assert len(strata_result["low"]) == 2
        assert len(strata_result["medium"]) == 1
        assert len(strata_result["high"]) == 2

    @pytest.mark.asyncio
    async def test_stratify_by_knowledge_base_size(self, analyzer):
        """Verify stratification by knowledge base size."""
        tasks = [
            _create_task_record("agent_a", "t1", knowledge_base_size=1000),  # small
            _create_task_record("agent_a", "t2", knowledge_base_size=10000),  # medium
            _create_task_record("agent_a", "t3", knowledge_base_size=100000),  # large
        ]

        strata = await analyzer.stratify_by_confounder(tasks, "knowledge_base_size")
        assert set(strata.keys()) == {"small", "medium", "large"}

    @pytest.mark.asyncio
    async def test_stratify_by_system_load(self, analyzer):
        """Verify stratification by system load levels."""
        tasks = [
            _create_task_record("agent_a", "t1", system_load=0.2),  # low
            _create_task_record("agent_a", "t2", system_load=0.5),  # medium
            _create_task_record("agent_a", "t3", system_load=0.8),  # high
        ]

        strata = await analyzer.stratify_by_confounder(tasks, "system_load")
        assert set(strata.keys()) == {"low", "medium", "high"}

    @pytest.mark.asyncio
    async def test_extract_confounder_value_invalid_confounder(self, analyzer):
        """Verify handling of unknown confounders."""
        task = _create_task_record("agent_a", "t1")
        value = analyzer._extract_confounder_value(task, "unknown_confounder")
        assert value is None


class TestStratumMetricsComputation:
    """Tests for computing metrics within a stratum."""

    def test_compute_success_rate_metric(self, analyzer):
        """Verify success_rate metric computation."""
        tasks = [
            _create_task_record("agent_a", "t1", status="completed"),
            _create_task_record("agent_a", "t2", status="completed"),
            _create_task_record("agent_a", "t3", status="failed"),
        ]

        metrics = analyzer._compute_stratum_metrics(tasks, "success_rate", "low")
        assert metrics is not None
        assert metrics.task_count == 3
        assert metrics.success_count == 2
        assert metrics.failed_count == 1
        assert metrics.metric_value == pytest.approx(66.67, rel=0.1)

    def test_compute_error_rate_metric(self, analyzer):
        """Verify error_rate metric computation."""
        tasks = [
            _create_task_record("agent_a", "t1", status="completed"),
            _create_task_record("agent_a", "t2", status="completed"),
            _create_task_record("agent_a", "t3", status="failed"),
        ]

        metrics = analyzer._compute_stratum_metrics(tasks, "error_rate", "low")
        assert metrics is not None
        assert metrics.metric_value == pytest.approx(33.33, rel=0.1)

    def test_compute_avg_duration_metric(self, analyzer):
        """Verify avg_duration_ms metric computation."""
        tasks = [
            _create_task_record("agent_a", "t1", duration_ms=1000),
            _create_task_record("agent_a", "t2", duration_ms=2000),
            _create_task_record("agent_a", "t3", duration_ms=3000),
        ]

        metrics = analyzer._compute_stratum_metrics(tasks, "avg_duration_ms", "low")
        assert metrics is not None
        assert metrics.metric_value == pytest.approx(2000.0, rel=0.01)

    def test_confidence_scoring_by_sample_size(self, analyzer):
        """Verify confidence increases with sample size."""
        # Small sample
        tasks_small = [_create_task_record("agent_a", f"t{i}") for i in range(5)]
        metrics_small = analyzer._compute_stratum_metrics(tasks_small, "success_rate", "low")

        # Large sample
        tasks_large = [_create_task_record("agent_a", f"t{i}") for i in range(100)]
        metrics_large = analyzer._compute_stratum_metrics(tasks_large, "success_rate", "low")

        assert metrics_small is not None
        assert metrics_large is not None
        assert metrics_large.confidence > metrics_small.confidence

    def test_compute_metrics_with_no_tasks(self, analyzer):
        """Verify None returned for empty task list."""
        metrics = analyzer._compute_stratum_metrics([], "success_rate", "low")
        assert metrics is None


class TestConfoundingDetection:
    """Tests for detecting confounding effects."""

    def test_confounding_detected_high_variance(self, analyzer):
        """Verify confounding detection when metric varies across strata."""
        # Create strata with widely different metrics
        strata_results = {
            "low": (
                StratumMetrics("low", 10, 10, 0, 100.0, 0.8),  # 100% success
                StratumMetrics("low", 10, 5, 5, 50.0, 0.8),  # 50% success
            ),
            "high": (
                StratumMetrics("high", 10, 6, 4, 60.0, 0.8),  # 60% success
                StratumMetrics("high", 10, 8, 2, 80.0, 0.8),  # 80% success
            ),
        }

        confounded, strength = analyzer._detect_confounding("success_rate", strata_results)
        assert confounded is True
        assert strength > 0.0

    def test_no_confounding_consistent_metric(self, analyzer):
        """Verify no confounding when metric is consistent."""
        # Create strata with similar metrics
        strata_results = {
            "low": (
                StratumMetrics("low", 10, 8, 2, 80.0, 0.8),
                StratumMetrics("low", 10, 8, 2, 80.0, 0.8),
            ),
            "high": (
                StratumMetrics("high", 10, 8, 2, 80.0, 0.8),
                StratumMetrics("high", 10, 8, 2, 80.0, 0.8),
            ),
        }

        confounded, strength = analyzer._detect_confounding("success_rate", strata_results)
        assert confounded is False
        assert strength < 0.15


class TestTrueEffectEstimation:
    """Tests for true effect estimation after confounder control."""

    def test_true_effect_consistent_across_strata(self, analyzer):
        """Verify true effect when agent A is consistently better."""
        strata_results = {
            "low": (
                StratumMetrics("low", 10, 9, 1, 90.0, 0.8),  # Agent A: 90%
                StratumMetrics("low", 10, 8, 2, 80.0, 0.8),  # Agent B: 80%
            ),
            "high": (
                StratumMetrics("high", 10, 8, 2, 80.0, 0.8),  # Agent A: 80%
                StratumMetrics("high", 10, 7, 3, 70.0, 0.8),  # Agent B: 70%
            ),
        }

        true_effect, confidence = analyzer._estimate_true_effect("success_rate", strata_results)
        assert true_effect > 0  # Agent A is better
        assert confidence > 0.5  # High confidence (consistent direction)

    def test_true_effect_inconsistent_across_strata(self, analyzer):
        """Verify confidence is lower when effects are inconsistent."""
        strata_results = {
            "low": (
                StratumMetrics("low", 10, 9, 1, 90.0, 0.8),  # Agent A: 90%
                StratumMetrics("low", 10, 8, 2, 80.0, 0.8),  # Agent B: 80%
            ),
            "high": (
                StratumMetrics("high", 10, 7, 3, 70.0, 0.8),  # Agent A: 70%
                StratumMetrics("high", 10, 8, 2, 80.0, 0.8),  # Agent B: 80%
            ),
        }

        true_effect, confidence = analyzer._estimate_true_effect("success_rate", strata_results)
        assert confidence < 0.5  # Lower confidence (inconsistent direction)


class TestOverallAdvantageComputation:
    """Tests for computing overall advantage."""

    def test_overall_advantage_agent_a_better(self, analyzer):
        """Verify advantage when agent A is better."""
        strata_results = {
            "low": (
                StratumMetrics("low", 10, 9, 1, 85.0, 0.8),
                StratumMetrics("low", 10, 6, 4, 60.0, 0.8),
            ),
        }

        advantage = analyzer._compute_overall_advantage("success_rate", strata_results)
        assert advantage > 0

    def test_overall_advantage_agent_b_better(self, analyzer):
        """Verify advantage when agent B is better."""
        strata_results = {
            "low": (
                StratumMetrics("low", 10, 6, 4, 60.0, 0.8),
                StratumMetrics("low", 10, 9, 1, 85.0, 0.8),
            ),
        }

        advantage = analyzer._compute_overall_advantage("success_rate", strata_results)
        assert advantage < 0

    def test_overall_advantage_zero_difference(self, analyzer):
        """Verify zero advantage when agents are equal."""
        strata_results = {
            "low": (
                StratumMetrics("low", 10, 8, 2, 80.0, 0.8),
                StratumMetrics("low", 10, 8, 2, 80.0, 0.8),
            ),
        }

        advantage = analyzer._compute_overall_advantage("success_rate", strata_results)
        assert abs(advantage) < 0.01


class TestInterpretationGeneration:
    """Tests for generating human-readable interpretations."""

    def test_interpretation_with_confounding(self, analyzer):
        """Verify interpretation mentions confounding when detected."""
        interpretation = analyzer._generate_interpretation(
            "agent_a",
            "agent_b",
            "success_rate",
            overall_advantage=0.1,
            true_effect=0.05,
            confounded=True,
            confounding_strength=0.3,
        )
        assert "Confounding detected" in interpretation
        assert "agent_a" in interpretation.lower()

    def test_interpretation_no_confounding(self, analyzer):
        """Verify interpretation when no confounding."""
        interpretation = analyzer._generate_interpretation(
            "agent_a",
            "agent_b",
            "success_rate",
            overall_advantage=0.1,
            true_effect=0.1,
            confounded=False,
            confounding_strength=0.0,
        )
        assert "No significant confounding" in interpretation

    def test_interpretation_no_advantage(self, analyzer):
        """Verify interpretation when agents are similar."""
        interpretation = analyzer._generate_interpretation(
            "agent_a",
            "agent_b",
            "success_rate",
            overall_advantage=0.001,
            true_effect=0.001,
            confounded=False,
            confounding_strength=0.0,
        )
        assert "perform similarly" in interpretation


class TestStratifiedComparisonIntegration:
    """Integration tests for full stratified comparison workflow."""

    @pytest.mark.asyncio
    async def test_compare_agents_stratified_happy_path(self, analyzer):
        """Verify complete stratified comparison workflow."""
        # Create test data: agent_a is better at low complexity, agent_b at high
        tasks_a = [
            _create_task_record("agent_a", f"t{i}", status="completed", query_complexity=1) for i in range(20)
        ] + [_create_task_record("agent_a", f"t{i+20}", status="failed", query_complexity=3) for i in range(5)]

        tasks_b = [_create_task_record("agent_b", f"t{i}", status="failed", query_complexity=1) for i in range(5)] + [
            _create_task_record("agent_b", f"t{i+5}", status="completed", query_complexity=3) for i in range(20)
        ]

        with patch.object(analyzer, "_get_agent_history") as mock_history:

            async def side_effect(agent_id, limit):
                if agent_id == "agent_a":
                    return tasks_a
                else:
                    return tasks_b

            mock_history.side_effect = side_effect

            comparison = await analyzer.compare_agents_stratified(
                "agent_a", "agent_b", "success_rate", ["query_complexity"]
            )

            assert comparison is not None
            assert comparison.agent_a == "agent_a"
            assert comparison.agent_b == "agent_b"
            assert comparison.metric == "success_rate"
            assert len(comparison.strata) > 0
            assert comparison.interpretation != ""

    @pytest.mark.asyncio
    async def test_compare_agents_stratified_insufficient_data(self, analyzer):
        """Verify None returned when insufficient data."""
        with patch.object(analyzer, "_get_agent_history") as mock_history:
            mock_history.return_value = []

            comparison = await analyzer.compare_agents_stratified("agent_a", "agent_b", "success_rate")

            assert comparison is None

    @pytest.mark.asyncio
    async def test_compare_agents_no_overlapping_strata(self, analyzer):
        """Verify None returned when strata don't overlap."""
        tasks_a = [_create_task_record("agent_a", f"t{i}", query_complexity=1) for i in range(10)]
        tasks_b = [_create_task_record("agent_b", f"t{i}", query_complexity=3) for i in range(10)]

        with patch.object(analyzer, "_get_agent_history") as mock_history:

            async def side_effect(agent_id, limit):
                return tasks_a if agent_id == "agent_a" else tasks_b

            mock_history.side_effect = side_effect

            comparison = await analyzer.compare_agents_stratified("agent_a", "agent_b")

            assert comparison is None


class TestStratifiedComparisonSerialization:
    """Tests for StratifiedComparison serialization."""

    def test_to_dict_serialization(self):
        """Verify StratifiedComparison.to_dict() produces valid JSON."""
        strata = {
            "low": (
                StratumMetrics("low", 10, 9, 1, 90.0, 0.8),
                StratumMetrics("low", 10, 8, 2, 80.0, 0.8),
            ),
        }

        comparison = StratifiedComparison(
            agent_a="agent_a",
            agent_b="agent_b",
            metric="success_rate",
            confounders=["query_complexity"],
            overall_advantage=0.1,
            strata=strata,
            confounded_effect=False,
            confounding_strength=0.0,
            true_effect=0.1,
            true_effect_confidence=0.9,
            interpretation="Agent A is 10% better",
            sample_coverage=1.0,
        )

        result_dict = comparison.to_dict()

        # Verify it's JSON-serializable
        json_str = json.dumps(result_dict)
        assert json_str is not None

        # Verify key fields
        assert result_dict["agent_a"] == "agent_a"
        assert result_dict["agent_b"] == "agent_b"
        assert result_dict["overall_advantage"] == pytest.approx(0.1, rel=0.01)
        assert "strata" in result_dict
