# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The down-only ratchets' base read: it catches a raise, and it refuses rather than guesses (#19283).

Hand-summed totals (MAX_CEILING_TOTAL, TOTAL_OCCURRENCES, css_rule_declarations) were the tripwire for a raised entry, and every PR that lowered any
entry edited the same total line, so two such PRs always conflicted. The tripwire is now the base
commit's own table (repo_tests/_ratchet_base.py). These tests pin its two promises: a raised or
added entry is reported, and a base it cannot read is an error, never "nothing rose".
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._ratchet_base import BaseUnavailable, base_commit, base_table, base_text, literal_in, raised_entries

from autobot_shared.isolated_git import git, make_repo


def test_a_raised_or_added_entry_is_reported_and_a_lowered_one_is_not() -> None:
    base = {"a.py": 700, "b.py": 650, "gone.py": 610}
    now = {"a.py": 701, "b.py": 640, "new.py": 900}
    assert raised_entries(now, base) == {"a.py": (700, 701), "new.py": (None, 900)}
    assert raised_entries({"a.py": 700}, base) == {}


def test_two_prs_lowering_different_entries_each_pass_against_the_same_base() -> None:
    """AC2: no shared line -- each PR's table is checked entry by entry against the base."""
    base = {"a.py": 700, "b.py": 650}
    assert raised_entries({"a.py": 690, "b.py": 650}, base) == {}
    assert raised_entries({"a.py": 700, "b.py": 640}, base) == {}
    assert raised_entries({"a.py": 690, "b.py": 640}, base) == {}


def _repo(tmp_path: Path, commits: int) -> Path:
    repo = make_repo(tmp_path / "repo")
    for n in range(commits):
        (repo / "table.py").write_text(f"KNOWN_LARGE = {{'x.py': {700 - n}}}\n", encoding="utf-8")
        git(repo, "add", "table.py")
        git(repo, "commit", "-q", "-m", f"c{n}")
    return repo


def test_in_ci_a_missing_head_parent_refuses_instead_of_passing(tmp_path, monkeypatch) -> None:
    """A depth-1 checkout has no HEAD^1: the ratchet must say so, never report 'nothing rose'."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    # CI itself may export the base (a push, or a PR into release, #19466); this test owns it
    monkeypatch.delenv("AUTOBOT_RATCHET_BASE_SHA", raising=False)
    with pytest.raises(BaseUnavailable, match="fetch-depth: 2"):
        base_commit(_repo(tmp_path, commits=1))


def test_in_ci_the_base_is_head_parent_and_reads_its_table(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    # CI itself may export the base (a push, or a PR into release, #19466); this test owns it
    monkeypatch.delenv("AUTOBOT_RATCHET_BASE_SHA", raising=False)
    repo = _repo(tmp_path, commits=2)
    assert literal_in(base_text(repo, "table.py"), "KNOWN_LARGE") == {"x.py": 700}
    assert base_text(repo, "not-there.py") is None


def test_locally_an_unresolvable_base_ref_refuses(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("AUTOBOT_RATCHET_BASE_REF", "origin/no-such-branch")
    with pytest.raises(BaseUnavailable, match="merge-base"):
        base_commit(_repo(tmp_path, commits=1))


def _history(tmp_path: Path, *tables: str, path: str = "table.py") -> tuple[Path, list[str]]:
    """A repo with one commit per table body (each written to *path*); returns (repo, shas)."""
    repo = make_repo(tmp_path / "hist")
    shas = []
    for body in tables:
        (repo / path).write_text(body, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "c")
        shas.append(git(repo, "rev-parse", "HEAD").stdout.strip())
    return repo, shas


def _ci(monkeypatch, *, base_sha: str = "") -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    # CI itself may export the base (a push, or a PR into release, #19466); this test owns it
    monkeypatch.delenv("AUTOBOT_RATCHET_BASE_SHA", raising=False)
    monkeypatch.setenv("AUTOBOT_RATCHET_BASE_SHA", base_sha)


def test_a_raise_its_pr_run_missed_turns_mains_landing_push_red(tmp_path, monkeypatch) -> None:
    """#19283 review: c1 raised 700 -> 720 and the PR run that spanned it was cancelled. Main's
    push run compares with `event.before` (c0, always an ancestor), so the landing push sees it,
    even when HEAD^1 (c1) already agrees with 720."""
    repo, shas = _history(tmp_path, "T = {'x.py': 700}\n", "T = {'x.py': 720}\n", "T = {'x.py': 720, 'y.py': 1}\n")
    _ci(monkeypatch)
    assert raised_entries({"x.py": 720}, base_table(repo, ("table.py",), "T")) == {}
    _ci(monkeypatch, base_sha=shas[0])
    assert raised_entries({"x.py": 720}, base_table(repo, ("table.py",), "T")) == {"x.py": (700, 720)}


def test_raising_both_mirrors_together_is_still_refused(tmp_path, monkeypatch) -> None:
    """The case a mirrored pair could not catch: hook and mirror raised in one commit."""
    repo, _ = _history(
        tmp_path,
        "KNOWN_LARGE = {'x.py': 700}\nMIRROR = {'x.py': 700}\n",
        "KNOWN_LARGE = {'x.py': 750}\nMIRROR = {'x.py': 750}\n",
    )
    _ci(monkeypatch)
    now = literal_in((repo / "table.py").read_text(encoding="utf-8"), "KNOWN_LARGE")
    assert raised_entries(now, base_table(repo, ("table.py",), "KNOWN_LARGE")) == {"x.py": (700, 750)}


def test_a_moved_table_is_read_from_its_old_path_at_the_base(tmp_path, monkeypatch) -> None:
    repo, _ = _history(tmp_path, "T = {'x.py': 700}\n")
    git(repo, "mv", "table.py", "moved.py")
    git(repo, "commit", "-q", "-m", "move")
    _ci(monkeypatch)
    assert base_table(repo, ("moved.py", "table.py"), "T") == {"x.py": 700}
    assert base_table(repo, ("moved.py",), "T") == {}, "without the old path every entry is an addition"


def test_an_event_base_sha_is_used_and_a_zero_one_is_ignored(tmp_path, monkeypatch) -> None:
    """merge_group.base_sha / push before: a 3-commit push is compared with its real base."""
    repo, shas = _history(tmp_path, "T = {'x.py': 700}\n", "T = {'x.py': 710}\n", "T = {'x.py': 720}\n")
    _ci(monkeypatch, base_sha=shas[0])
    assert base_commit(repo) == shas[0]
    _ci(monkeypatch, base_sha="0" * 40)
    assert base_commit(repo) == shas[1]


def test_an_unfetched_event_base_refuses(tmp_path, monkeypatch) -> None:
    repo, _ = _history(tmp_path, "T = {}\n", "T = {'x.py': 1}\n")
    _ci(monkeypatch, base_sha="1" * 40)
    with pytest.raises(BaseUnavailable, match="AUTOBOT_RATCHET_BASE_SHA"):
        base_commit(repo)


def test_no_later_merge_can_cancel_a_push_to_main():
    """#19283 review: the backstop is main's push run, so it must not share a cancellable
    group. Per-ref, GitHub's `queue: single` cancelled the pending push when the next merge
    queued, and the next merge's base already held the raise."""
    import yaml  # noqa: PLC0415

    ci = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    group = ci["concurrency"]["group"]
    assert "github.event_name == 'push' && github.sha" in group, f"push runs must key on their commit: {group!r}"
    assert ci["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
