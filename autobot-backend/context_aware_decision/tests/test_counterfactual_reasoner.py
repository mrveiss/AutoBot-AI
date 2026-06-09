# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Counterfactual Reasoning

Verifies that:
1. Empirical predictions match historical outcomes
2. Causal predictions apply correct patterns
3. Heuristic fallbacks provide sensible defaults
4. Side effect detection works correctly
5. Confidence scoring reflects prediction certainty
6. All three prediction tiers (empirical -> causal -> heuristic) work
"""

import json
import time
from unittest.mock import AsyncMock

import pytest

from context_aware_decision.counterfactual_reasoner import CounterfactualReasoner
from context_aware_decision.models import (
    ContextElement,
    DecisionContext,
    InterventionOutcome,
)
from context_aware_decision.types import ContextType, DecisionType

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis():
    """Mock async Redis client."""
    redis = AsyncMock()
    return redis


@pytest.fixture
def sample_context():
    """Create a sample decision context for testing."""
    return DecisionContext(
        decision_id="test-decision-001",
        decision_type=DecisionType.AUTOMATION_ACTION,
        primary_goal="complete_task",
        context_elements=[
            ContextElement(
                context_id="ce-001",
                context_type=ContextType.SYSTEM_STATE,
                content={"network_status": "unstable"},
                confidence=0.8,
                relevance_score=0.9,
                timestamp=time.time(),
                source="system_monitor",
                metadata={"type": "network"},
            ),
        ],
        constraints=[],
        available_actions=[
            {
                "action": "retry",
                "action_type": "retry",
                "confidence": 0.6,
                "description": "Retry the failed operation",
            }
        ],
        risk_factors=[],
        user_preferences={"automation_level": "high"},
        system_state={"load": "normal"},
        historical_patterns=[],
        timestamp=time.time(),
    )


@pytest.fixture
def sample_execution_history():
    """Create sample execution history for empirical predictions."""
    current_time = time.time()
    return [
        {
            "option": "retry",
            "decision_type": "automation_action",
            "succeeded": True,
            "timestamp": current_time - 3600,  # 1 hour ago
            "latency_ms": 2500,
            "side_effects": [{"type": "latency_increase", "duration_ms": 2500}],
        },
        {
            "option": "retry",
            "decision_type": "automation_action",
            "succeeded": True,
            "timestamp": current_time - 7200,  # 2 hours ago
            "latency_ms": 3100,
            "side_effects": [{"type": "latency_increase", "duration_ms": 3100}],
        },
        {
            "option": "retry",
            "decision_type": "automation_action",
            "succeeded": False,
            "timestamp": current_time - 86400,  # 1 day ago
            "latency_ms": 5000,
            "side_effects": [
                {"type": "latency_increase", "duration_ms": 5000},
                {"type": "timeout", "duration_ms": 0},
            ],
        },
    ]


@pytest.fixture
def sample_causal_patterns():
    """Create sample causal patterns."""
    return [
        {
            "name": "retry_on_unstable_network",
            "action_type": "retry",
            "conditions": {
                "decision_type": "automation_action",
                "required_context_types": ["network"],
            },
            "predicted_success_rate": 0.65,
            "side_effects": [
                {
                    "type": "latency_increase",
                    "frequency": 0.9,
                    "severity": "medium",
                }
            ],
        },
        {
            "name": "escalate_on_high_risk",
            "action_type": "escalate",
            "conditions": {"min_high_risk_factors": 1},
            "predicted_success_rate": 0.85,
            "side_effects": [
                {
                    "type": "user_notification",
                    "frequency": 1.0,
                    "severity": "low",
                }
            ],
        },
    ]


# =============================================================================
# Tests: Empirical Prediction
# =============================================================================


class TestEmpiricalPrediction:
    """Tests for history-based empirical predictions."""

    @pytest.mark.asyncio
    async def test_empirical_prediction_with_history(self, sample_context, sample_execution_history, mock_redis):
        """Verify empirical prediction aggregates historical outcomes correctly."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        # Setup mock to return execution history
        history_key = CounterfactualReasoner.EXECUTION_HISTORY_KEY.format(
            decision_type=sample_context.decision_type.value
        )
        mock_redis.get.return_value = json.dumps(sample_execution_history)

        outcome = await reasoner._predict_empirical("retry", sample_context, mock_redis)

        assert outcome is not None
        assert outcome.option == "retry"
        assert outcome.prediction_source == "empirical"
        # 2 successes out of 3 = 66.7% success rate (with temporal decay)
        assert 0.5 < outcome.predicted_success_rate < 0.9
        assert outcome.confidence > 0.5  # Should have good confidence with 3 samples
        assert len(outcome.side_effects) > 0
        assert outcome.estimated_latency_ms is not None

    @pytest.mark.asyncio
    async def test_empirical_prediction_no_history(self, sample_context, mock_redis):
        """Verify empirical prediction returns None when no history exists."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        # No history found
        mock_redis.get.return_value = None

        outcome = await reasoner._predict_empirical("retry", sample_context, mock_redis)

        assert outcome is None

    @pytest.mark.asyncio
    async def test_empirical_prediction_insufficient_samples(self, sample_context, mock_redis):
        """Verify empirical prediction requires minimum sample size."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        # Only 1 sample (too few for reliable prediction)
        single_sample = [
            {
                "option": "retry",
                "decision_type": "automation_action",
                "succeeded": True,
                "timestamp": time.time(),
                "latency_ms": 2500,
                "side_effects": [],
            }
        ]
        mock_redis.get.return_value = json.dumps(single_sample)

        outcome = await reasoner._predict_empirical("retry", sample_context, mock_redis)

        assert outcome is None  # Too few samples

    @pytest.mark.asyncio
    async def test_empirical_prediction_temporal_decay(self, sample_context, mock_redis):
        """Verify empirical prediction applies temporal decay to old data."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        current_time = time.time()
        old_history = [
            {
                "option": "retry",
                "decision_type": "automation_action",
                "succeeded": True,
                "timestamp": current_time - (90 * 86400),  # 90 days ago (old)
                "latency_ms": 2500,
                "side_effects": [],
            },
            {
                "option": "retry",
                "decision_type": "automation_action",
                "succeeded": True,
                "timestamp": current_time - 3600,  # 1 hour ago (recent)
                "latency_ms": 2500,
                "side_effects": [],
            },
            {
                "option": "retry",
                "decision_type": "automation_action",
                "succeeded": True,
                "timestamp": current_time - 7200,  # 2 hours ago (recent)
                "latency_ms": 2500,
                "side_effects": [],
            },
        ]
        mock_redis.get.return_value = json.dumps(old_history)

        outcome = await reasoner._predict_empirical("retry", sample_context, mock_redis)

        assert outcome is not None
        # Old data should be heavily discounted, but recent successes dominate
        assert outcome.predicted_success_rate > 0.7

    @pytest.mark.asyncio
    async def test_empirical_side_effect_aggregation(self, sample_context, sample_execution_history, mock_redis):
        """Verify empirical prediction correctly aggregates side effects."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        mock_redis.get.return_value = json.dumps(sample_execution_history)

        outcome = await reasoner._predict_empirical("retry", sample_context, mock_redis)

        assert outcome is not None
        # Should detect latency_increase (in all 3) and timeout (in 1)
        effect_types = {e["type"] for e in outcome.side_effects}
        assert "latency_increase" in effect_types

    @pytest.mark.asyncio
    async def test_empirical_latency_averaging(self, sample_context, sample_execution_history, mock_redis):
        """Verify empirical prediction averages latency correctly."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        mock_redis.get.return_value = json.dumps(sample_execution_history)

        outcome = await reasoner._predict_empirical("retry", sample_context, mock_redis)

        assert outcome is not None
        assert outcome.estimated_latency_ms is not None
        # (2500 + 3100 + 5000) / 3 = 3533
        assert 3400 < outcome.estimated_latency_ms < 3700


# =============================================================================
# Tests: Causal Prediction
# =============================================================================


class TestCausalPrediction:
    """Tests for causal pattern-based predictions."""

    @pytest.mark.asyncio
    async def test_causal_prediction_pattern_match(self, sample_context, sample_causal_patterns, mock_redis):
        """Verify causal prediction matches and applies patterns correctly."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        # Add network context type for pattern matching
        sample_context.context_elements[0].context_type = ContextType.SYSTEM_STATE
        sample_context.context_elements[0].metadata = {"type": "network"}

        patterns_key = CounterfactualReasoner.CAUSAL_PATTERNS_KEY.format(action_type="retry")
        mock_redis.get.return_value = json.dumps(sample_causal_patterns)

        outcome = await reasoner._predict_causal("retry", sample_context, mock_redis)

        assert outcome is not None
        assert outcome.option == "retry"
        assert outcome.prediction_source == "causal"
        assert outcome.predicted_success_rate == 0.65
        assert len(outcome.side_effects) > 0

    @pytest.mark.asyncio
    async def test_causal_prediction_no_patterns(self, sample_context, mock_redis):
        """Verify causal prediction returns None when no patterns match."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        # No patterns found
        mock_redis.get.return_value = None

        outcome = await reasoner._predict_causal("retry", sample_context, mock_redis)

        assert outcome is None

    @pytest.mark.asyncio
    async def test_causal_prediction_pattern_conditions(self, sample_context, mock_redis):
        """Verify causal prediction evaluates pattern conditions correctly."""
        reasoner = CounterfactualReasoner()

        # Test pattern with specific decision type
        pattern = {
            "name": "automation_retry",
            "conditions": {"decision_type": "automation_action"},
            "predicted_success_rate": 0.7,
            "side_effects": [],
        }

        assert reasoner._pattern_matches_context(pattern, sample_context)

        # Test pattern with non-matching decision type
        pattern["conditions"]["decision_type"] = "navigation_choice"
        assert not reasoner._pattern_matches_context(pattern, sample_context)

    @pytest.mark.asyncio
    async def test_causal_prediction_multiple_patterns(self, sample_context, mock_redis):
        """Verify causal prediction aggregates multiple matching patterns."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        patterns = [
            {
                "name": "pattern1",
                "conditions": {"decision_type": "automation_action"},
                "predicted_success_rate": 0.6,
                "side_effects": [{"type": "effect1", "severity": "low"}],
            },
            {
                "name": "pattern2",
                "conditions": {"decision_type": "automation_action"},
                "predicted_success_rate": 0.8,
                "side_effects": [{"type": "effect2", "severity": "medium"}],
            },
        ]

        patterns_key = CounterfactualReasoner.CAUSAL_PATTERNS_KEY.format(action_type="retry")
        mock_redis.get.return_value = json.dumps(patterns)

        outcome = await reasoner._predict_causal("retry", sample_context, mock_redis)

        assert outcome is not None
        # Average of 0.6 and 0.8 = 0.7
        assert outcome.predicted_success_rate == 0.7
        # Should aggregate both patterns' side effects
        assert len(outcome.side_effects) == 2


