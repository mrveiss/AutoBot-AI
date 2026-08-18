# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14551 — production and CI Python dependency sets are hand-mirrored; catch silent drift.

Exercises the exact functions ``code-quality`` calls
(``tools/lint/check_requirements_ci_drift.py --audit``) rather than
paraphrasing the rule, so a test agreeing with a second copy of the decision
proves nothing about the copy that actually blocks a merge.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECKER = REPO_ROOT / "tools" / "lint" / "check_requirements_ci_drift.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_requirements_ci_drift", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


# --------------------------------------------------------------------------
# The invariant, against synthetic input
# --------------------------------------------------------------------------


def test_compute_drift_flags_a_package_missing_from_ci_and_not_allowlisted():
    production = {"foo": "foo>=1.0", "bar": "bar>=2.0"}
    ci = {"bar": "bar==2.0"}
    new_drift, stale = checker.compute_drift(production, ci, allowlist=set())
    assert new_drift == ["foo"]
    assert stale == []


def test_compute_drift_accepts_an_allowlisted_omission():
    production = {"foo": "foo>=1.0"}
    ci: dict[str, str] = {}
    new_drift, stale = checker.compute_drift(production, ci, allowlist={"foo"})
    assert new_drift == []
    assert stale == []


def test_compute_drift_rejects_a_stale_allowlist_entry_now_fixed():
    """An entry CI now installs must be removed, not left exempting nothing."""
    production = {"foo": "foo>=1.0"}
    ci = {"foo": "foo==1.0"}
    new_drift, stale = checker.compute_drift(production, ci, allowlist={"foo"})
    assert new_drift == []
    assert stale == ["foo"]


def test_compute_drift_rejects_a_stale_allowlist_entry_now_removed():
    """An entry for a package production no longer declares is also stale."""
    production: dict[str, str] = {}
    ci: dict[str, str] = {}
    new_drift, stale = checker.compute_drift(production, ci, allowlist={"ghost-package"})
    assert new_drift == []
    assert stale == ["ghost-package"]


def test_normalize_treats_underscores_dots_and_dashes_as_equivalent():
    assert checker._normalize("python_dotenv") == checker._normalize("python-dotenv")
    assert checker._normalize("PyYAML") == "pyyaml"


# --------------------------------------------------------------------------
# Discrimination — against a real (synthetic) tree on disk
# --------------------------------------------------------------------------


def _write_tree(tmp_path, *, prod_pkgs: list[str], ci_pkgs: list[str], allowlist: list[str]):
    backend = tmp_path / "autobot-backend"
    backend.mkdir()
    (backend / "requirements.txt").write_text("\n".join(prod_pkgs) + "\n", encoding="utf-8")
    slm = tmp_path / "autobot-slm-backend"
    slm.mkdir()
    (slm / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / "requirements-ci.txt").write_text("\n".join(ci_pkgs) + "\n", encoding="utf-8")
    repo_tests = tmp_path / "repo_tests"
    repo_tests.mkdir()
    (repo_tests / "requirements_ci_drift_baseline.txt").write_text("\n".join(allowlist) + "\n", encoding="utf-8")


def test_audit_fails_on_an_undeclared_omission(tmp_path):
    # ci_pkgs carries an unrelated entry so the CI parse itself is non-empty —
    # an empty CI file is a *different* failure mode, covered separately below.
    _write_tree(tmp_path, prod_pkgs=["widget>=1.0"], ci_pkgs=["gadget==1.0"], allowlist=[])
    reached, problems = checker.audit_drift(tmp_path)
    assert reached == 1
    assert problems, "an undeclared production-only package must fail the audit"
    assert "widget" in problems[0]


def test_audit_passes_when_the_omission_is_allowlisted(tmp_path):
    _write_tree(tmp_path, prod_pkgs=["widget>=1.0"], ci_pkgs=["gadget==1.0"], allowlist=["widget"])
    reached, problems = checker.audit_drift(tmp_path)
    assert reached == 1
    assert problems == []


def test_audit_fails_on_zero_production_packages(tmp_path):
    """A moved/renamed requirements.txt must not read as a clean scan of nothing."""
    (tmp_path / "autobot-backend").mkdir()
    (tmp_path / "autobot-backend" / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / "autobot-slm-backend").mkdir()
    (tmp_path / "autobot-slm-backend" / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / "requirements-ci.txt").write_text("widget==1.0\n", encoding="utf-8")
    reached, problems = checker.audit_drift(tmp_path)
    assert reached == 0
    assert problems and "zero packages" in problems[0]


def test_audit_is_clean_on_the_real_tree():
    """The live repo's guard must pass against itself — proves the seed was accurate."""
    reached, problems = checker.audit_drift()
    assert reached > 50, f"only {reached} production packages reached — the parse silently collapsed"
    assert problems == [], problems


# --------------------------------------------------------------------------
# The #13885/#14551 regression this PR fixes
# --------------------------------------------------------------------------


def test_pytesseract_is_mirrored_into_ci_not_allowlisted():
    """The headline incident this issue documents must not recur.

    pytesseract sat declared in production and undeclared in CI for months
    (#13885) while every real OCR test skipped. It must now be a genuine CI
    package, not an allowlist entry papering over the same gap again.
    """
    ci = checker.ci_requirement_names()
    allowlist = checker.load_allowlist()
    assert "pytesseract" in ci, "pytesseract must be declared in requirements-ci/*.txt (#14551)"
    assert "pytesseract" not in allowlist, "pytesseract must not be allowlisted — it is the bug this guard exists for"


# --------------------------------------------------------------------------
# The audit entrypoint, and the check that actually runs it
# --------------------------------------------------------------------------


def test_code_quality_runs_the_audit():
    """A guard nothing invokes is documentation, not enforcement."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "code-quality.yml").read_text(encoding="utf-8")
    assert "check_requirements_ci_drift.py --audit" in workflow, (
        "code-quality.yml no longer runs the requirements-ci drift audit — the guard "
        "would stop blocking merges while these tests kept passing (#14551)"
    )
    assert _CHECKER.is_file(), f"{_CHECKER} is gone but the workflow still calls it"


def test_the_checker_needs_no_third_party_import():
    """It must run in a job that installs linters, not the application's dependencies."""
    source = _CHECKER.read_text(encoding="utf-8")
    third_party = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
        and not line.startswith("from __future__")
        and line.split()[1].split(".")[0] not in {"argparse", "logging", "pathlib", "re", "sys"}
    ]
    assert third_party == [], f"the checker imports non-stdlib modules: {third_party}"
