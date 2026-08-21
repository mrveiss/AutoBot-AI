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


def test_audit_fails_on_zero_ci_packages(tmp_path):
    """The sibling of test_audit_fails_on_zero_production_packages — same guard,
    same anti-empty-result requirement, other side of the comparison. audit_drift()
    has a symmetric `if not ci:` branch that was previously exercised only ad hoc."""
    (tmp_path / "autobot-backend").mkdir()
    (tmp_path / "autobot-backend" / "requirements.txt").write_text("widget>=1.0\n", encoding="utf-8")
    (tmp_path / "autobot-slm-backend").mkdir()
    (tmp_path / "autobot-slm-backend" / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / "requirements-ci.txt").write_text("", encoding="utf-8")
    reached, problems = checker.audit_drift(tmp_path)
    assert reached == 1
    assert problems and "zero packages" in problems[0]


def test_audit_is_clean_on_the_real_tree():
    """The live repo's guard must pass against itself — proves the seed was accurate."""
    reached, problems = checker.audit_drift()
    assert reached > 50, f"only {reached} production packages reached — the parse silently collapsed"
    assert problems == [], problems


# --------------------------------------------------------------------------
# The #13885/#14551 regression this PR fixes
# --------------------------------------------------------------------------


def test_pytesseract_is_tracked_pending_the_colliding_pr():
    """The headline incident this issue documents, without racing #14510.

    pytesseract sat declared in production and undeclared in CI for months
    (#13885) while every real OCR test skipped — normally this guard's policy
    is "mirror it, don't allowlist it" (see the fixes for scikit-learn, ldap3,
    etc. below). pytesseract is the one deliberate exception: #14510 (open as
    of this writing) already adds it to requirements-ci/document.txt for its
    own OCR-fallback feature. Landing it from BOTH PRs would collide, so it is
    allowlisted here instead, with a comment pointing at #14510 — and the
    audit will force this line's removal the moment either PR lands it for
    real, which is the self-correcting property that makes the exception safe.
    """
    allowlist = checker.load_allowlist()
    assert "pytesseract" in allowlist, "pytesseract must stay tracked (allowlisted) until #14510 lands it for real"


def test_the_9_corrected_baseline_entries_are_now_mirrored_not_allowlisted():
    """Re-proves the code-reviewer finding this baseline was corrected against.

    9 packages were allowlisted with a false "no CI-scoped test" rationale
    while a real importorskip/find_spec gate existed and silently skipped.
    Each must now be a genuine CI package, not still papering over the gap.
    """
    ci = checker.ci_requirement_names()
    allowlist = checker.load_allowlist()
    corrected = {
        "scikit-learn",
        "ldap3",
        "weasyprint",
        "faiss-cpu",
        "datasketch",
        "tree-sitter-python",
        "trafilatura",
        "yt-dlp",
        "ddgs",
    }
    for name in corrected:
        assert name in ci, f"{name} must be declared in requirements-ci/*.txt (#14551)"
        assert name not in allowlist, f"{name} must not be allowlisted — it is a corrected false rationale"


def test_bcrypt_and_pydantic_settings_are_mirrored_not_allowlisted():
    """autobot_shared/pyproject.toml is NOT installed by CI (#13411's shape).

    Both are unconditionally imported by autobot_shared modules reached by
    nearly the whole suite (auth/jwt_core.py, ssot_config.py) — the same
    class of bug as the pre-existing PyJWT[crypto] comment in security.txt,
    just not previously caught for these two.
    """
    ci = checker.ci_requirement_names()
    allowlist = checker.load_allowlist()
    for name in ("bcrypt", "pydantic-settings"):
        assert name in ci, f"{name} must be declared in requirements-ci/*.txt (#14551)"
        assert name not in allowlist, f"{name} must not be allowlisted — collection-critical, not a soft omission"


def test_tree_sitter_core_is_mirrored_alongside_tree_sitter_python():
    """A real CI run (not a local audit) caught the third false rationale.

    tree-sitter-python was mirrored assuming it pulled in the base
    `tree-sitter` package transitively -- it does not, and 4 shards went red
    on the real runner with "No module named 'tree_sitter'" before this was
    fixed. Pin both packages present and neither allowlisted, so a future
    edit cannot quietly re-introduce the same unverified-transitive-resolution
    mistake for this specific pair.
    """
    ci = checker.ci_requirement_names()
    allowlist = checker.load_allowlist()
    for name in ("tree-sitter", "tree-sitter-python"):
        assert name in ci, f"{name} must be declared in requirements-ci/*.txt (#14551)"
        assert name not in allowlist, f"{name} must not be allowlisted — verified missing on the real CI runner"
    # tree-sitter-javascript is the deliberate exception: no CI-scoped test
    # gates on it directly, so it stays allowlisted.
    assert "tree-sitter-javascript" in allowlist


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