# =============================================================================
# Tests: Heuristic Prediction
# =============================================================================


class TestHeuristicPrediction:
    """Tests for rule-based fallback heuristics."""

    def test_heuristic_retry_prediction(self, sample_context):
        """Verify heuristic prediction for retry option."""
        reasoner = CounterfactualReasoner()

        outcome = reasoner._predict_heuristic("retry", sample_context, {"confidence": 0.6})

        assert outcome.option == "retry"
        assert outcome.prediction_source == "heuristic"
        assert outcome.predicted_success_rate == 0.6
        assert outcome.confidence == 0.5  # Heuristic has low confidence
        # Retry should include latency increase side effect
        assert any(e["type"] == "latency_increase" for e in outcome.side_effects)
        assert outcome.fallback_risk == "backlog_growth"
        assert outcome.estimated_latency_ms == 3000

    def test_heuristic_escalation_prediction(self, sample_context):
        """Verify heuristic prediction for escalation option."""
        reasoner = CounterfactualReasoner()

        outcome = reasoner._predict_heuristic("escalate", sample_context, {"confidence": 0.9})

        assert outcome.option == "escalate"
        assert outcome.predicted_success_rate == 0.9
        # Escalation should include user notification and wait time
        effect_types = {e["type"] for e in outcome.side_effects}
        assert "user_notification" in effect_types
        assert "wait_time" in effect_types
        assert outcome.fallback_risk == "timeout_waiting_for_human"
        assert outcome.estimated_latency_ms == 300000  # 5 minutes

    def test_heuristic_automation_prediction(self, sample_context):
        """Verify heuristic prediction for automation option."""
        reasoner = CounterfactualReasoner()

        outcome = reasoner._predict_heuristic("automate", sample_context, {"confidence": 0.7})

        assert outcome.option == "automate"
        assert outcome.predicted_success_rate == 0.7
        # Automation should include state mutation (high severity)
        assert any(e["type"] == "state_mutation" for e in outcome.side_effects)
        assert outcome.fallback_risk == "irreversible_change"

    def test_heuristic_wait_prediction(self, sample_context):
        """Verify heuristic prediction for wait option."""
        reasoner = CounterfactualReasoner()

        outcome = reasoner._predict_heuristic("wait", sample_context, {"confidence": 0.5})

        assert outcome.option == "wait"
        assert outcome.fallback_risk == "missed_deadline"
        assert any(e["type"] == "deadline_risk" for e in outcome.side_effects)

    def test_heuristic_risk_factor_penalty(self, sample_context):
        """Verify heuristic prediction penalizes high-risk contexts."""
        reasoner = CounterfactualReasoner()

        # Add high-risk factors
        sample_context.risk_factors = [{"risk_type": "critical_error", "severity": "high"}]

        outcome = reasoner._predict_heuristic("retry", sample_context, {"confidence": 0.8})

        # Success rate should be reduced due to high risk
        # 0.8 * 0.7 = 0.56
        assert outcome.predicted_success_rate < 0.8


