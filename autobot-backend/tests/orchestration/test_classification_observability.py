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

from autobot_types import (
    ClassificationAvailability,
    ClassificationState,
    TaskComplexity,
)


class _StubOrchestrator:
    """The classification surface of Orchestrator, without its constructor.

    Orchestrator.__init__ builds a KnowledgeBase, an LLM service and a memory
    manager; none of that is what this behaviour depends on. Binding the real
    methods onto a bare object keeps the test about classification.
    """

    def __init__(self, agent, availability, detail=None):
        from orchestrator import Orchestrator

        self.classification_agent = agent
        self.classification_availability = availability
        self.classification_detail = detail
        self.last_classification_state = None
        self._classification_fallback_logged = False
        for name in (
            "classify_request_complexity_verdict",
            "classify_request_complexity",
            "_classify",
            "_log_classification_fallback",
        ):
            setattr(self, name, getattr(Orchestrator, name).__get__(self))


def _verdict(orch, request="List files"):
    return asyncio.run(orch.classify_request_complexity_verdict(request))


def test_unavailable_classifier_reports_unavailable_not_a_verdict():
    """The AC: an absent classifier must not answer as if it judged the request."""
    orch = _StubOrchestrator(None, ClassificationAvailability.UNAVAILABLE_INIT, "AgentConfigurationError")

    verdict = _verdict(orch)

    assert verdict.classified is False
    assert verdict.state is ClassificationState.UNAVAILABLE_INIT
    assert verdict.detail == "AgentConfigurationError"
    # The routing value is unchanged — this is about knowing it is a default.
    assert verdict.complexity is TaskComplexity.COMPLEX


def test_a_real_complex_verdict_is_distinguishable_from_the_fallback():
    """Same complexity, different provenance — the two must not compare equal."""
    agent = SimpleNamespace(
        classify_user_request=lambda _r: _completed(SimpleNamespace(complexity=TaskComplexity.COMPLEX))
    )
    judged = _verdict(_StubOrchestrator(agent, ClassificationAvailability.AVAILABLE))
    defaulted = _verdict(_StubOrchestrator(None, ClassificationAvailability.UNAVAILABLE_IMPORT, "not importable"))

    assert judged.complexity == defaulted.complexity  # the old signal
    assert judged.classified is True and defaulted.classified is False  # the new one


def test_classifier_raising_is_its_own_state():
    """A raising classifier is not the same as an absent one."""

    def _boom(_request):
        raise RuntimeError("model timeout")

    orch = _StubOrchestrator(SimpleNamespace(classify_user_request=_boom), ClassificationAvailability.AVAILABLE)

    verdict = _verdict(orch)

    assert verdict.state is ClassificationState.FAILED
    assert verdict.classified is False
    # Type only: this value reaches an API payload, and provider errors carry
    # endpoints and paths. The message stays in the log.
    assert verdict.detail == "RuntimeError"
    assert "model timeout" not in (verdict.detail or "")


def test_a_simple_request_is_still_classified_simple():
    """The guard must not turn every request into a fallback."""
    agent = SimpleNamespace(
        classify_user_request=lambda _r: _completed(SimpleNamespace(complexity=TaskComplexity.SIMPLE))
    )

    verdict = _verdict(_StubOrchestrator(agent, ClassificationAvailability.AVAILABLE))

    assert verdict.complexity is TaskComplexity.SIMPLE
    assert verdict.classified is True


def test_legacy_callers_still_get_a_bare_complexity():
    """classify_request_complexity keeps its contract for existing callers."""
    orch = _StubOrchestrator(None, ClassificationAvailability.UNAVAILABLE_INIT, "boom")

    result = asyncio.run(orch.classify_request_complexity("List files"))

    assert result is TaskComplexity.COMPLEX


def test_fallback_warns_once_not_per_request(caplog):
    """Per-request logging would bury the signal; silence is what hid it before."""
    orch = _StubOrchestrator(None, ClassificationAvailability.UNAVAILABLE_INIT, "boom")

    with caplog.at_level("WARNING"):
        for _ in range(5):
            _verdict(orch)

    hits = [r for r in caplog.records if "being defaulted to COMPLEX" in r.getMessage()]
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
    orch = _StubOrchestrator(None, ClassificationAvailability.UNAVAILABLE_INIT, "no provider")
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


