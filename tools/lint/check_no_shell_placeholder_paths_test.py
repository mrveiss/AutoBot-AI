#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Discrimination tests for the #14517 shell-placeholder guard.

Every fixture assembles the banned text from fragments rather than quoting it, so
this file does not trip the guard it tests and needs no exemption entry of its
own. That is the whole point: a test that had to be allowlisted would be the
first dormant exemption (#14517).
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from tools.lint import check_no_shell_placeholder_paths as guard

#: The full literal the sweep removed, never written out in one piece here.
FULL = guard.PLACEHOLDER + ":-/opt/autobot/code_source}"


def _tree(base: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    for rel, body in files.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body), encoding="utf-8")
    return base


def _padding(count: int) -> dict[str, str]:
    """Enough clean modules to clear the discovery floor."""
    return {f"pad/mod_{i}.py": "VALUE = 1\n" for i in range(count)}


def _exempt_files() -> dict[str, str]:
    """The three deliberate sites, reproduced with the anchors and counts the guard expects."""
    return {
        "autobot-backend/security/enterprise/compliance_manager.py": (
            f'_LEGACY_AUDIT_ROOT = "{FULL}/logs/audit"\n'
        ),
        "repo_tests/compliance_audit_path_test.py": (
            f'_PLACEHOLDER = "{FULL}/logs/audit"\nHAND = "{guard.PLACEHOLDER}:-"\n'
        ),
        "scripts/check_ansible_file_references_test.py": (
            "def test_paths_that_cannot_be_resolved_statically_are_skipped():\n"
            f'    assert "{FULL}/"\n'
        ),
    }


def _clean_base(tmp_path: pathlib.Path) -> pathlib.Path:
    return _tree(tmp_path, {**_padding(guard.DISCOVERY_FLOOR), **_exempt_files()})


def test_a_clean_tree_passes(tmp_path):
    reached, problems = guard.audit(_clean_base(tmp_path))

    assert problems == []
    assert reached >= guard.DISCOVERY_FLOOR


def test_a_plain_string_constant_is_reported(tmp_path):
    base = _clean_base(tmp_path)
    _tree(base, {"svc/paths.py": f'REPORTS = "{FULL}/reports"\n'})

    _, problems = guard.audit(base)

    assert any("svc/paths.py:1" in p for p in problems)
    assert any(guard.RESOLVER in p for p in problems)


def test_a_docstring_describing_the_defect_is_not_reported(tmp_path):
    base = _clean_base(tmp_path)
    _tree(base, {"svc/doc.py": f'"""Fixed: this used to read {FULL}/logs."""\n\nVALUE = 1\n'})

    _, problems = guard.audit(base)

    assert problems == []


def test_a_docstring_does_not_shield_a_constant_in_the_same_file(tmp_path):
    """The docstring exclusion is structural, so it must not extend to the module body."""
    base = _clean_base(tmp_path)
    _tree(base, {"svc/both.py": f'"""Explains {FULL}."""\n\nBAD = "{FULL}/logs"\n'})

    _, problems = guard.audit(base)

    assert any("svc/both.py:3" in p for p in problems)


def test_an_empty_enumeration_fails_rather_than_reading_clean(tmp_path):
    """A sweep that reaches nothing must never be indistinguishable from a clean sweep."""
    reached, problems = guard.audit(_tree(tmp_path, {}))

    assert reached == 0
    assert any("floor" in p and "assert nothing" in p for p in problems)


def test_a_sweep_far_below_the_floor_fails(tmp_path):
    reached, problems = guard.audit(_tree(tmp_path, _padding(5)))

    assert reached == 5
    assert any(f"floor {guard.DISCOVERY_FLOOR}" in p for p in problems)


def test_an_unparseable_file_fails_instead_of_being_skipped(tmp_path):
    base = _clean_base(tmp_path)
    _tree(base, {"svc/broken.py": "def f(:\n"})

    _, problems = guard.audit(base)

    assert any("svc/broken.py does not parse" in p for p in problems)


def test_an_exemption_whose_file_moved_fails(tmp_path):
    base = _clean_base(tmp_path)
    (base / "repo_tests/compliance_audit_path_test.py").unlink()

    _, problems = guard.audit(base)

    assert any("does not exist" in p and "compliance_audit_path_test.py" in p for p in problems)


def test_an_exemption_whose_anchor_was_renamed_fails(tmp_path):
    base = _clean_base(tmp_path)
    target = base / "autobot-backend/security/enterprise/compliance_manager.py"
    target.write_text(f'_RENAMED_AUDIT_ROOT = "{FULL}/logs/audit"\n', encoding="utf-8")

    _, problems = guard.audit(base)

    assert any("_LEGACY_AUDIT_ROOT" in p and "no longer defines" in p for p in problems)


def test_an_exemption_that_grew_a_second_literal_fails(tmp_path):
    """A fresh defect must not inherit an existing file's exemption."""
    base = _clean_base(tmp_path)
    target = base / "autobot-backend/security/enterprise/compliance_manager.py"
    target.write_text(
        f'_LEGACY_AUDIT_ROOT = "{FULL}/logs/audit"\nNEW_DEFECT = "{FULL}/reports"\n',
        encoding="utf-8",
    )

    _, problems = guard.audit(base)

    assert any("now holds 2" in p for p in problems)


def test_a_dormant_exemption_fails(tmp_path):
    """An exemption whose literal is gone is deleted, not left reading as coverage."""
    base = _clean_base(tmp_path)
    target = base / "scripts/check_ansible_file_references_test.py"
    target.write_text(
        "def test_paths_that_cannot_be_resolved_statically_are_skipped():\n    assert True\n",
        encoding="utf-8",
    )

    _, problems = guard.audit(base)

    assert any("dormant" in p for p in problems)


@pytest.mark.parametrize("rel", [e.path for e in guard.EXEMPTIONS])
def test_every_exemption_describes_the_real_repository(rel):
    """The recorded path, anchor and site count are re-proved against the live tree."""
    assert (guard.repo_root() / rel).is_file()
    assert guard.exemption_problems() == []


def test_the_live_repository_is_clean():
    reached, problems = guard.audit()

    assert problems == [], "\n\n".join(problems)
    assert reached >= guard.DISCOVERY_FLOOR


def test_the_guard_does_not_need_an_exemption_for_itself():
    """A guard that trips its own rule would be the first entry on its own list."""
    assert guard.SELF_REL not in {e.path for e in guard.EXEMPTIONS}
    assert guard.placeholder_sites(guard.repo_root() / guard.SELF_REL) == []
    assert guard.placeholder_sites(pathlib.Path(__file__)) == []