# =============================================================================
# Tests: Prediction Tier Selection
# =============================================================================


class TestPredictionTierSelection:
    """Tests for three-tier prediction (empirical -> causal -> heuristic)."""

    @pytest.mark.asyncio
    async def test_tier_1_empirical_preferred(self, sample_context, sample_execution_history, mock_redis):
        """Verify empirical prediction is preferred when available."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        # Setup: empirical exists
        history_key = CounterfactualReasoner.EXECUTION_HISTORY_KEY.format(
            decision_type=sample_context.decision_type.value
        )
        mock_redis.get.side_effect = [
            json.dumps(sample_execution_history),  # For empirical call
            json.dumps([]),  # For causal call (shouldn't be reached)
        ]

        outcome = await reasoner.what_if("retry", sample_context, {"confidence": 0.6})

        assert outcome.prediction_source == "empirical"
        # Only one get call should be made (empirical succeeded)
        assert mock_redis.get.call_count == 1

    @pytest.mark.asyncio
    async def test_tier_2_causal_fallback(self, sample_context, sample_causal_patterns, mock_redis):
        """Verify causal prediction is used when empirical unavailable."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        # Setup: empirical fails, causal exists
        patterns_key = CounterfactualReasoner.CAUSAL_PATTERNS_KEY.format(action_type="retry")
        mock_redis.get.side_effect = [
            None,  # Empirical returns nothing
            json.dumps(sample_causal_patterns),  # Causal has data
        ]

        outcome = await reasoner.what_if("retry", sample_context, {"confidence": 0.6})

        assert outcome.prediction_source == "causal"

    @pytest.mark.asyncio
    async def test_tier_3_heuristic_fallback(self, sample_context, mock_redis):
        """Verify heuristic fallback when no empirical or causal data."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        # Setup: both empirical and causal fail
        mock_redis.get.side_effect = [
            None,  # Empirical
            None,  # Causal
        ]

        outcome = await reasoner.what_if("retry", sample_context, {"confidence": 0.6})

        assert outcome.prediction_source == "heuristic"

    @pytest.mark.asyncio
    async def test_fallback_on_redis_error(self, sample_context, mock_redis):
        """Verify graceful fallback to heuristic on Redis errors."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        # Setup: Redis throws error
        mock_redis.get.side_effect = Exception("Redis connection failed")

        outcome = await reasoner.what_if("retry", sample_context, {"confidence": 0.6})

        assert outcome.prediction_source == "heuristic"


