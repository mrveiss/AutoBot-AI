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


def _ci_site(guard, path: str, raw: str) -> list[str]:
    decls = {"planted-pkg": [(Path(path), 1, raw, bool(guard._SPEC.match(raw)))]}
    found = guard.find_violations(decls, {"planted-pkg"})
    return [v for v in found if "stale EXEMPT" not in v]


_PLANES = ["requirements-ci/x.txt", "requirements-ci-test.txt", "autobot-backend/requirements.txt"]


@pytest.mark.parametrize("path", _PLANES)
@pytest.mark.parametrize("raw", ["planted-pkg==2.3.0", "planted-pkg>=2.0", "planted-pkg[extra]==2.3.0"])
def test_a_ci_plane_pin_that_meets_the_shared_constraint_is_still_named(guard, path, raw):
    """#21471: the CI plane once passed with a pin that satisfied the shared range, so a dependabot bump of
    constraints/shared.txt (the only file it edits) left the pin behind. Every plane now lists it bare."""
    found = _ci_site(guard, path, raw)
    assert any("re-pins a constrained package" in v for v in found), found


@pytest.mark.parametrize("path", ["requirements-ci/x.txt", "requirements-ci-test.txt"])
def test_a_bare_constrained_name_in_the_ci_plane_is_clean(guard, path):
    assert _ci_site(guard, path, "planted-pkg  # version from constraints/shared.txt") == []


@pytest.mark.parametrize(
    "line",
    [
        "planted-pkg (>=1.0)",
        "planted-pkg @ https://example.invalid/planted-pkg-1.0.tar.gz",
        "planted-pkg>=1.0; python_version<'3.12'",
    ],
    ids=["parenthesised", "direct-url", "versioned-with-marker"],
)
def test_a_versioned_requirement_in_any_spelling_counts_as_a_declaration_with_a_version(guard, tmp_path, line):
    found = _violations(guard, tmp_path, {"a.txt": line + "\n", "b.txt": "planted-pkg (>=2.0)\n"}, set())
    assert any("planted-pkg" in v and "absent from" in v for v in found), found


def test_a_bare_requirement_with_a_marker_stays_clean(guard, tmp_path, monkeypatch):
    monkeypatch.setattr(guard, "EXEMPT", {})
    files = {"a.txt": "shared-pkg; python_version<'3.12'\n", "b.txt": "shared-pkg\n"}
    assert _violations(guard, tmp_path, files, {"shared-pkg"}) == []


def test_a_marked_pin_of_a_constrained_package_is_reported(guard, tmp_path):
    found = _violations(guard, tmp_path, {"a.txt": "planted-pkg>=1.0; python_version<'3.12'\n"}, {"planted-pkg"})
    assert any("re-pins a constrained package" in v for v in found), found


def test_two_parenthesised_specs_of_one_package_are_drift_not_silence(guard, tmp_path):
    found = _violations(guard, tmp_path, {"a.txt": "planted-pkg (>=1)\n", "b.txt": "planted-pkg (>=2)\n"}, set())
    assert found, "parenthesised specifiers were treated as bare"


def _manifest(guard, tmp_path: Path, name: str, body: str, specs: dict[str, str]) -> list[str]:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return guard.manifest_violations([path], specs)


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("pyproject.toml", 'dependencies = [\n    "planted-pkg>=1.0",\n]\n'),
        ("pyproject.toml", 'dev = ["planted-pkg[extra]>=1.0", "other>=1"]\n'),
        ("setup.py", '    install_requires=["planted-pkg>=1.0"],\n'),
    ],
    ids=["pyproject-dependencies", "pyproject-extras-inline", "setup-py"],
)
def test_a_manifest_restating_a_constrained_package_below_the_shared_floor_is_named(guard, tmp_path, name, body):
    found = _manifest(guard, tmp_path, name, body, {"planted-pkg": ">=2.0"})
    assert any("planted-pkg" in v and "restates a constrained package" in v for v in found), found


def test_a_manifest_floor_that_meets_the_shared_specifier_or_names_it_bare_is_clean(guard, tmp_path):
    body = 'dependencies = ["planted-pkg>=2.1", "other>=1"]\nextras = ["planted-pkg"]\n'
    assert _manifest(guard, tmp_path, "pyproject.toml", body, {"planted-pkg": ">=2.0"}) == []


def test_the_guard_reads_the_real_packaging_manifests(guard):
    cwd = Path.cwd()
    os.chdir(_ROOT)
    try:
        files = {str(f) for f in guard.manifest_files()}
    finally:
        os.chdir(cwd)
    assert "libs/autobot-sdk-python/pyproject.toml" in files
    assert "autobot-backend/code_analysis/setup.py" in files


def test_a_manifest_prerelease_floor_below_the_shared_floor_is_named(guard, tmp_path):
    """PEP 440: ``2.0rc1`` sits below ``>=2.0``, so a standalone manifest floored there is drift."""
    body = 'dev = ["planted-pkg>=2.0rc1"]\n'
    assert _manifest(guard, tmp_path, "pyproject.toml", body, {"planted-pkg": ">=2.0"})
    assert _manifest(guard, tmp_path, "pyproject.toml", 'dev = ["planted-pkg>=2.0"]\n', {"planted-pkg": ">=2.0"}) == []


def _unbound(guard, tmp_path: Path, body: str) -> list[str]:
    path = tmp_path / "requirements-ci-test.txt"
    path.write_text(body, encoding="utf-8")
    return guard.unconstrained_bare_names([path], {"planted-pkg"})


def test_a_bare_constrained_name_with_no_shared_include_is_named(guard, tmp_path):
    """#21471: requirements-ci-test.txt listed pytest-asyncio bare with no -c line, so its own installs floated."""
    found = _unbound(guard, tmp_path, "planted-pkg\nother-pkg\n")
    assert any("planted-pkg" in v and "no -c line" in v for v in found), found


@pytest.mark.parametrize(
    "include",
    ["-c constraints/shared.txt", "-c ../constraints/shared.txt  # why", "--constraint=constraints/shared.txt"],
)
def test_a_bare_constrained_name_under_a_shared_include_is_clean(guard, tmp_path, include):
    assert _unbound(guard, tmp_path, f"{include}\nplanted-pkg\n") == []


def test_a_file_with_no_constrained_bare_name_needs_no_include(guard, tmp_path):
    assert _unbound(guard, tmp_path, "other-pkg\nkombu==5.6.2\n") == []


_COMMENTED_INCLUDES = ["# -c constraints/shared.txt\nplanted-pkg\n", "planted-pkg  # -c constraints/shared.txt\n"]


@pytest.mark.parametrize("body", _COMMENTED_INCLUDES)
def test_a_commented_out_shared_include_does_not_count(guard, tmp_path, body):
    """Negative control: pip ignores a commented ``-c``, so the bare name still floats and must be named."""
    found = _unbound(guard, tmp_path, body)
    assert any("planted-pkg" in v and "no -c line" in v for v in found), found
