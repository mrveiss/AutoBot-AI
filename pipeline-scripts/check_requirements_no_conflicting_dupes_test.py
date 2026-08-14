# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the conflicting-duplicate requirements guard (#14228)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE = Path(__file__).with_name("check_requirements_no_conflicting_dupes.py")


@pytest.fixture
def guard():
    spec = importlib.util.spec_from_file_location("check_requirements_dupes", _MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree(tmp_path: Path, child: str, parent: str) -> Path:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "requirements.txt").write_text(child, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(parent, encoding="utf-8")
    return tmp_path


def test_a_differing_pin_across_an_include_is_reported(guard, tmp_path, monkeypatch):
    """The live failure: pip aborts provisioning on this."""
    _tree(tmp_path, "openpyxl>=3.1.0\n-r ../requirements.txt\n", "openpyxl>=3.1.5\n")
    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 0, "stdout": "sub/requirements.txt\nrequirements.txt\n", "stderr": ""})())

    assert guard.main([]) == 1


def test_an_identical_pin_is_not_reported(guard, tmp_path, monkeypatch):
    """pip tolerates these, and failing on them would turn a real bug into a
    tidiness campaign — `aiosqlite` sits in both real files this way, on a line
    before the openpyxl conflict, and did not error."""
    _tree(tmp_path, "aiosqlite>=0.22.1\n-r ../requirements.txt\n", "aiosqlite>=0.22.1\n")
    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 0, "stdout": "sub/requirements.txt\nrequirements.txt\n", "stderr": ""})())

    assert guard.main([]) == 0


def test_all_conflicts_are_reported_not_just_the_first(guard, tmp_path, monkeypatch):
    """pip stops at the first, so a one-at-a-time fix fails again next deploy.

    This is the property that matters: `openpyxl` and `python-pptx` both
    conflicted, and fixing only the reported one would have moved the failure
    rather than removed it.
    """
    _tree(
        tmp_path,
        "openpyxl>=3.1.0\npython-pptx>=0.6.23\n-r ../requirements.txt\n",
        "openpyxl>=3.1.5\npython-pptx>=1.0.2\n",
    )
    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 0, "stdout": "sub/requirements.txt\nrequirements.txt\n", "stderr": ""})())

    assert len(guard.conflicts(tmp_path)) == 2


def test_underscore_and_hyphen_are_the_same_distribution(guard, tmp_path, monkeypatch):
    """PyPI canonicalises `_` to `-`, so pip sees these as one package."""
    _tree(tmp_path, "python_pptx>=0.6.23\n-r ../requirements.txt\n", "python-pptx>=1.0.2\n")
    monkeypatch.setattr(guard, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 0, "stdout": "sub/requirements.txt\nrequirements.txt\n", "stderr": ""})())

    assert len(guard.conflicts(tmp_path)) == 1


def test_the_repository_currently_has_no_conflicts(guard):
    """End-to-end against the real tree — the assertion that fails if a
    conflicting pin is reintroduced anywhere."""
    assert guard.main([]) == 0


def test_an_empty_file_listing_is_fatal_not_clean(guard, monkeypatch):
    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 0, "stdout": "", "stderr": ""})())

    with pytest.raises(SystemExit) as excinfo:
        guard.conflicts(Path("."))

    assert "refusing to report clean" in str(excinfo.value)
