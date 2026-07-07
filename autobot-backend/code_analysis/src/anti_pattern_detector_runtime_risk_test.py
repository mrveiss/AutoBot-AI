# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for runtime failure-risk → anti-pattern ranking join (#11183).

Tests cover:
1. Resolver aggregation math: raw_risk = occurrence * (1-resolution_rate),
   bounded-exp normalization, blame-frame attribution (locations[-1]).
2. Empty source → {} no error.
3. Ranking boost: a finding whose file has runtime_risk > 0 sorts at or above
   the same finding with risk 0 (monotonic-up guarantee).
4. Critical join test: absolute prod path joins against repo-relative file_path.
5. Back-compat: to_dict() has all prior keys plus runtime_risk.
"""

from __future__ import annotations

import importlib.util
import math
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module loader helpers
# ---------------------------------------------------------------------------


def _load_apd():
    """Load anti_pattern_detector module from worktree-relative path."""
    spec = importlib.util.spec_from_file_location(
        "apd_rr_test",
        "autobot-backend/code_analysis/src/anti_pattern_detector.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        pytest.skip(f"AntiPatternDetector dep chain unavailable: {exc}")
    if not hasattr(mod, "config"):
        mod.config = None
    return mod


def _load_rr():
    """Load runtime_risk module from worktree-relative path."""
    spec = importlib.util.spec_from_file_location(
        "rr_test",
        "autobot-backend/code_analysis/src/runtime_risk.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        pytest.skip(f"runtime_risk dep chain unavailable: {exc}")
    return mod


# ---------------------------------------------------------------------------
# Stub FailurePattern
# ---------------------------------------------------------------------------


def _make_pattern(occurrence_count: int, resolution_success_rate: float, blame_file: str):
    """Build a minimal FailurePattern-shaped stub."""
    return SimpleNamespace(
        occurrence_count=occurrence_count,
        resolution_success_rate=resolution_success_rate,
        failure_locations=[{"file": blame_file, "line": 1, "func": "f"}],
    )


# ---------------------------------------------------------------------------
# Test 1: aggregation math
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_aggregation_math():
    """raw_risk per file == sum(occ * (1-rate)); bounded-exp applied."""
    rr = _load_rr()

    # File "autobot-backend/x.py": two patterns each contributing to it.
    # Pattern A: occ=10, rate=0.5 → weight=5.0
    # Pattern B: occ=4,  rate=0.0 → weight=4.0
    # raw_risk = 9.0; K default=5.0; expected = 1 - exp(-9/5)
    patterns = [
        _make_pattern(10, 0.5, "autobot-backend/x.py"),
        _make_pattern(4, 0.0, "autobot-backend/x.py"),
    ]

    with patch.object(rr, "_blame_file", side_effect=lambda p: p.failure_locations[-1]["file"]):
        result = rr._aggregate_risk(patterns)

    assert "autobot-backend/x.py" in result
    expected = 1.0 - math.exp(-9.0 / rr._RISK_K)
    assert abs(result["autobot-backend/x.py"] - expected) < 1e-9
    # Bounded: [0, 1)
    assert 0.0 <= result["autobot-backend/x.py"] < 1.0


# ---------------------------------------------------------------------------
# Test 2: blame-frame is locations[-1]
# ---------------------------------------------------------------------------


def test_blame_frame_is_last_location():
    """_blame_file should attribute to the innermost (last) location."""
    rr = _load_rr()

    pattern = SimpleNamespace(
        failure_locations=[
            {"file": "autobot-backend/outer.py", "line": 1, "func": "outer"},
            {"file": "autobot-backend/inner.py", "line": 5, "func": "inner"},
        ]
    )
    blame = rr._blame_file(pattern)
    # inner.py is the last frame → blame
    assert blame is not None
    assert "inner.py" in blame
    assert "outer.py" not in blame


# ---------------------------------------------------------------------------
# Test 3: empty source → {} no error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_patterns_returns_empty_dict():
    """When list_known_patterns returns [], build_runtime_risk_map returns {}."""
    rr = _load_rr()

    mock_detector = AsyncMock()
    mock_detector.list_known_patterns = AsyncMock(return_value=[])

    with patch("services.failure_pattern_detector.get_pattern_detector", return_value=mock_detector):
        result = await rr.build_runtime_risk_map()

    assert result == {}


# ---------------------------------------------------------------------------
# Test 4: ranking boost is monotonic-up
# ---------------------------------------------------------------------------


def test_ranking_boost_monotonic_up():
    """A finding with runtime_risk>0 must sort at or above the same finding with risk=0."""
    apd = _load_apd()

    detector = apd.AntiPatternDetector()

    high_sev = apd.Severity.HIGH
    pattern_type = apd.AntiPatternType.LONG_METHOD

    # Two identical findings except file_path; risk_map will give risk only to "risky.py"
    ap_risky = apd.AntiPatternInstance(
        pattern_type=pattern_type,
        severity=high_sev,
        file_path="autobot-backend/risky.py",
        line_number=10,
        entity_name="SomeClass.long_method",
        description="too long",
        metrics={},
        suggestion="refactor",
        refactoring_effort="medium",
    )
    ap_safe = apd.AntiPatternInstance(
        pattern_type=pattern_type,
        severity=high_sev,
        file_path="autobot-backend/safe.py",
        line_number=10,
        entity_name="OtherClass.long_method",
        description="too long",
        metrics={},
        suggestion="refactor",
        refactoring_effort="medium",
    )

    risk_map = {"autobot-backend/risky.py": 0.8}
    report = detector._generate_report([ap_risky, ap_safe], 0.0, risk_map)

    sorted_paths = [ap.file_path for ap in report.anti_patterns]
    # risky.py must appear before or at the same position as safe.py
    assert sorted_paths.index("autobot-backend/risky.py") <= sorted_paths.index("autobot-backend/safe.py")
    # Also verify risk was stamped onto the instance
    risky_inst = next(ap for ap in report.anti_patterns if ap.file_path == "autobot-backend/risky.py")
    assert risky_inst.runtime_risk == pytest.approx(0.8)
    safe_inst = next(ap for ap in report.anti_patterns if ap.file_path == "autobot-backend/safe.py")
    assert safe_inst.runtime_risk == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test 5: CRITICAL JOIN TEST
# Absolute prod path + repo-relative file_path → same key after to_repo_relative
# ---------------------------------------------------------------------------


def test_critical_join_absolute_prod_path_to_repo_relative():
    """Absolute prod path in failure_locations joins against repo-relative file_path.

    Scenario:
      - FailurePattern.failure_locations[-1]["file"] =
            "/opt/autobot/code_source/autobot-backend/x.py"
      - AntiPatternInstance.file_path = "autobot-backend/x.py"

    After to_repo_relative() both normalize to "autobot-backend/x.py",
    so the risk score is applied to the anti-pattern instance.
    """
    rr = _load_rr()
    apd = _load_apd()

    prod_path = "/opt/autobot/code_source/autobot-backend/x.py"
    repo_rel_path = "autobot-backend/x.py"

    # Verify the normalizer equates both paths
    from autobot_shared.repo_path import to_repo_relative

    assert to_repo_relative(prod_path) == repo_rel_path
    assert to_repo_relative(repo_rel_path) == repo_rel_path

    # Build a pattern that attributes to the prod path
    pattern = _make_pattern(10, 0.0, prod_path)
    blame = rr._blame_file(pattern)
    assert blame == repo_rel_path, f"Expected '{repo_rel_path}', got '{blame}'"

    risk_result = rr._aggregate_risk([pattern])
    assert repo_rel_path in risk_result, f"risk key '{repo_rel_path}' not in {list(risk_result.keys())}"

    # Now verify it lands on the anti-pattern instance
    detector = apd.AntiPatternDetector()
    ap = apd.AntiPatternInstance(
        pattern_type=apd.AntiPatternType.GOD_CLASS,
        severity=apd.Severity.HIGH,
        file_path=repo_rel_path,
        line_number=1,
        entity_name="BigClass",
        description="too big",
        metrics={},
        suggestion="refactor",
        refactoring_effort="high",
    )

    report = detector._generate_report([ap], 0.0, risk_result)
    assert len(report.anti_patterns) == 1
    assert report.anti_patterns[0].runtime_risk > 0.0


# ---------------------------------------------------------------------------
# Test 6: back-compat — to_dict() has all prior keys plus runtime_risk
# ---------------------------------------------------------------------------


def test_to_dict_back_compat():
    """to_dict() must include all pre-existing keys AND the new runtime_risk."""
    apd = _load_apd()

    ap = apd.AntiPatternInstance(
        pattern_type=apd.AntiPatternType.DEAD_CODE,
        severity=apd.Severity.LOW,
        file_path="autobot-backend/utils.py",
        line_number=42,
        entity_name="OldHelper",
        description="unused",
        metrics={"lines_of_code": 5},
        suggestion="remove",
        refactoring_effort="low",
        related_entities=["OtherClass"],
    )
    d = ap.to_dict()

    # Pre-existing keys
    for key in (
        "pattern_type",
        "severity",
        "severity_score",
        "file_path",
        "line_number",
        "entity_name",
        "description",
        "metrics",
        "suggestion",
        "refactoring_effort",
        "related_entities",
    ):
        assert key in d, f"Missing pre-existing key: {key}"

    # New key
    assert "runtime_risk" in d
    assert d["runtime_risk"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test 7: pattern with no failure_locations is skipped (no AttributeError)
# ---------------------------------------------------------------------------


def test_pattern_with_empty_locations_skipped():
    """Patterns with failure_locations=[] produce no risk entry."""
    rr = _load_rr()

    pattern = SimpleNamespace(
        occurrence_count=5,
        resolution_success_rate=0.0,
        failure_locations=[],
    )
    result = rr._aggregate_risk([pattern])
    assert result == {}


# ---------------------------------------------------------------------------
# Test 8: write_module fixture for full round-trip with file on disk
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_report_with_risk_map(tmp_path):
    """End-to-end: scan a minimal codebase; risk map is applied if supplied."""
    apd = _load_apd()

    source = tmp_path / "big.py"
    source.write_text(
        textwrap.dedent("""\
            class BigClass:
                def m1(self): pass
            """),
        encoding="utf-8",
    )

    detector = apd.AntiPatternDetector()
    await detector._parse_codebase(str(tmp_path), ["**/*.py"], [])

    # Manufacture one instance pointing to our source file
    ap = apd.AntiPatternInstance(
        pattern_type=apd.AntiPatternType.GOD_CLASS,
        severity=apd.Severity.MEDIUM,
        file_path=str(source),
        line_number=1,
        entity_name="BigClass",
        description="test",
        metrics={},
        suggestion="refactor",
        refactoring_effort="low",
    )

    # Supply risk for the source file's repo-relative path
    from autobot_shared.repo_path import to_repo_relative

    rel = to_repo_relative(str(source)) or str(source)
    risk_map = {rel: 0.5}

    report = detector._generate_report([ap], 0.0, risk_map)
    inst = report.anti_patterns[0]
    assert inst.runtime_risk == pytest.approx(0.5)
    d = inst.to_dict()
    assert d["runtime_risk"] == pytest.approx(0.5)
