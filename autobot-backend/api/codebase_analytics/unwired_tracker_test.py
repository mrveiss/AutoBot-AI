# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for the unwired-tracker analyzer and API surface (Issue #6871).

Verifies that:
  1. _detect_unwired_trackers() flags modules with tracker refs and 0 callers.
  2. Modules with callers are NOT flagged.
  3. Ambiguous stems (utils, config, ...) are silently skipped.
  4. The finding dict shape matches what ChromaDB persistence expects.
  5. The cross-file bridge routes unwired-tracker findings into ChromaDB so
     they surface at /api/codebase/problems?type=code_smell_unwired_tracker.
"""

import importlib.util
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------


def _load_detector():
    """Load AntiPatternDetector from the code_analysis sub-module."""
    spec = importlib.util.spec_from_file_location(
        "apd_under_test",
        "autobot-backend/code_analysis/src/anti_pattern_detector.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        pytest.skip(f"AntiPatternDetector dep chain unavailable: {exc}")
    return mod


def _load_cross_file_module():
    spec = importlib.util.spec_from_file_location(
        "xfa_under_test",
        "autobot-backend/api/codebase_analytics/cross_file_analysis.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        pytest.skip(f"cross_file_analysis dep chain unavailable: {exc}")
    return mod


def _write(root: Path, name: str, body: str) -> Path:
    p = root / f"{name}.py"
    p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Detector unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_unwired_tracker_flags_zero_caller_module(tmp_path):
    """A module whose header cites a tracker and has no callers must be flagged."""
    apd = _load_detector()

    _write(
        tmp_path,
        "orphan_feature",
        """
        # Issue #9999: initial implementation
        def do_something():
            return 42
        """,
    )

    detector = apd.AntiPatternDetector()
    findings = await detector._detect_unwired_trackers(str(tmp_path))

    assert len(findings) >= 1, f"expected at least one finding, got {findings}"
    types = {f.pattern_type.value for f in findings}
    assert "unwired_tracker" in types, f"expected unwired_tracker in {types}"

    # Check the finding refers to our module
    stems = {f.entity_name for f in findings}
    assert "orphan_feature" in stems, f"expected orphan_feature in {stems}"


@pytest.mark.asyncio
async def test_detect_unwired_tracker_ignores_imported_module(tmp_path):
    """A module that IS imported by another file must NOT be flagged."""
    apd = _load_detector()

    # Feature module with tracker ref
    _write(
        tmp_path,
        "wired_feature",
        """
        # Issue #1000: implemented feature
        def run():
            return True
        """,
    )
    # Caller that imports it
    _write(
        tmp_path,
        "main_runner",
        """
        from wired_feature import run

        run()
        """,
    )

    detector = apd.AntiPatternDetector()
    findings = await detector._detect_unwired_trackers(str(tmp_path))

    stems = {f.entity_name for f in findings}
    assert "wired_feature" not in stems, "wired_feature has a caller (main_runner) and must NOT be flagged"


@pytest.mark.asyncio
async def test_detect_unwired_tracker_skips_ambiguous_stems(tmp_path):
    """Modules with ambiguous stems like 'utils' or 'config' must be skipped."""
    apd = _load_detector()

    # An "ambiguous" module with tracker ref — should be silently skipped
    _write(
        tmp_path,
        "utils",
        """
        # Issue #5555: utility helpers
        def helper():
            pass
        """,
    )

    detector = apd.AntiPatternDetector()
    findings = await detector._detect_unwired_trackers(str(tmp_path))

    stems = {f.entity_name for f in findings}
    assert "utils" not in stems, "utils is an ambiguous stem and must be skipped"


@pytest.mark.asyncio
async def test_detect_unwired_tracker_no_ref_no_finding(tmp_path):
    """A module with zero tracker refs must never be flagged, even without callers."""
    apd = _load_detector()

    _write(
        tmp_path,
        "plain_module",
        """
        def compute(x):
            return x * 2
        """,
    )

    detector = apd.AntiPatternDetector()
    findings = await detector._detect_unwired_trackers(str(tmp_path))

    stems = {f.entity_name for f in findings}
    assert "plain_module" not in stems, "plain_module has no tracker ref and must be skipped"


# ---------------------------------------------------------------------------
# Finding dict shape test (via cross-file bridge)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unwired_tracker_problem_dict_shape(tmp_path):
    """The problem dict produced by the cross-file bridge must include all
    required ChromaDB persistence keys, with the expected type prefix."""
    xfa = _load_cross_file_module()

    _write(
        tmp_path,
        "dangling_impl",
        """
        # Tracking issue #7777
        def placeholder():
            pass
        """,
    )

    persisted: list = []

    async def fake_persist(problems, source_id=None):
        persisted.extend(problems)
        return len(problems)

    with patch.object(xfa, "_persist_to_chromadb", new=fake_persist):
        count = await xfa.run_cross_file_analysis(str(tmp_path), source_id=None, exclude_patterns=["__pycache__"])

    # There must be at least 1 finding for our fixture
    assert count >= 1, f"expected at least 1 finding persisted, got {count}"

    # Verify the dict shape ChromaDB persistence reads
    unwired = [p for p in persisted if "unwired" in p.get("type", "")]
    assert unwired, f"expected at least one unwired_tracker finding in {persisted}"

    p = unwired[0]
    for key in ("type", "severity", "file_path", "line", "description", "suggestion"):
        assert key in p, f"problem dict missing required key {key!r}: {p}"

    assert p["type"] == "code_smell_unwired_tracker", f"expected code_smell_unwired_tracker, got {p['type']!r}"
    assert p["severity"] in ("low", "medium", "high", "critical"), f"unexpected severity: {p['severity']}"


# ---------------------------------------------------------------------------
# Integration: cross-file bridge includes unwired-tracker findings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_file_bridge_includes_unwired_tracker(tmp_path):
    """run_cross_file_analysis() must surface unwired-tracker findings so
    they appear in /api/codebase/problems?type=code_smell_unwired_tracker."""
    xfa = _load_cross_file_module()

    # A module with a tracker ref and no callers
    _write(
        tmp_path,
        "incomplete_feature",
        """
        # Issue #8888: feature never wired in
        class FeatureStub:
            pass
        """,
    )

    persisted: list = []

    async def fake_persist(problems, source_id=None):
        persisted.extend(problems)
        return len(problems)

    with patch.object(xfa, "_persist_to_chromadb", new=fake_persist):
        await xfa.run_cross_file_analysis(str(tmp_path), source_id="test-source", exclude_patterns=["__pycache__"])

    types = {p.get("type") for p in persisted}
    assert "code_smell_unwired_tracker" in types, f"expected code_smell_unwired_tracker in persisted types; got {types}"
