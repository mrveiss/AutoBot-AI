# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Classification degradation must be observable and distinguishable (#13807).

`COMPLEX` used to be the answer to four different questions: the request really
is complex, the classification module is not importable, the agent failed to
construct, or the call raised. One output for four states meant a classifier
that had been dead since boot looked exactly like one working correctly — the
only evidence was a single startup warning that scrolls away.

These tests pin the distinction itself, not the fallback value. The fallback
staying `COMPLEX` is deliberate (callers routing on complexity keep working);
what must never come back is being unable to tell a judgement from a default.
"""

import asyncio
from types import SimpleNamespace

import pytest

from autobot_types import ClassificationState, ComplexityVerdict, TaskComplexity


class _StubOrchestrator:
    """The classification surface of Orchestrator, without its constructor.

    Orchestrator.__init__ builds a KnowledgeBase, an LLM service and a memory
    manager; none of that is what this behaviour depends on. Binding the real
    methods onto a bare object keeps the test about classification.
    """

    def __init__(self, agent, state, detail=None):
        from orchestrator import Orchestrator

        self.classification_agent = agent
        self.classification_state = state
        self.classification_detail = detail
        self._classification_fallback_logged = False
        self.classify_request_complexity_verdict = Orchestrator.classify_request_complexity_verdict.__get__(self)
        self.classify_request_complexity = Orchestrator.classify_request_complexity.__get__(self)
        self._log_classification_fallback = Orchestrator._log_classification_fallback.__get__(self)


def _verdict(orch, request="List files"):
    return asyncio.run(orch.classify_request_complexity_verdict(request))


def test_unavailable_classifier_reports_unavailable_not_a_verdict():
    """The AC: an absent classifier must not answer as if it judged the request."""
    orch = _StubOrchestrator(None, ClassificationState.UNAVAILABLE_INIT, "AgentConfigurationError: no provider")

    verdict = _verdict(orch)

    assert verdict.classified is False
    assert verdict.state is ClassificationState.UNAVAILABLE_INIT
    assert "no provider" in verdict.detail
    # The routing value is unchanged — this is about knowing it is a default.
    assert verdict.complexity is TaskComplexity.COMPLEX


def test_a_real_complex_verdict_is_distinguishable_from_the_fallback():
    """Same complexity, different provenance — the two must not compare equal."""
    agent = SimpleNamespace(
        classify_user_request=lambda _r: _completed(SimpleNamespace(complexity=TaskComplexity.COMPLEX))
    )
    judged = _verdict(_StubOrchestrator(agent, ClassificationState.CLASSIFIED))
    defaulted = _verdict(_StubOrchestrator(None, ClassificationState.UNAVAILABLE_IMPORT, "not importable"))

    assert judged.complexity == defaulted.complexity  # the old signal
    assert judged.classified is True and defaulted.classified is False  # the new one
    assert judged != defaulted


def test_classifier_raising_is_its_own_state():
    """A raising classifier is not the same as an absent one."""

    def _boom(_request):
        raise RuntimeError("model timeout")

    orch = _StubOrchestrator(SimpleNamespace(classify_user_request=_boom), ClassificationState.CLASSIFIED)

    verdict = _verdict(orch)

    assert verdict.state is ClassificationState.FAILED
    assert verdict.classified is False
    assert "model timeout" in verdict.detail


def test_a_simple_request_is_still_classified_simple():
    """The guard must not turn every request into a fallback."""
    agent = SimpleNamespace(
        classify_user_request=lambda _r: _completed(SimpleNamespace(complexity=TaskComplexity.SIMPLE))
    )

    verdict = _verdict(_StubOrchestrator(agent, ClassificationState.CLASSIFIED))

    assert verdict.complexity is TaskComplexity.SIMPLE
    assert verdict.classified is True


def test_legacy_callers_still_get_a_bare_complexity():
    """classify_request_complexity keeps its contract for existing callers."""
    orch = _StubOrchestrator(None, ClassificationState.UNAVAILABLE_INIT, "boom")

    result = asyncio.run(orch.classify_request_complexity("List files"))

    assert result is TaskComplexity.COMPLEX
    assert not isinstance(result, ComplexityVerdict)


def test_fallback_warns_once_not_per_request(caplog):
    """Per-request logging would bury the signal; silence is what hid it before."""
    orch = _StubOrchestrator(None, ClassificationState.UNAVAILABLE_INIT, "boom")

    with caplog.at_level("WARNING"):
        for _ in range(5):
            _verdict(orch)

    hits = [r for r in caplog.records if "every request is being defaulted" in r.getMessage()]
    assert len(hits) == 1


@pytest.mark.parametrize(
    "env_value,should_raise",
    [("true", True), ("1", True), ("yes", True), ("false", False), ("", False)],
)
def test_require_classification_env_decides_fail_fast(monkeypatch, env_value, should_raise):
    """#13807 decision: non-fatal by default, fatal only when a deployment asks.

    Local and test runs must keep working without a provider; a deployment that
    depends on classification opts into a startup failure rather than silently
    defaulting every request.
    """
    from orchestrator import Orchestrator

    monkeypatch.setenv("AUTOBOT_REQUIRE_CLASSIFICATION", env_value)
    orch = _StubOrchestrator(None, ClassificationState.UNAVAILABLE_INIT, "no provider")
    enforce = Orchestrator._enforce_classification_requirement.__get__(orch)

    if should_raise:
        with pytest.raises(RuntimeError, match="AUTOBOT_REQUIRE_CLASSIFICATION"):
            enforce()
    else:
        enforce()


def _completed(value):
    """Wrap a value in an already-finished awaitable."""

    async def _coro():
        return value

    return _coro()
