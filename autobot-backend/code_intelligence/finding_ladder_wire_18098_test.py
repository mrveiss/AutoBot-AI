# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Four severity forks became aliases without changing a byte on the wire (#18098).

`PerformanceSeverity`, `OptimizationSeverity`, `SecuritySeverity` and
`TestPatternSeverity` were each a five-member enum (INFO..CRITICAL) that response
builders ITERATED to key a `severity_breakdown` / `severity_counts` dict. Aliased
to the ten-rung canonical, a plain iteration would add five always-zero keys, so
those sites iterate `Severity.finding_ladder()`.

The expected values below are LITERALS captured from the old enums (member order
INFO, LOW, MEDIUM, HIGH, CRITICAL) -- never derived from the code under test.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from autobot_shared.status_enums import Severity

OLD_ORDER = ["info", "low", "medium", "high", "critical"]
OLD_COUNTS = {"info": 0, "low": 1, "medium": 0, "high": 2, "critical": 0}


def _finding(severity):
    return SimpleNamespace(
        severity=severity,
        file_path="a.py",
        type="pipeline",
        vulnerability_type=SimpleNamespace(value="injection"),
        issue_type=SimpleNamespace(value="loop"),
        to_dict=lambda: {},
    )


def _findings():
    return [_finding(Severity.HIGH), _finding(Severity.LOW), _finding(Severity.HIGH)]


def test_finding_ladder_is_the_old_five_rungs_in_order():
    assert [s.value for s in Severity.finding_ladder()] == OLD_ORDER


@pytest.mark.parametrize(
    "module, name",
    [
        ("code_intelligence.performance_analysis.types", "PerformanceSeverity"),
        ("code_intelligence.redis_optimizer", "OptimizationSeverity"),
        ("code_intelligence.security.constants", "SecuritySeverity"),
        ("code_intelligence.testing_pattern_analyzer", "TestPatternSeverity"),
    ],
)
def test_the_fork_is_the_canonical(module, name):
    import importlib

    assert getattr(importlib.import_module(module), name) is Severity


@pytest.fixture
def target(tmp_path):
    path = tmp_path / "x.py"
    path.write_text("x = 1\n", encoding="utf-8")
    return path


def _body(response):
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_redis_file_scan_breakdown_is_byte_identical(target):
    import api.code_intelligence as mod

    fake = SimpleNamespace(analyze_file=lambda _p: _findings())
    with patch.object(mod, "RedisOptimizer", lambda: fake):
        response = await mod.scan_redis_file(SimpleNamespace(file_path=str(target)), admin_check=True)
    breakdown = _body(response)["severity_breakdown"]
    assert breakdown == OLD_COUNTS
    assert list(breakdown) == OLD_ORDER


@pytest.mark.asyncio
async def test_redis_health_analysis_breakdown_is_byte_identical():
    import api.code_intelligence as mod

    class _Optimizer:
        def __init__(self, project_root=None):
            self.results = []

        def get_summary(self):
            return {"by_type": {}}

    with patch.object(mod, "RedisOptimizer", _Optimizer):
        with patch.object(mod, "run_isolated", return_value=_findings()):
            result = await mod._run_redis_health_analysis("/tmp/example")
    assert result["severity_breakdown"] == OLD_COUNTS
    assert list(result["severity_breakdown"]) == OLD_ORDER


@pytest.mark.asyncio
async def test_security_file_scan_counts_are_byte_identical(target):
    import api.code_intelligence as mod

    fake = SimpleNamespace(analyze_file=lambda _p: _findings())
    with patch.object(mod, "SecurityAnalyzer", lambda: fake):
        response = await mod.security_scan_file(SimpleNamespace(file_path=str(target)), admin_check=True)
    counts = _body(response)["severity_counts"]
    assert counts == OLD_COUNTS
    assert list(counts) == OLD_ORDER


@pytest.mark.asyncio
async def test_performance_file_scan_counts_are_byte_identical(target):
    import api.code_intelligence as mod

    fake = SimpleNamespace(analyze_file=lambda _p: _findings())
    with patch.object(mod, "PerformanceAnalyzer", lambda: fake):
        response = await mod.performance_scan_file(SimpleNamespace(file_path=str(target)), admin_check=True)
    counts = _body(response)["severity_counts"]
    assert counts == OLD_COUNTS
    assert list(counts) == OLD_ORDER


def test_test_pattern_distribution_and_levels_are_byte_identical(tmp_path):
    from code_intelligence import testing_pattern_analyzer as tpa

    target = tmp_path / "test_x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    report = SimpleNamespace(
        test_count=1,
        assertion_count=1,
        anti_patterns=_findings(),
        coverage_gaps=[],
        metrics={},
        suggestions=[],
    )
    with patch.object(tpa.TestPatternAnalyzer, "analyze_test_file", return_value=report):
        result = tpa.analyze_tests(str(target))
    assert result.severity_distribution == OLD_COUNTS
    assert list(result.severity_distribution) == OLD_ORDER
    assert tpa.get_test_severity_levels() == OLD_ORDER


def test_optimization_priority_is_the_canonical_and_keeps_its_wire_order():
    """Old enum declared CRITICAL first; the emitted list must stay critical-first."""
    from code_intelligence.llm_pattern_analysis.types import OptimizationPriority
    from code_intelligence.llm_pattern_analyzer import get_optimization_priorities

    assert OptimizationPriority is Severity
    assert get_optimization_priorities() == ["critical", "high", "medium", "low", "info"]


def test_optimization_priority_sort_order_is_unchanged():
    from code_intelligence.llm_pattern_analysis.recommendation_engine import RecommendationEngine

    recs = [SimpleNamespace(priority=p) for p in (Severity.INFO, Severity.CRITICAL, Severity.LOW, Severity.HIGH)]
    ordered = RecommendationEngine._sort_by_priority(recs)
    assert [r.priority.value for r in ordered] == ["critical", "high", "low", "info"]