# ---------------------------------------------------------------------------
# _init_classification_agent — the state machine itself.
#
# The stub above exercises the request path but hands the availability in
# pre-made, so it never proved that init records the right thing, nor that init
# calls the fail-fast guard at all. These drive the real method.
# ---------------------------------------------------------------------------


class _BareOrchestrator:
    """An object with only what _init_classification_agent touches."""

    def __init__(self):
        import orchestrator as orch_mod

        self._init_classification_agent = orch_mod.Orchestrator._init_classification_agent.__get__(self)
        self._enforce_classification_requirement = orch_mod.Orchestrator._enforce_classification_requirement.__get__(
            self
        )


def test_init_records_why_the_module_is_unavailable(monkeypatch):
    """The UNAVAILABLE_IMPORT branch — previously uncovered entirely."""
    import orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "CLASSIFICATION_AVAILABLE", False)
    orch = _BareOrchestrator()

    orch._init_classification_agent()

    assert orch.classification_agent is None
    assert orch.classification_availability is ClassificationAvailability.UNAVAILABLE_IMPORT
    assert orch.last_classification_state is None  # nothing has been classified yet


def test_init_records_why_construction_failed(monkeypatch):
    """A construction failure must name itself, not just log and vanish."""
    import orchestrator as orch_mod

    def _explode():
        raise RuntimeError("no provider configured")

    monkeypatch.setattr(orch_mod, "CLASSIFICATION_AVAILABLE", True)
    monkeypatch.setattr(orch_mod, "GemmaClassificationAgent", _explode)
    orch = _BareOrchestrator()

    orch._init_classification_agent()

    assert orch.classification_agent is None
    assert orch.classification_availability is ClassificationAvailability.UNAVAILABLE_INIT
    # The type only — provider errors carry endpoints and paths, and this value
    # reaches an API payload. The full text stays in the log.
    assert orch.classification_detail == "RuntimeError"
    assert "no provider configured" not in (orch.classification_detail or "")


def test_init_marks_a_working_classifier_available(monkeypatch):
    import orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "CLASSIFICATION_AVAILABLE", True)
    monkeypatch.setattr(orch_mod, "GemmaClassificationAgent", lambda: SimpleNamespace())
    orch = _BareOrchestrator()

    orch._init_classification_agent()

    assert orch.classification_agent is not None
    assert orch.classification_availability is ClassificationAvailability.AVAILABLE


def test_init_actually_calls_the_fail_fast_guard(monkeypatch):
    """Deleting the guard's call sites must fail a test, not pass quietly."""
    import orchestrator as orch_mod

    monkeypatch.setenv("AUTOBOT_REQUIRE_CLASSIFICATION", "true")
    monkeypatch.setattr(orch_mod, "CLASSIFICATION_AVAILABLE", False)
    orch = _BareOrchestrator()

    with pytest.raises(RuntimeError, match="AUTOBOT_REQUIRE_CLASSIFICATION"):
        orch._init_classification_agent()


def test_a_classifier_that_builds_then_always_raises_is_visible():
    """The degradation the first cut still hid.

    Availability says AVAILABLE and classification_enabled is True, so a status
    reader looking only at those calls this healthy. last_classification_state
    is what shows that nothing is actually being classified.
    """

    def _boom(_request):
        raise RuntimeError("model timeout")

    orch = _StubOrchestrator(SimpleNamespace(classify_user_request=_boom), ClassificationAvailability.AVAILABLE)

    _verdict(orch)

    assert orch.classification_availability is ClassificationAvailability.AVAILABLE
    assert orch.last_classification_state is ClassificationState.FAILED


def test_last_state_tracks_the_most_recent_request():
    """A recovered classifier must stop reporting the old failure."""
    calls = {"n": 0}

    def _flaky(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return _completed(SimpleNamespace(complexity=TaskComplexity.SIMPLE))

    orch = _StubOrchestrator(SimpleNamespace(classify_user_request=_flaky), ClassificationAvailability.AVAILABLE)

    _verdict(orch)
    assert orch.last_classification_state is ClassificationState.FAILED

    _verdict(orch)
    assert orch.last_classification_state is ClassificationState.CLASSIFIED
