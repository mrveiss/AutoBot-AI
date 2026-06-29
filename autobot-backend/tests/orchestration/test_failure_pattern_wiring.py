# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for FailurePatternDetector wiring into workflow failure handling (#10628).

Verifies the previously-unwired detector is now driven on workflow failure:
- learn_pattern is always called (write side)
- a known recurring pattern is surfaced as `known_failure_pattern` (read side)
- a first-time failure returns no annotation
- detector/Redis errors never break failure handling

Moved from tests/enhanced_orchestration/ to tests/orchestration/ (issue #10666 B3).
"""

from __future__ import annotations

import types

import pytest

from orchestration.workflow_runner import WorkflowRunner


class _FakeDetector:
    def __init__(self, prior_count: int) -> None:
        self.prior = prior_count
        self.learned: list = []

    async def detect_pattern(self, causal_chain: str, error_type: str):
        if self.prior <= 0:
            return None
        return types.SimpleNamespace(pattern_id="p1", occurrence_count=self.prior, resolution_success_rate=0.5)

    async def learn_pattern(self, causal_chain: str, error_type: str, successful_action=None):
        self.learned.append((causal_chain, error_type))
        return None


def _plan(strategy_value: str):
    return types.SimpleNamespace(strategy=types.SimpleNamespace(value=strategy_value))


@pytest.mark.asyncio
async def test_recurring_failure_is_flagged(monkeypatch):
    det = _FakeDetector(prior_count=3)
    import services.failure_pattern_detector as fpd

    monkeypatch.setattr(fpd, "get_pattern_detector", lambda: det)

    info = await WorkflowRunner._record_failure_pattern(object(), _plan("sequential"), ValueError("boom"))

    assert det.learned == [("workflow:sequential:ValueError", "ValueError")]  # write happened
    assert info == {"pattern_id": "p1", "occurrences": 3, "resolution_success_rate": 0.5}


@pytest.mark.asyncio
async def test_first_time_failure_returns_no_annotation(monkeypatch):
    det = _FakeDetector(prior_count=0)
    import services.failure_pattern_detector as fpd

    monkeypatch.setattr(fpd, "get_pattern_detector", lambda: det)

    info = await WorkflowRunner._record_failure_pattern(object(), _plan("parallel"), RuntimeError("x"))

    assert info is None
    assert det.learned == [("workflow:parallel:RuntimeError", "RuntimeError")]  # still learned


@pytest.mark.asyncio
async def test_detector_error_never_breaks_failure_handling(monkeypatch):
    import services.failure_pattern_detector as fpd

    def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(fpd, "get_pattern_detector", _boom)

    # Must swallow and return None rather than propagate.
    info = await WorkflowRunner._record_failure_pattern(object(), _plan("sequential"), ValueError("e"))
    assert info is None


class _FakeRunner:
    """Stand-in exposing only what _handle_workflow_execution_failure touches."""

    def __init__(self, recovery_result):
        self.record_calls = 0
        self._recovery_result = recovery_result

    async def _record_failure_pattern(self, plan, error):
        self.record_calls += 1
        return {"pattern_id": "p", "occurrences": 2, "resolution_success_rate": 0.0}

    async def _attempt_failure_recovery(self, plan, error, results, _depth):
        return self._recovery_result


@pytest.mark.asyncio
async def test_handle_records_once_at_top_level_and_annotates_failure():
    fake = _FakeRunner({"plan_id": "x", "success": False, "error": "e", "results": {}})
    result = await WorkflowRunner._handle_workflow_execution_failure(fake, _plan("sequential"), ValueError("e"), {}, 0)
    assert fake.record_calls == 1  # recorded once
    assert result["known_failure_pattern"]["occurrences"] == 2  # annotation rides final dict


@pytest.mark.asyncio
async def test_handle_does_not_record_or_annotate_on_recursion():
    fake = _FakeRunner({"plan_id": "x", "success": False, "error": "e", "results": {}})
    result = await WorkflowRunner._handle_workflow_execution_failure(
        fake, _plan("sequential"), ValueError("e"), {}, 1  # _depth > 0 → nested fallback
    )
    assert fake.record_calls == 0  # no double-count on fallback recursion
    assert "known_failure_pattern" not in result


@pytest.mark.asyncio
async def test_handle_does_not_annotate_successful_recovery():
    fake = _FakeRunner({"success": True, "results": {}})
    result = await WorkflowRunner._handle_workflow_execution_failure(fake, _plan("sequential"), ValueError("e"), {}, 0)
    assert "known_failure_pattern" not in result  # recovery succeeded → no failure annotation
