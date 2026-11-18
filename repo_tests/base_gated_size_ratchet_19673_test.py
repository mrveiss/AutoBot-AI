# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The size ratchets are gated against the merge base, so a shrinking PR edits no shared table (#19673).

Rule: ``lines(F@HEAD) <= min(KNOWN_LARGE[F], lines(F@base))``. These tests drive
``repo_tests._ratchet_base.growth_over_base`` over a temporary git repository, so each clause has a
known-positive control that does not depend on the repository's current contents.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._ratchet_base import BASE_REF_ENV, BaseUnavailable, base_commit, base_line_counts, growth_over_base

from autobot_shared.isolated_git import git, make_repo

F = "pkg/big.py"
G = "pkg/other.py"


def _git(root: Path, *args: str) -> str:
    return git(root, *args).stdout.strip()


def _write(root: Path, rel: str, lines: int) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text("x\n" * lines, encoding="utf-8")


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """A repo whose ``main`` holds F at 700 and G at 650; returns (root, base sha)."""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    make_repo(tmp_path)
    _write(tmp_path, F, 700)
    _write(tmp_path, G, 650)
    return tmp_path, _commit(tmp_path, "base")


def test_growth_by_one_line_fails(repo):
    root, base = repo
    _write(root, F, 701)
    found = growth_over_base(root, {F: 700, G: 650}, base)
    assert list(found) == [F] and "701" in found[F]


def test_shrinking_passes_with_the_table_untouched(repo):
    root, base = repo
    _write(root, F, 690)  # the table still says 700
    assert growth_over_base(root, {F: 700, G: 650}, base) == {}


def test_a_stale_high_ceiling_does_not_license_regrowth(repo):
    """The base is the tight gate: a ceiling above the base's length buys nothing."""
    root, base = repo
    _write(root, F, 700)
    assert growth_over_base(root, {F: 999}, base) == {}
    _write(root, F, 701)
    assert F in growth_over_base(root, {F: 999}, base)


def test_a_raised_ceiling_does_not_help(repo):
    root, base = repo
    _write(root, F, 710)
    assert F in growth_over_base(root, {F: 710}, base)


def test_a_ceiling_below_the_base_still_binds(repo):
    """The min() has two arms: HEAD under the base but over the recorded ceiling fails."""
    root, base = repo
    _write(root, F, 695)  # base is 700, ceiling 690
    assert F in growth_over_base(root, {F: 690}, base)
    _write(root, F, 690)
    assert growth_over_base(root, {F: 690}, base) == {}


def test_a_renamed_file_gets_the_move_the_entry_hint(repo):
    """git mv of a grandfathered file: the path is absent at the base, and the message says what to do."""
    root, base = repo
    _git(root, "mv", F, "pkg/moved.py")
    found = growth_over_base(root, {"pkg/moved.py": 700}, base)
    assert "renamed? move its entry in the table" in found["pkg/moved.py"]


def test_an_entry_added_for_a_file_new_at_the_base_is_blocked(repo):
    root, base = repo
    _write(root, "pkg/new.py", 800)
    found = growth_over_base(root, {"pkg/new.py": 800}, base)
    assert "not at the base" in found["pkg/new.py"]


def test_an_unreadable_head_file_is_a_finding_not_a_skip(repo):
    root, base = repo
    (root / F).unlink()
    assert "never measured" in growth_over_base(root, {F: 700}, base)[F]


def test_it_fails_closed_when_no_base_is_readable(repo, monkeypatch):
    root, _ = repo
    monkeypatch.setenv(BASE_REF_ENV, "origin/does-not-exist")
    with pytest.raises(BaseUnavailable):
        growth_over_base(root, {F: 700})
    with pytest.raises(BaseUnavailable):
        base_line_counts(root, [F], "0" * 40)


def test_the_base_is_the_merge_base_not_the_tip(repo, monkeypatch):
    """Main moves on (F shrinks to 600-ish there); a branch cut earlier is judged against ITS fork point."""
    root, fork = repo
    _git(root, "switch", "-q", "-c", "feature")
    _git(root, "switch", "-q", "main")
    _write(root, F, 680)
    _commit(root, "main shrinks F")
    _git(root, "switch", "-q", "feature")
    _write(root, F, 700)  # unchanged on the branch
    monkeypatch.setenv(BASE_REF_ENV, "main")
    assert base_commit(root) == fork
    assert growth_over_base(root, {F: 700}) == {}, "an untouched file must not fail because main moved"


def test_adjacent_shrinks_merge_cleanly_and_pass(repo):
    """Two PRs shrinking neighbouring files conflict on nothing, because neither edits the table."""
    root, base = repo
    table = root / "table.py"
    table.write_text(f'KNOWN_LARGE = {{\n    "{F}": 700,\n    "{G}": 650,\n}}\n', encoding="utf-8")
    base = _commit(root, "table")
    for branch, rel, n in (("a", F, 690), ("b", G, 640)):
        _git(root, "switch", "-q", "-c", branch, base)
        _write(root, rel, n)  # a shrink edits the file only, never the table
        _commit(root, f"shrink {rel}")
    merged = git(root, "merge-tree", base, "a", "b", check=False)  # the form every git version has
    assert merged.returncode == 0 and "<<<<<<<" not in merged.stdout, merged.stdout + merged.stderr
    _git(root, "switch", "-q", "a")
    _git(root, "merge", "-q", "--no-edit", "b")
    assert growth_over_base(root, {F: 700, G: 650}, base) == {}


def test_contrast_adjacent_table_edits_do_conflict(repo):
    """Control for the test above: the old way (each PR lowers its own table line) is what conflicted."""
    root, _ = repo
    table = root / "table.py"
    table.write_text(f'KNOWN_LARGE = {{\n    "{F}": 700,\n    "{G}": 650,\n}}\n', encoding="utf-8")
    base = _commit(root, "table")
    for branch, old, new in (("a", f'"{F}": 700', f'"{F}": 690'), ("b", f'"{G}": 650', f'"{G}": 640')):
        _git(root, "switch", "-q", "-c", branch, base)
        table.write_text(table.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
        _commit(root, f"lower {new}")
    merged = git(root, "merge-tree", base, "a", "b", check=False)
    assert "<<<<<<<" in merged.stdout, "the known-bad shape stopped conflicting; the control proves nothing"
