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

# The exact set of stubbed module names the real causal import chain needs
# displaced (#11796): causal_error_analyzer only imports agent_loop.think_tool
# and agent_loop.types (types is never stubbed).  The parent ``agent_loop``
# entry must NOT be popped — the root-conftest stub (and tests/search's
# conftest wiring) carries a real ``__path__``, so ``agent_loop.think_tool``
# re-imports from disk underneath it, and popping the parent forced a full
# real ``agent_loop/__init__`` re-import that replaced the package identity
# mid-session for every later-collected test (tests/search lost its wired
# ``agent_loop.search`` attribute).  Same for the old ``agent_loop.loop`` /
# ``tools.parallel*`` / ``code_intelligence`` entries — nothing in this
# module's chain imports them.
_CONFTEST_STUB_NAMES: tuple = (
    "orchestration.causal_error_recovery",
    "orchestration.causal_error_analyzer",
    "orchestration.causal_validator",
    "agent_loop.think_tool",
)

# Save the current (stub) entries for the specific names we will displace.
_SAVED_STUBS: dict[str, object] = {name: sys.modules[name] for name in _CONFTEST_STUB_NAMES if name in sys.modules}

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

# ---------------------------------------------------------------------------
# Real-symbol anchor (#13162).
#
# Displacing the stubs above is only half the contract: the names this module
# imported must still be the REAL ones when the tests run. If anything replaces
# a symbol in the loaded module's globals with a MagicMock (the shape the root
# conftest's stub decoration used to have), the real ``recommend_recovery()``
# keeps running but returns ``RecoveryPlan(...)`` as a mock — ``plan.error_type``
# compares a MagicMock against a string, and ``plan.causal_chain.encode()``
# reaches ``hashlib.md5`` as a non-buffer. Both were live CI failures whose
# tracebacks pointed at production code that was in fact behaving correctly.
#
# Assert the identity once, at import, so any future clobber is a single loud
# error here instead of two misleading failures deep inside the recovery system.
# ---------------------------------------------------------------------------

_CER = sys.modules["orchestration.causal_error_recovery"]
assert _CER.RecoveryPlan is RecoveryPlan and _CER.CausalErrorRecovery is CausalErrorRecovery, (
    "orchestration.causal_error_recovery symbols were replaced after import — "
    "the module in sys.modules no longer matches what this test imported, so the "
    "recovery system under test would be exercised through mocks."
)


@pytest.fixture(scope="module", autouse=True)
def _restore_conftest_stubs():
    """Restore the displaced parent-conftest stubs after this module's tests.

    #11796: the old teardown also popped every key our module-scope imports
    happened to add (``_KEYS_OUR_IMPORTS_ADDED``) — but this fixture tears
    down at RUN time, long after collection finished, and by then those keys
    are shared by every later-collected test module (e.g. popping
    ``security.content_firewall`` split the module identity out from under
    tests/test_content_firewall.py, making its monkeypatch inert).  Likewise
    re-inserting the saved ``agent_loop``/``tools.parallel``/
    ``code_intelligence`` stubs replaced REAL packages mid-run for every
    later test (tests/search lost ``agent_loop.search``).  Teardown now
    restores ONLY the displaced ``orchestration.*`` stub entries, which
    sibling type-only orchestration tests patch by name; everything else
    stays as the run left it.
    """
    yield
    for _name, _mod in _SAVED_STUBS.items():
        if _name.startswith("orchestration."):
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


class _FakeAsyncRedis:
    """Minimal in-memory async Redis stand-in for the pattern-detector tests.

    Implements only the ops ``FailurePatternDetector`` uses
    (get/set/sadd/smembers/expire) so the learn→detect→statistics roundtrip
    works without a live Redis. Previously these tests hit the real client,
    whose circuit breaker is open in CI, so every op returned ``None`` and the
    detector silently no-opped — 4 tests failed on ``assert ... is not None``
    (#11144).
    """

    def __init__(self):
        self._kv = {}
        self._sets = {}

    async def get(self, key):
        return self._kv.get(key)

    async def set(self, key, value, ex=None):
        self._kv[key] = value
        return True

    async def sadd(self, key, *members):
        self._sets.setdefault(key, set()).update(members)
        return len(members)

    async def smembers(self, key):
        return set(self._sets.get(key, set()))

    async def expire(self, key, ttl):
        return True

    async def delete(self, key):
        self._kv.pop(key, None)
        self._sets.pop(key, None)
        return True


class _FakeSyncRedis:
    """Minimal in-memory *sync* Redis stand-in for ``CausalErrorRecovery``.

    ``CausalErrorRecovery`` uses a synchronous client (get/incr/expire/set/hset);
    like the detector it silently no-ops when the real client's circuit breaker
    is open, which broke the feedback-loop integration test (#11144).
    """

    def __init__(self):
        self._kv = {}
        self._hashes = {}

    def get(self, key):
        return self._kv.get(key)

    def set(self, key, value, ex=None):
        self._kv[key] = value
        return True

    def incr(self, key):
        self._kv[key] = str(int(self._kv.get(key, 0)) + 1)
        return int(self._kv[key])

    def expire(self, key, ttl):
        return True

    def hset(self, key, *args, **kwargs):
        mapping = kwargs.get("mapping") or {}
        if len(args) >= 2:
            mapping[args[0]] = args[1]
        self._hashes.setdefault(key, {}).update(mapping)
        return len(mapping)


def _make_detector_with_fake_redis() -> FailurePatternDetector:
    """A detector wired to an in-memory Redis so persistence roundtrips (#11144)."""
    detector = FailurePatternDetector()
    detector._redis = _FakeAsyncRedis()
    return detector


class TestFailurePatternDetector:
    """Test failure pattern detection and learning."""

    @pytest.fixture
    def detector(self):
        """Create a pattern detector instance backed by an in-memory Redis."""
        return _make_detector_with_fake_redis()

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
        detector = _make_detector_with_fake_redis()
        recovery_sys = CausalErrorRecovery()
        recovery_sys._redis = _FakeSyncRedis()  # in-memory sync Redis so feedback roundtrips (#11144)

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
