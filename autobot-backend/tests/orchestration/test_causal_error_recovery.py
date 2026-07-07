# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test suite for causal error recovery system.

Tests recovery recommendations for various error scenarios:
- Network timeouts → retry with backoff
- Resource exhaustion → wait or scale
- Workflow design issues → restructure
- Cascading failures → proper detection
- Pattern learning and feedback loop

Issue #2154.

Note (#10870): autobot-backend/conftest.py stubs the heavy causal/agent_loop/
code_intelligence import chain (``orchestration.causal_error_recovery`` &co.) as
MagicMocks so the lightweight, types-only orchestration tests can collect without
the full backend stack.  This suite, however, exercises the *real* recovery logic
(action scoring, leaf-vs-downstream classification, pattern feedback), so it must
load the genuine modules.  We swap the stubs for the real implementations at import
time and restore the stubs on teardown so sibling test modules that rely on them are
unaffected — the same isolation contract used by ``tests/agent_loop/conftest.py``.
"""

import sys
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Real-module loading (#10870).
#
# The parent conftest replaces the causal/agent_loop/code_intelligence packages
# with MagicMock package stubs.  Awaiting the stubbed ``recommend_recovery`` raised
# "object MagicMock can't be used in 'await' expression".  Drop the stubs, import the
# real modules, then restore the exact objects we displaced so process-shared state is
# left untouched for other test files.
#
# Restoration strategy: capture only the EXACT conftest stub entries (by name),
# displace them, import real implementations, then on teardown re-insert only the
# displaced stubs and remove any NEW transitive deps added by our real imports.
#
# The original broad prefix-based scan (_STUBBED_PREFIXES startswith) was wrong:
# by the time this module's code runs during collection, the real orchestration
# package has already been fully imported by earlier test files (e.g.
# orchestration.success_criteria, orchestration.workflow_runner are all real).
# The broad scan captured ALL those real modules in _SAVED_STUBS, popped them,
# and on teardown re-inserted old objects — causing class identity splits and
# isinstance() failures in later test files.
# ---------------------------------------------------------------------------

# The exact set of module names that conftest.py replaced with MagicMock stubs.
# These are the ONLY entries we need to displace and restore.
_CONFTEST_STUB_NAMES: tuple = (
    "orchestration.causal_error_recovery",
    "orchestration.causal_error_analyzer",
    "orchestration.causal_validator",
    "agent_loop",
    "agent_loop.loop",
    "agent_loop.think_tool",
    "tools.parallel",
    "tools.parallel.executor",
    "code_intelligence",
)

# Save the current (stub) entries for the specific names we will displace.
_SAVED_STUBS: dict[str, object] = {name: sys.modules[name] for name in _CONFTEST_STUB_NAMES if name in sys.modules}

# Record all keys present before our real imports so we can compute the delta.
_KEYS_BEFORE_IMPORT: frozenset = frozenset(sys.modules)

# Displace only the specific stub entries we identified above.
for _name in _SAVED_STUBS:
    sys.modules.pop(_name, None)

from orchestration.causal_error_analyzer import (  # noqa: E402
    CausalErrorAnalysis,
    CausalErrorAnalyzer,
)
from orchestration.causal_error_recovery import (  # noqa: E402
    CausalErrorRecovery,
    RecoveryAction,
    RecoveryPlan,
)
from services.failure_pattern_detector import (  # noqa: E402
    FailurePattern,
    FailurePatternDetector,
)

# Keys added ONLY by our real imports — these are safe to remove on teardown.
# Keys that were already in _KEYS_BEFORE_IMPORT (real orchestration modules
# imported by earlier test files) are excluded and left untouched.
_KEYS_OUR_IMPORTS_ADDED: frozenset = frozenset(sys.modules) - _KEYS_BEFORE_IMPORT


@pytest.fixture(scope="module", autouse=True)
def _restore_conftest_stubs():
    """Restore the parent-conftest MagicMock stubs after this module's tests.

    Keeps the real modules loaded for the duration of this file, then puts the
    original stub objects back so sibling type-only orchestration tests (which
    depend on the stubbed import chain) see the state they expect.

    Only removes new transitive deps added by OUR imports and re-inserts the
    specific stub entries we displaced — never touches orchestration modules
    that were already real before this file's module-level code ran.
    """
    yield
    # Remove only the transitive deps that our real imports added.
    for _name in _KEYS_OUR_IMPORTS_ADDED:
        sys.modules.pop(_name, None)
    # Restore the specific stub entries we displaced at import time.
    for _name, _mod in _SAVED_STUBS.items():
        sys.modules[_name] = _mod  # type: ignore[assignment]


# =============================================================================
# Test CausalErrorRecovery
# =============================================================================


class TestCausalErrorRecovery:
    """Test recovery recommendation logic."""

    @pytest.fixture
    def recovery_system(self):
        """Create a recovery system instance."""
        return CausalErrorRecovery()

    @pytest.fixture
    def sample_timeout_analysis(self) -> CausalErrorAnalysis:
        """Sample causal analysis for network timeout."""
        return CausalErrorAnalysis(
            error_description="Connection timeout after 30s",
            think_result=MagicMock(
                reasoning="Network latency increased → Connection timeout",
                conclusion="Retry with backoff",
                confidence=0.85,
                risks_identified=["Network instability"],
            ),
            root_cause="Network latency",
            causal_chain="High latency → Connection reset → Timeout",
            confounders_identified=["DNS resolution"],
            confidence=0.85,
            recommended_action="Retry with backoff",
        )

    @pytest.fixture
    def sample_resource_analysis(self) -> CausalErrorAnalysis:
        """Sample causal analysis for resource exhaustion."""
        return CausalErrorAnalysis(
            error_description="Connection pool exhausted",
            think_result=MagicMock(
                reasoning="Too many concurrent connections → Pool empty",
                conclusion="Wait or scale",
                confidence=0.9,
                risks_identified=["Resource contention"],
            ),
            root_cause="Connection pool exhaustion",
            causal_chain="Concurrent requests → Pool limit reached → No connections available",
            confounders_identified=[],
            confidence=0.9,
            recommended_action="Wait for connections to release",
        )

    @pytest.mark.asyncio
    async def test_timeout_error_recovery_recommendation(self, recovery_system, sample_timeout_analysis):
        """Test that timeout errors recommend retry with backoff."""
        error = TimeoutError("Connection timeout")
        plan = await recovery_system.recommend_recovery(error, sample_timeout_analysis, {})

        assert plan.error_type == "TimeoutError"
        assert plan.root_cause == "Network latency"
        assert len(plan.recommended_actions) > 0

        # First action should be retry with backoff
        top_action = plan.recommended_actions[0]
        assert top_action.action in [
            RecoveryAction.RETRY_WITH_BACKOFF,
            RecoveryAction.RETRY_IMMEDIATELY,
        ]
        assert top_action.likelihood_to_succeed > 0.5
        assert plan.confidence > 0.7

    @pytest.mark.asyncio
    async def test_resource_exhaustion_recovery_recommendation(self, recovery_system, sample_resource_analysis):
        """Test that resource exhaustion recommends wait or scale."""
        error = RuntimeError("Connection pool exhausted")
        plan = await recovery_system.recommend_recovery(error, sample_resource_analysis, {})

        assert plan.root_cause == "Connection pool exhaustion"
        assert len(plan.recommended_actions) > 0

        # Should recommend wait or scale
        actions = [a.action for a in plan.recommended_actions]
        assert RecoveryAction.WAIT_FOR_DEPENDENCY in actions or RecoveryAction.SCALE_RESOURCES in actions

    @pytest.mark.asyncio
    async def test_permission_error_recovery_escalates(self, recovery_system):
        """Test that permission errors recommend escalation."""
        error = PermissionError("Access denied")
        analysis = CausalErrorAnalysis(
            error_description="Access denied",
            think_result=MagicMock(
                reasoning="User lacks permissions → Access denied",
                conclusion="Escalate to operator",
                confidence=0.95,
                risks_identified=[],
            ),
            root_cause="Insufficient permissions",
            causal_chain="Missing permission → Access denied",
            confounders_identified=[],
            confidence=0.95,
            recommended_action="Escalate",
        )

        plan = await recovery_system.recommend_recovery(error, analysis, {})

        assert plan.root_cause == "Insufficient permissions"
        # Should recommend escalation
        actions = [a.action for a in plan.recommended_actions]
        assert RecoveryAction.ESCALATE in actions

    @pytest.mark.asyncio
    async def test_leaf_vs_downstream_error_classification(self, recovery_system):
        """Test that errors are correctly classified as leaf vs downstream."""
        # Leaf error: single cause
        leaf_analysis = CausalErrorAnalysis(
            error_description="File not found",
            think_result=MagicMock(),
            root_cause="Missing file",
            causal_chain="File missing",
            confounders_identified=[],
            confidence=0.9,
            recommended_action="Retry",
        )

        # Downstream error: cascading
        downstream_analysis = CausalErrorAnalysis(
            error_description="Timeout",
            think_result=MagicMock(),
            root_cause="Database down",
            causal_chain="Database down → Connection timeout → Request timeout → User sees timeout",
            confounders_identified=["Network latency"],
            confidence=0.8,
            recommended_action="Wait",
        )

        error = TimeoutError("Request timeout")

        leaf_plan = await recovery_system.recommend_recovery(error, leaf_analysis, {})
        downstream_plan = await recovery_system.recommend_recovery(error, downstream_analysis, {})

        assert leaf_plan.is_leaf_error is True
        assert downstream_plan.is_leaf_error is False

    @pytest.mark.asyncio
    async def test_recovery_action_scoring(self, recovery_system):
        """Test that recovery actions are scored and ranked correctly."""
        error = TimeoutError("Connection timeout")
        analysis = CausalErrorAnalysis(
            error_description="Timeout",
            think_result=MagicMock(),
            root_cause="Network latency",
            causal_chain="Network slow → Timeout",
            confounders_identified=[],
            confidence=0.9,
            recommended_action="Retry",
        )

        plan = await recovery_system.recommend_recovery(error, analysis, {})

        # Actions should be ranked by score
        assert len(plan.recommended_actions) > 0
        scores = [a.score for a in plan.recommended_actions]
        assert scores == sorted(scores, reverse=True)

        # All actions should have reasonable scores
        for action in plan.recommended_actions:
            assert 0 <= action.likelihood_to_succeed <= 1.0
            assert 0 <= action.cost <= 1.0
            assert 0 <= action.risk <= 1.0

    @pytest.mark.asyncio
    async def test_record_recovery_attempt_success(self, recovery_system):
        """Test recording successful recovery attempts."""
        plan = RecoveryPlan(
            error_id="test_error_1",
            error_type="TimeoutError",
            root_cause="Network latency",
            causal_chain="Latency → Timeout",
            is_leaf_error=True,
            is_known_pattern=False,
            pattern_frequency=0,
        )

        # Should not raise
        await recovery_system.record_recovery_attempt(
            plan,
            RecoveryAction.RETRY_WITH_BACKOFF,
            success=True,
            outcome="Connection re-established",
        )

    @pytest.mark.asyncio
    async def test_top_three_actions_returned(self, recovery_system):
        """Test that only top 3 recovery actions are returned."""
        error = TimeoutError("Timeout")
        analysis = CausalErrorAnalysis(
            error_description="Timeout",
            think_result=MagicMock(),
            root_cause="Network issue",
            causal_chain="Network → Timeout",
            confounders_identified=[],
            confidence=0.8,
            recommended_action="Retry",
        )

        plan = await recovery_system.recommend_recovery(error, analysis, {})

        # Should have at most 3 actions
        assert len(plan.recommended_actions) <= 3


# =============================================================================
# Test FailurePatternDetector
# =============================================================================


class TestFailurePatternDetector:
    """Test failure pattern detection and learning."""

    @pytest.fixture
    def detector(self):
        """Create a pattern detector instance."""
        return FailurePatternDetector()

    def test_hash_causal_chain_consistency(self, detector):
        """Test that hashing is consistent."""
        chain1 = "Database down → Connection timeout"
        hash1a = detector.hash_causal_chain(chain1)
        hash1b = detector.hash_causal_chain(chain1)

        assert hash1a == hash1b

    def test_hash_causal_chain_different_chains(self, detector):
        """Test that different chains produce different hashes."""
        chain1 = "Database down → Connection timeout"
        chain2 = "Network latency → Connection timeout"

        hash1 = detector.hash_causal_chain(chain1)
        hash2 = detector.hash_causal_chain(chain2)

        assert hash1 != hash2

    @pytest.mark.asyncio
    async def test_learn_new_pattern(self, detector):
        """Test learning a new failure pattern."""
        causal_chain = "Database unavailable → Connection refused"
        error_type = "ConnectionError"

        pattern = await detector.learn_pattern(causal_chain, error_type)

        assert pattern.causal_chain == causal_chain
        assert error_type in pattern.error_types
        assert pattern.occurrence_count == 1

    @pytest.mark.asyncio
    async def test_detect_known_pattern(self, detector):
        """Test detecting a previously learned pattern."""
        causal_chain = "Pool exhaustion → No connections"

        # First occurrence: learn the pattern
        await detector.learn_pattern(causal_chain, "TimeoutError")

        # Second occurrence: should detect as known
        detected = await detector.detect_pattern(causal_chain, "TimeoutError")

        assert detected is not None
        assert detected.causal_chain == causal_chain

    @pytest.mark.asyncio
    async def test_pattern_success_rate_tracking(self, detector):
        """Test that resolution success rates are tracked."""
        causal_chain = "Connection failed → Retry needed"

        # Learn pattern
        pattern = await detector.learn_pattern(causal_chain, "ConnectionError", successful_action="retry_with_backoff")

        # Occurrence 1: success
        assert pattern.occurrence_count >= 1
        assert "retry_with_backoff" in pattern.successful_resolutions

        # Learn again with success
        pattern = await detector.learn_pattern(causal_chain, "ConnectionError", successful_action="retry_with_backoff")

        # Success rate should improve
        assert pattern.resolution_success_rate >= 0.5

    @pytest.mark.asyncio
    async def test_confidence_increases_with_success_history(self, detector):
        """Test that confidence increases as resolution history grows."""
        causal_chain = "Network timeout → Retry needed"

        # Initial pattern
        p1 = await detector.learn_pattern(causal_chain, "TimeoutError")
        initial_confidence = p1.confidence

        # Multiple successes
        for _ in range(5):
            p = await detector.learn_pattern(causal_chain, "TimeoutError", successful_action="retry_with_backoff")

        final_confidence = p.confidence

        # Confidence should increase
        assert final_confidence >= initial_confidence

    @pytest.mark.asyncio
    async def test_list_patterns_sorted_by_frequency(self, detector):
        """Test that patterns are listed in frequency order."""
        # Learn multiple patterns with different frequencies
        await detector.learn_pattern("Pattern A", "ErrorA")
        await detector.learn_pattern("Pattern A", "ErrorA")
        await detector.learn_pattern("Pattern A", "ErrorA")

        await detector.learn_pattern("Pattern B", "ErrorB")
        await detector.learn_pattern("Pattern B", "ErrorB")

        await detector.learn_pattern("Pattern C", "ErrorC")

        patterns = await detector.list_known_patterns(limit=10)

        # Should be sorted by occurrence count (descending)
        if len(patterns) > 1:
            for i in range(len(patterns) - 1):
                assert patterns[i].occurrence_count >= patterns[i + 1].occurrence_count

    @pytest.mark.asyncio
    async def test_get_pattern_statistics(self, detector):
        """Test getting overall pattern statistics."""
        # Clear existing patterns
        await detector.clear_patterns()

        # Learn patterns
        await detector.learn_pattern("Chain A", "ErrorA", "fix_a")
        await detector.learn_pattern("Chain A", "ErrorA", "fix_a")
        await detector.learn_pattern("Chain B", "ErrorB", "fix_b")

        stats = await detector.get_pattern_statistics()

        assert stats["total_patterns"] >= 1
        assert stats["total_occurrences"] >= 3
        assert stats["average_success_rate"] >= 0.0

    @pytest.mark.asyncio
    async def test_clear_patterns(self, detector):
        """Test clearing all learned patterns."""
        # Learn a pattern
        await detector.learn_pattern("Chain A", "ErrorA")

        # Clear
        await detector.clear_patterns()

        # Should be gone
        detected = await detector.detect_pattern("Chain A", "ErrorA")
        assert detected is None


# =============================================================================
# Integration Tests
# =============================================================================


class TestCausalErrorRecoveryIntegration:
    """Integration tests for the full recovery pipeline."""

    @pytest.mark.asyncio
    async def test_error_analysis_to_recovery_pipeline(self):
        """Test full pipeline: error → causal analysis → recovery plan."""
        # Mock the causal analyzer
        CausalErrorAnalyzer()
        recovery_sys = CausalErrorRecovery()

        # Simulate a timeout error
        error = TimeoutError("Connection timed out after 30s")

        # Mock causal analysis result
        causal_analysis = CausalErrorAnalysis(
            error_description="Connection timeout",
            think_result=MagicMock(),
            root_cause="Network latency",
            causal_chain="Network congestion → High latency → Timeout",
            confounders_identified=["DNS resolution"],
            confidence=0.85,
            recommended_action="Retry with exponential backoff",
        )

        # Get recovery plan
        plan = await recovery_sys.recommend_recovery(error, causal_analysis, {"step_id": "step_1"})

        # Verify plan
        assert plan.error_type == "TimeoutError"
        assert plan.root_cause == "Network latency"
        assert len(plan.recommended_actions) > 0
        assert plan.confidence > 0.7

        # Recommended action should be retry-related
        top_action = plan.recommended_actions[0]
        assert "retry" in top_action.action.value.lower() or "wait" in top_action.action.value.lower()

    @pytest.mark.asyncio
    async def test_pattern_feedback_improves_confidence(self):
        """Test that feedback loops improve confidence in recommendations."""
        detector = FailurePatternDetector()
        recovery_sys = CausalErrorRecovery()

        causal_chain = "Pool exhaustion → Connection denied"
        error = RuntimeError("Connection denied")

        # First encounter: low confidence (no history)
        analysis1 = CausalErrorAnalysis(
            error_description="Connection denied",
            think_result=MagicMock(),
            root_cause="Resource exhaustion",
            causal_chain=causal_chain,
            confounders_identified=[],
            confidence=0.7,
            recommended_action="Wait or scale",
        )
        plan1 = await recovery_sys.recommend_recovery(error, analysis1, {})
        confidence1 = plan1.confidence

        # Learn and record success
        await detector.learn_pattern(causal_chain, "RuntimeError", successful_action="wait_for_dependency")
        await recovery_sys.record_recovery_attempt(plan1, RecoveryAction.WAIT_FOR_DEPENDENCY, success=True)

        # Second encounter: should be known pattern now, higher confidence
        is_known = await detector.detect_pattern(causal_chain, "RuntimeError")
        assert is_known is not None

        # New plan should reference known pattern
        analysis2 = CausalErrorAnalysis(
            error_description="Connection denied",
            think_result=MagicMock(),
            root_cause="Resource exhaustion",
            causal_chain=causal_chain,
            confounders_identified=[],
            confidence=0.75,
            recommended_action="Wait or scale",
        )
        plan2 = await recovery_sys.recommend_recovery(error, analysis2, {})

        # Confidence should increase for known pattern
        assert plan2.is_known_pattern is True
        assert plan2.confidence >= confidence1


# =============================================================================
# Smoke Tests
# =============================================================================


class TestRecoverySystemSmoke:
    """Smoke tests to ensure basic functionality."""

    @pytest.mark.asyncio
    async def test_recovery_plan_serialization(self):
        """Test that recovery plans can be serialized/deserialized."""
        from orchestration.causal_error_recovery import RecoveryAction_

        plan = RecoveryPlan(
            error_id="test_1",
            error_type="TimeoutError",
            root_cause="Network issue",
            causal_chain="Timeout",
            is_leaf_error=True,
            is_known_pattern=False,
            pattern_frequency=0,
            recommended_actions=[
                RecoveryAction_(
                    action=RecoveryAction.RETRY_WITH_BACKOFF,
                    description="Retry",
                    likelihood_to_succeed=0.8,
                    cost=0.1,
                    risk=0.05,
                    expected_outcome="Success",
                )
            ],
            confidence=0.85,
        )

        # Serialize
        data = plan.to_dict()
        assert "error_id" in data
        assert "recommended_actions" in data

        # Deserialize
        plan2 = RecoveryPlan.from_dict(data)
        assert plan2.error_id == plan.error_id
        assert len(plan2.recommended_actions) == len(plan.recommended_actions)

    @pytest.mark.asyncio
    async def test_pattern_serialization(self):
        """Test that patterns can be serialized/deserialized."""
        pattern = FailurePattern(
            pattern_id="pat_1",
            causal_chain="Test chain",
            error_types=["ErrorA", "ErrorB"],
            occurrence_count=5,
            successful_resolutions=["action_a"],
            resolution_success_rate=0.8,
            confidence=0.9,
        )

        # Serialize
        data = pattern.to_dict()
        assert "pattern_id" in data

        # Deserialize
        pattern2 = FailurePattern.from_dict(data)
        assert pattern2.pattern_id == pattern.pattern_id
        assert pattern2.occurrence_count == pattern.occurrence_count


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
