# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for venv_provenance.py — install-provenance for the venv reconciler (#15067).

A plain top-level module (see its own docstring for why), so it imports
directly here with no dance around ``api/__init__.py`` — unlike
``tests/test_venv_reconcile.py``, which loads ``api/venv_reconcile.py`` by
file path for exactly that reason.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import venv_provenance as provenance


def _normalize(name: str) -> str:
    return name.replace("_", "-").replace(".", "-").lower()


# ---------------------------------------------------------------------------
# allow_unverified_removal — opt-in, read live, defaults closed
# ---------------------------------------------------------------------------


def test_allow_unverified_removal_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(provenance.ALLOW_UNVERIFIED_REMOVAL_ENV, raising=False)
    assert provenance.allow_unverified_removal() is False


@pytest.mark.parametrize("value", ["1", "true", "True", "yes", "YES"])
def test_allow_unverified_removal_true_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(provenance.ALLOW_UNVERIFIED_REMOVAL_ENV, value)
    assert provenance.allow_unverified_removal() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "", "garbage"])
def test_allow_unverified_removal_false_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(provenance.ALLOW_UNVERIFIED_REMOVAL_ENV, value)
    assert provenance.allow_unverified_removal() is False


# ---------------------------------------------------------------------------
# dist_info_paths — from installed_state's raw shape, name-normalized
# ---------------------------------------------------------------------------


def test_dist_info_paths_normalizes_names_and_maps_missing_to_none(tmp_path: Path) -> None:
    raw_state = {
        "Pkg_Root": {"requires": [], "dist_info": str(tmp_path / "pkg_root-1.0.dist-info")},
        "pkg-no-path": {"requires": [], "dist_info": None},
        "pkg-malformed": "not-a-dict",
    }
    paths = provenance.dist_info_paths(raw_state, _normalize)
    assert paths["pkg-root"] == tmp_path / "pkg_root-1.0.dist-info"
    assert paths["pkg-no-path"] is None
    assert paths["pkg-malformed"] is None


# ---------------------------------------------------------------------------
# has_tool_provenance / write_provenance_marker — the dist-info-adjacent signal
# ---------------------------------------------------------------------------


def test_has_tool_provenance_false_when_dist_info_is_none() -> None:
    assert provenance.has_tool_provenance(None) is False


def test_has_tool_provenance_false_when_marker_absent(tmp_path: Path) -> None:
    dist_info = tmp_path / "pkg-1.0.dist-info"
    dist_info.mkdir()
    assert provenance.has_tool_provenance(dist_info) is False


def test_write_provenance_marker_then_has_tool_provenance_true(tmp_path: Path) -> None:
    dist_info = tmp_path / "pkg-1.0.dist-info"
    dist_info.mkdir()
    provenance.write_provenance_marker(dist_info, "test-comp")
    assert provenance.has_tool_provenance(dist_info) is True
    payload = json.loads((dist_info / provenance.PROVENANCE_MARKER_FILENAME).read_text(encoding="utf-8"))
    assert payload["tool"] == "autobot-venv-reconcile"
    assert payload["component"] == "test-comp"
    assert "recorded_at" in payload


def test_write_provenance_marker_swallows_oserror_instead_of_raising(tmp_path: Path) -> None:
    """A marker write failure must fail the NEXT candidacy check closed
    (unverified), never abort the surrounding install — see module docstring."""
    missing_dist_info = tmp_path / "does-not-exist" / "pkg-1.0.dist-info"
    provenance.write_provenance_marker(missing_dist_info, "test-comp")  # no exception
    assert provenance.has_tool_provenance(missing_dist_info) is False


# ---------------------------------------------------------------------------
# mark_current_set — stamps only names with a real, existing dist-info
# ---------------------------------------------------------------------------


def test_mark_current_set_stamps_present_packages_and_reports_a_count(tmp_path: Path) -> None:
    dist_info_a = tmp_path / "pkg-a-1.0.dist-info"
    dist_info_a.mkdir()
    paths = {"pkg-a": dist_info_a, "pkg-missing": tmp_path / "nowhere.dist-info"}

    steps: list = []
    provenance.mark_current_set("test-comp", {"pkg-a", "pkg-missing"}, paths, steps)

    assert provenance.has_tool_provenance(dist_info_a) is True
    assert any("stamped install-provenance for 1 package" in s for s in steps)


def test_mark_current_set_appends_no_step_when_nothing_to_stamp(tmp_path: Path) -> None:
    steps: list = []
    provenance.mark_current_set("test-comp", {"pkg-ghost"}, {"pkg-ghost": None}, steps)
    assert steps == []


# ---------------------------------------------------------------------------
# split_by_provenance — the removal-candidate gate itself
# ---------------------------------------------------------------------------


def test_split_by_provenance_separates_marked_from_unmarked(tmp_path: Path) -> None:
    verified_dist_info = tmp_path / "pkg-verified-1.0.dist-info"
    verified_dist_info.mkdir()
    provenance.write_provenance_marker(verified_dist_info, "test-comp")
    unverified_dist_info = tmp_path / "pkg-unverified-1.0.dist-info"
    unverified_dist_info.mkdir()  # no marker — e.g. an operator's own install

    paths = {"pkg-verified": verified_dist_info, "pkg-unverified": unverified_dist_info, "pkg-no-path": None}
    verified, unverified = provenance.split_by_provenance({"pkg-verified", "pkg-unverified", "pkg-no-path"}, paths)

    assert verified == {"pkg-verified"}
    assert unverified == {"pkg-unverified", "pkg-no-path"}
