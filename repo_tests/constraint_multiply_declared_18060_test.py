# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A package declared in two or more requirements files has ONE home, ``constraints/shared.txt`` (#18060).

``scripts/check_constraint_drift.py`` used to fail only on a re-declared version of the ten names the
constraints file already pinned, so every other package carried its own spec per file and the specs
drifted apart. These tests plant the offence and require the guard to name it, so a guard that has
stopped looking cannot report clean.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()


@pytest.fixture(scope="module")
def guard():
    spec = importlib.util.spec_from_file_location("check_constraint_drift", _ROOT / "scripts/check_constraint_drift.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _violations(guard, tmp_path: Path, files: dict[str, str], shared: set[str]) -> list[str]:
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    return guard.find_violations(guard._declarations(paths), shared)


def test_a_package_pinned_in_two_files_outside_shared_is_named(guard, tmp_path):
    found = _violations(guard, tmp_path, {"a.txt": "planted-pkg>=1.0\n", "b.txt": "planted-pkg>=2.0\n"}, set())
    assert any("planted-pkg" in v and "absent from" in v for v in found), found


def test_a_pin_in_one_file_and_a_bare_name_in_another_is_named(guard, tmp_path):
    found = _violations(guard, tmp_path, {"a.txt": "planted-pkg[extra]==1.0\n", "b.txt": "planted-pkg\n"}, set())
    assert any("planted-pkg" in v for v in found), found


def test_a_pin_with_extras_for_a_constrained_package_is_named(guard, tmp_path):
    found = _violations(guard, tmp_path, {"a.txt": "planted-pkg[extra]>=1.0\n"}, {"planted-pkg"})
    assert any("re-pins a constrained package" in v for v in found), found


def test_bare_names_and_a_single_declaration_are_clean(guard, tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "EXEMPT", {})
    files = {"a.txt": "shared-pkg\nonly-here>=1.0\n", "b.txt": "shared-pkg\n"}
    assert _violations(guard, tmp_path, files, {"shared-pkg"}) == []


def test_a_stale_exemption_is_an_error(guard, tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "EXEMPT", {"gone-pkg": "reason"})
    found = _violations(guard, tmp_path, {"a.txt": "gone-pkg>=1.0\n"}, set())
    assert any("stale EXEMPT" in v for v in found), found


def test_the_guard_reads_the_real_manifests_and_the_tree_is_clean(guard):
    cwd = Path.cwd()
    os.chdir(_ROOT)
    try:
        files = {str(f) for f in guard.requirement_files()}
        assert "autobot-backend/requirements.txt" in files, "the guard no longer reaches the backend manifest"
        assert guard.main() == 0
    finally:
        os.chdir(cwd)


def _ci_site(guard, raw: str, specs: dict[str, str]) -> list[str]:
    decls = {"planted-pkg": [(Path("requirements-ci/x.txt"), 1, raw, True)]}
    found = guard.find_violations(decls, {"planted-pkg"}, specs)
    return [v for v in found if "stale EXEMPT" not in v]


def test_a_ci_exact_pin_that_meets_the_shared_constraint_is_allowed(guard):
    assert _ci_site(guard, "planted-pkg==2.3.0", {"planted-pkg": ">=2.0,<3.0"}) == []


def test_a_ci_exact_pin_below_the_shared_floor_is_named(guard):
    found = _ci_site(guard, "planted-pkg==1.9.0", {"planted-pkg": ">=2.0,<3.0"})
    assert any("re-pins a constrained package" in v for v in found), found


def test_a_ci_exact_pin_past_the_shared_cap_is_named(guard):
    assert _ci_site(guard, "planted-pkg==3.1.0", {"planted-pkg": ">=2.0,<3.0"})


def test_a_non_ci_file_may_not_repeat_a_constrained_pin_even_when_it_satisfies(guard):
    decls = {"planted-pkg": [(Path("autobot-backend/requirements.txt"), 1, "planted-pkg==2.3.0", True)]}
    found = guard.find_violations(decls, {"planted-pkg"}, {"planted-pkg": ">=2.0"})
    assert [v for v in found if "stale EXEMPT" not in v]
