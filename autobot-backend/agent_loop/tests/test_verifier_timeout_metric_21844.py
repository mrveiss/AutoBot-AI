# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A verifier timeout is counted per tool in metrics, not only written as an audit event (#21844)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from prometheus_client import CollectorRegistry

from autobot_shared.monitoring.metrics import quality_gates
from autobot_shared.monitoring.metrics.quality_gates import QualityGateMetricsRecorder
from autobot_shared.pre_action_verifier_guard import VerifierResult, VerifierVerdict
from autobot_shared.verifier_degradation import VerifierDegradation
from services.verifier_audit import audit_verifier_degraded


def _result(tool: str, degradation: VerifierDegradation) -> VerifierResult:
    return VerifierResult(VerifierVerdict.PASS, 0.0, "no reading", tool, degradation=degradation)


@pytest.fixture
def recorder(monkeypatch):
    fake = QualityGateMetricsRecorder(CollectorRegistry())
    monkeypatch.setattr(quality_gates, "quality_gate_metrics", lambda: fake)
    return fake


def _count(recorder, tool):
    return recorder.registry.get_sample_value("autobot_verifier_timeout_total", {"tool": tool})


@pytest.mark.asyncio
async def test_each_timeout_is_counted_under_its_tool(recorder):
    with patch("services.audit_logger.audit_log", AsyncMock(return_value=True)):
        await audit_verifier_degraded(_result("navigate", VerifierDegradation.TIMEOUT))
        await audit_verifier_degraded(_result("navigate", VerifierDegradation.TIMEOUT))
        await audit_verifier_degraded(_result("bash", VerifierDegradation.TIMEOUT))
    assert (_count(recorder, "navigate"), _count(recorder, "bash")) == (2.0, 1.0)


@pytest.mark.asyncio
async def test_a_degradation_that_is_not_a_timeout_is_not_counted_as_one(recorder):
    with patch("services.audit_logger.audit_log", AsyncMock(return_value=True)):
        await audit_verifier_degraded(_result("navigate", VerifierDegradation.CALL_FAILED))
    assert _count(recorder, "navigate") is None


@pytest.mark.asyncio
async def test_the_timeout_is_counted_even_when_the_audit_write_fails(recorder):
    with patch("services.audit_logger.audit_log", AsyncMock(side_effect=RuntimeError("down"))):
        await audit_verifier_degraded(_result("navigate", VerifierDegradation.TIMEOUT))
    assert _count(recorder, "navigate") == 1.0


def test_a_model_invented_tool_name_cannot_grow_the_series_without_bound(recorder):
    for index in range(500):
        recorder.record_verifier_timeout(f"invented_{index}")
    series = [s for m in recorder.registry.collect() for s in m.samples if s.name == "autobot_verifier_timeout_total"]
    assert len(series) < 500


def test_the_shared_recorder_is_created_once_per_registry():
    assert quality_gates.quality_gate_metrics() is quality_gates.quality_gate_metrics()