# =============================================================================
# Tests: Side Effect Detection
# =============================================================================


class TestSideEffectDetection:
    """Tests for side effect severity assessment and detection."""

    def test_side_effect_severity_high(self):
        """Verify high-severity side effects are classified correctly."""
        reasoner = CounterfactualReasoner()

        assert reasoner._assess_side_effect_severity("state_mutation") == "high"
        assert reasoner._assess_side_effect_severity("irreversible_change") == "high"
        assert reasoner._assess_side_effect_severity("data_loss") == "high"

    def test_side_effect_severity_medium(self):
        """Verify medium-severity side effects are classified correctly."""
        reasoner = CounterfactualReasoner()

        assert reasoner._assess_side_effect_severity("latency_increase") == "medium"
        assert reasoner._assess_side_effect_severity("wait_time") == "medium"
        assert reasoner._assess_side_effect_severity("deadline_risk") == "medium"

    def test_side_effect_severity_low(self):
        """Verify low-severity side effects default to low."""
        reasoner = CounterfactualReasoner()

        assert reasoner._assess_side_effect_severity("user_notification") == "low"
        assert reasoner._assess_side_effect_severity("log_entry") == "low"

    def test_retry_side_effects(self, sample_context):
        """Verify retry option includes latency side effect."""
        reasoner = CounterfactualReasoner()

        outcome = reasoner._predict_heuristic("retry", sample_context, {"confidence": 0.6})

        assert any(e["type"] == "latency_increase" for e in outcome.side_effects)
        latency_effect = next(e for e in outcome.side_effects if e["type"] == "latency_increase")
        assert latency_effect["severity"] == "medium"

    def test_escalation_side_effects(self, sample_context):
        """Verify escalation option includes notification and wait side effects."""
        reasoner = CounterfactualReasoner()

        outcome = reasoner._predict_heuristic("escalate", sample_context, {"confidence": 0.9})

        effect_types = {e["type"] for e in outcome.side_effects}
        assert "user_notification" in effect_types
        assert "wait_time" in effect_types


