# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for FailurePattern.failure_locations field and frame extraction (#11182).

Covers:
- FailurePattern round-trip serialisation (to_dict / from_dict).
- Backward compatibility: from_dict on old records without failure_locations.
- _extract_failure_locations: keeps in-repo frames, drops out-of-repo frames,
  caps at _MAX_FAILURE_FRAMES, is defensive when __traceback__ is None.
"""

from __future__ import annotations

import traceback
from typing import Any, Dict
from unittest.mock import patch

from orchestration.workflow_runner import _MAX_FAILURE_FRAMES, _extract_failure_locations
from services.failure_pattern_detector import FailurePattern


# ---------------------------------------------------------------------------
# FailurePattern serialisation round-trip
# ---------------------------------------------------------------------------


def _sample_pattern(**overrides) -> FailurePattern:
    base: Dict[str, Any] = {
        "pattern_id": "abc123",
        "causal_chain": "workflow:sequential:ValueError",
        "error_types": ["ValueError"],
        "occurrence_count": 2,
        "successful_resolutions": [],
        "resolution_success_rate": 0.0,
        "confidence": 0.8,
        "first_seen": "2026-01-01T00:00:00",
        "last_seen": "2026-01-02T00:00:00",
        "failure_locations": [
            {"file": "autobot-backend/services/x.py", "line": 42, "func": "run"}
        ],
    }
    base.update(overrides)
    return FailurePattern(**base)


def test_round_trip_preserves_failure_locations() -> None:
    """from_dict(to_dict(p)) reproduces failure_locations exactly."""
    p = _sample_pattern()
    restored = FailurePattern.from_dict(p.to_dict())
    assert restored.failure_locations == p.failure_locations


def test_round_trip_empty_failure_locations() -> None:
    """Empty failure_locations round-trips correctly."""
    p = _sample_pattern(failure_locations=[])
    restored = FailurePattern.from_dict(p.to_dict())
    assert restored.failure_locations == []


def test_from_dict_backward_compat_missing_field() -> None:
    """Old records without failure_locations deserialise to an empty list."""
    old_dict = {
        "pattern_id": "old1",
        "causal_chain": "workflow:parallel:RuntimeError",
        "error_types": ["RuntimeError"],
        "occurrence_count": 5,
        "successful_resolutions": ["retry"],
        "resolution_success_rate": 0.2,
        "confidence": 0.75,
        "first_seen": "2025-12-01T00:00:00",
        "last_seen": "2025-12-15T00:00:00",
        # failure_locations intentionally absent
    }
    p = FailurePattern.from_dict(old_dict)
    assert p.failure_locations == []


def test_to_dict_includes_failure_locations_key() -> None:
    """to_dict() always emits the failure_locations key."""
    p = _sample_pattern()
    d = p.to_dict()
    assert "failure_locations" in d
    assert d["failure_locations"] == p.failure_locations


# ---------------------------------------------------------------------------
# _extract_failure_locations helper
# ---------------------------------------------------------------------------


def _in_repo_raiser() -> None:
    """Helper that actually raises so we have a real traceback with frames."""
    raise ValueError("test failure")


def test_extract_returns_in_repo_frames() -> None:
    """In-repo frames (repo-relative) appear in the extracted locations.

    We patch to_repo_relative so that frames from *this test file* are treated
    as in-repo (returns a fake repo-relative path) while everything else is
    out-of-repo (returns None).
    """
    try:
        _in_repo_raiser()
    except ValueError as exc:
        raw_frames = traceback.extract_tb(exc.__traceback__)
        # Identify which filenames appear in our traceback
        test_file = raw_frames[-1].filename  # innermost frame = _in_repo_raiser

        def _fake_to_repo_relative(path: str) -> str | None:
            if path == test_file:
                return f"autobot-backend/tests/fake/{path.split('/')[-1]}"
            return None

        with patch(
            "orchestration.workflow_runner.to_repo_relative",
            side_effect=_fake_to_repo_relative,
        ):
            locations = _extract_failure_locations(exc)

    assert len(locations) >= 1
    innermost = locations[-1]
    assert "file" in innermost
    assert "line" in innermost
    assert "func" in innermost
    assert innermost["func"] == "_in_repo_raiser"


def test_extract_drops_out_of_repo_frames() -> None:
    """Frames where to_repo_relative returns None are excluded."""
    try:
        _in_repo_raiser()
    except ValueError as exc:
        with patch(
            "orchestration.workflow_runner.to_repo_relative",
            return_value=None,  # all frames look out-of-repo
        ):
            locations = _extract_failure_locations(exc)

    assert locations == []


def test_extract_caps_at_max_frames() -> None:
    """At most _MAX_FAILURE_FRAMES frames are returned."""

    def _make_deep_error(depth: int) -> Exception:
        if depth <= 0:
            raise RuntimeError("deep")
        _make_deep_error(depth - 1)

    try:
        _make_deep_error(_MAX_FAILURE_FRAMES + 5)
    except RuntimeError as exc:
        with patch(
            "orchestration.workflow_runner.to_repo_relative",
            return_value="autobot-backend/fake.py",
        ):
            locations = _extract_failure_locations(exc)

    assert len(locations) <= _MAX_FAILURE_FRAMES


def test_extract_none_traceback_returns_empty_list() -> None:
    """Exception with no traceback (e.g. raised outside a try) returns []."""
    exc = ValueError("no tb")
    assert exc.__traceback__ is None
    locations = _extract_failure_locations(exc)
    assert locations == []


def test_extract_is_defensive_on_extractor_error() -> None:
    """If frame extraction itself raises, an empty list is returned, not an exception."""
    try:
        _in_repo_raiser()
    except ValueError as exc:
        with patch(
            "orchestration.workflow_runner.to_repo_relative",
            side_effect=RuntimeError("broken"),
        ):
            locations = _extract_failure_locations(exc)

    assert locations == []