# =============================================================================
# Tests: Convenience Methods
# =============================================================================


class TestConvenienceMethods:
    """Tests for decision-specific convenience methods."""

    @pytest.mark.asyncio
    async def test_predict_retry_outcome(self, sample_context, mock_redis):
        """Verify predict_retry_outcome convenience method."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        mock_redis.get.side_effect = [None, None]  # Fallback to heuristic

        outcome = await reasoner.predict_retry_outcome(sample_context)

        assert outcome.option == "retry"

    @pytest.mark.asyncio
    async def test_predict_escalation_outcome(self, sample_context, mock_redis):
        """Verify predict_escalation_outcome convenience method."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        mock_redis.get.side_effect = [None, None]  # Fallback to heuristic

        outcome = await reasoner.predict_escalation_outcome(sample_context)

        assert outcome.option == "escalate"

    @pytest.mark.asyncio
    async def test_predict_automation_outcome(self, sample_context, mock_redis):
        """Verify predict_automation_outcome convenience method."""
        reasoner = CounterfactualReasoner()
        reasoner.redis = mock_redis

        mock_redis.get.side_effect = [None, None]  # Fallback to heuristic

        outcome = await reasoner.predict_automation_outcome(sample_context)

        assert outcome.option == "automate"


# =============================================================================
# Tests: InterventionOutcome Serialization
# =============================================================================


class TestInterventionOutcomeSerialization:
    """Tests for InterventionOutcome data model."""

    def test_intervention_outcome_to_dict(self):
        """Verify InterventionOutcome serializes to dict correctly."""
        outcome = InterventionOutcome(
            option="retry",
            predicted_success_rate=0.75,
            side_effects=[
                {
                    "type": "latency_increase",
                    "frequency": 0.8,
                    "severity": "medium",
                }
            ],
            confidence=0.8,
            reasoning="Historical success rate",
            prediction_source="empirical",
            supporting_evidence=[{"type": "history_count", "value": 10}],
        )

        result = outcome.to_dict()

        assert result["option"] == "retry"
        assert result["predicted_success_rate"] == 0.75
        assert result["confidence"] == 0.8
        assert result["prediction_source"] == "empirical"
        assert len(result["side_effects"]) == 1
