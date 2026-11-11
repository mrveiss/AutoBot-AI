# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Controls for the filter-entry rules that replaced the per-PR allowance tables (#21205).

Each rule in ``repo_tests/_filter_entries.py`` has a known-positive control that does not depend on
the repository's current filters, and a planted pair shows two PRs that each widen a filter under
their own comment block merge without a conflict (the old tables made them edit the same lines).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._filter_entries import (
    agreed_entries,
    parse_entries,
    removed_without_tombstone,
    split_against_snapshot,
    uncited,
    yaml_entries,
)
from repo_tests._ratchet_base import BASE_REF_ENV, BASE_SHA_ENV, BaseUnavailable, base_commit, base_text

from autobot_shared.isolated_git import git, make_repo

FILTER = ".github/filters/demo-paths.yml"
BASE = """\
# the demo filter
demo: &demo
  - 'a/**'
  - "b/**"
  # #1111: a guard reads c
  - 'c/one.txt'

# a second block, cited below when something lands in it
other:
  - *demo
  - 'z/**'
"""
SNAPSHOT = [
    ("demo", "a/**"),
    ("demo", "b/**"),
    ("demo", "c/one.txt"),
    ("other", "a/**"),
    ("other", "b/**"),
    ("other", "c/one.txt"),
    ("other", "z/**"),
]


def _with(text: str, anchor: str, add: str) -> str:
    return text.replace(anchor, anchor + add, 1)


def test_the_unchanged_file_passes_and_the_line_reader_agrees_with_yaml():
    assert uncited(BASE, SNAPSHOT) == []
    assert [(e.key, e.value) for e in agreed_entries(BASE)] == SNAPSHOT


def test_an_uncited_new_entry_fails():
    head = _with(BASE, "  - 'z/**'\n", "  - 'y/new.txt'\n")
    found = uncited(head, SNAPSHOT)
    assert len(found) == 1 and "'y/new.txt'" in found[0] and "cites no" in found[0]


def test_a_cited_new_entry_passes_by_its_own_line_or_the_block_above():
    on_line = _with(BASE, "  - 'z/**'\n", "  - 'y/new.txt'  # #2222\n")
    above = _with(BASE, "  - 'z/**'\n", "  # #2222: a guard reads y\n  - 'y/new.txt'\n  - 'y/two.txt'\n")
    assert uncited(on_line, SNAPSHOT) == [] and uncited(above, SNAPSHOT) == []


def test_a_citation_further_up_does_not_cover_an_entry_after_a_blank_line():
    head = _with(BASE, "  - 'z/**'\n", "  # #2222: a guard reads y\n  - 'y/new.txt'\n\n  - 'y/two.txt'\n")
    assert [("y/two.txt" in f) for f in uncited(head, SNAPSHOT)] == [True]


def test_an_added_entry_in_the_anchored_list_is_judged_at_its_definition():
    bare = _with(BASE, "  - 'a/**'\n", "  - 'a/two.txt'\n")
    cited = _with(BASE, "  - 'a/**'\n", "  - 'a/two.txt'  # #2222\n")
    assert len(uncited(bare, SNAPSHOT)) == 2  # once under demo, once through the alias under other
    assert uncited(cited, SNAPSHOT) == []


def test_a_dropped_or_reordered_snapshot_entry_fails():
    dropped = BASE.replace('  - "b/**"\n', "")
    swapped = BASE.replace("  - 'a/**'\n  - \"b/**\"\n", "  - \"b/**\"\n  - 'a/**'\n")
    assert any("gone or out of order" in f for f in uncited(dropped, SNAPSHOT))
    assert any("gone or out of order" in f for f in uncited(swapped, SNAPSHOT))
    assert split_against_snapshot(SNAPSHOT, agreed_entries(BASE))[0] == []


def test_a_removal_needs_a_tombstone_in_the_head_file():
    head = BASE.replace("  - 'z/**'\n", "")
    assert removed_without_tombstone(BASE, head) and "'z/**'" in removed_without_tombstone(BASE, head)[0]
    stoned = "# retired #3333: 'z/**'\n" + head
    assert removed_without_tombstone(BASE, stoned) == []
    assert removed_without_tombstone(None, head) == []  # a file the base lacked has nothing to lose


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    make_repo(tmp_path)
    (tmp_path / FILTER).parent.mkdir(parents=True)
    (tmp_path / FILTER).write_text(BASE, encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path, git(tmp_path, "rev-parse", "HEAD").stdout.strip()


def test_a_removal_is_judged_against_the_base_the_real_resolver_names(repo, monkeypatch):
    """`AUTOBOT_RATCHET_BASE_SHA` (as ci.yml sets it) names the planted base; `base_commit` resolves it."""
    root, base = repo
    (root / FILTER).write_text("other:\n  - 'q/**'\n", encoding="utf-8")
    git(root, "commit", "-q", "-am", "main moves on")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv(BASE_SHA_ENV, base)
    assert base_commit(root) == base
    head = BASE.replace("  - 'z/**'\n", "")
    found = removed_without_tombstone(base_text(root, FILTER), head)  # no sha: the resolver picks it
    assert len(found) == 1 and "'z/**'" in found[0]
    assert removed_without_tombstone(base_text(root, FILTER), "# retired #3333: 'z/**'\n" + head) == []


def test_an_uncited_entry_appended_to_a_cited_run_fails():
    """The run's block cites `c/one.txt`; it must not vouch for an entry appended to it."""
    head = _with(BASE, "  - 'c/one.txt'\n", "  - 'c/two.txt'\n")
    found = uncited(head, SNAPSHOT, BASE)
    assert len(found) == 2 and all("'c/two.txt'" in f for f in found)  # under demo and through the alias
    own = _with(BASE, "  - 'c/one.txt'\n", "  - 'c/two.txt'  # #2222\n")
    assert uncited(own, SNAPSHOT, BASE) == []


def test_a_landed_run_still_passes_when_judged_with_its_base():
    """Entries that landed under one block stay valid; only a NEW entry cannot inherit it."""
    landed = _with(BASE, "  - 'z/**'\n", "  # #2222: landed\n  - 'y/one.txt'\n  - 'y/two.txt'\n")
    assert uncited(landed, SNAPSHOT, landed) == []
    assert len(uncited(_with(landed, "  - 'y/two.txt'\n", "  - 'y/three.txt'\n"), SNAPSHOT, landed)) == 1


def test_the_line_reader_agrees_with_yaml_on_every_filter_file():
    root = Path(__file__).resolve().parent.parent
    files = sorted(f for f in (root / ".github" / "filters").iterdir() if f.suffix == ".yml")
    assert len(files) >= 5 and "docs-only-paths.yml" in {f.name for f in files}
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert [(e.key, e.value) for e in parse_entries(text)] == yaml_entries(text), f.name


def test_a_planted_disagreement_trips_the_agreement_check():
    """A flow-style list is valid YAML the line reader cannot see; the check must say so."""
    with pytest.raises(AssertionError, match="disagree"):
        agreed_entries("demo: ['a/**', 'b/**']\n")
    assert parse_entries("demo: ['a/**']\n") == [] and yaml_entries("demo: ['a/**']\n") == [("demo", "a/**")]


def test_base_unavailable_propagates_and_is_never_a_pass(repo, monkeypatch):
    root, _ = repo
    monkeypatch.setenv(BASE_REF_ENV, "origin/does-not-exist")
    with pytest.raises(BaseUnavailable):
        removed_without_tombstone(base_text(root, FILTER), BASE)


def test_two_prs_each_adding_a_cited_entry_under_their_own_block_merge_and_both_pass(repo):
    root, base = repo
    planted = BASE.replace("other:\n", "# #4444: the planted block\nother:\n")
    (root / FILTER).write_text(planted, encoding="utf-8")
    git(root, "commit", "-q", "-am", "two blocks")
    fork = git(root, "rev-parse", "HEAD").stdout.strip()
    adds = (
        ("a", "  - 'c/one.txt'\n", "  # #5555: first\n  - 'c/a-new.txt'\n"),
        ("b", "  - 'z/**'\n", "  # #6666: second\n  - 'z/b-new.txt'\n"),
    )
    texts = {}
    for branch, anchor, add in adds:
        git(root, "switch", "-q", "-c", branch, fork)
        texts[branch] = _with(planted, anchor, add)
        (root / FILTER).write_text(texts[branch], encoding="utf-8")
        git(root, "commit", "-q", "-am", f"widen {branch}")
        assert uncited(texts[branch], SNAPSHOT) == []
    merged = git(root, "merge-tree", fork, "a", "b", check=False)  # the 3-arg form; local git is 2.34
    assert merged.returncode == 0 and "<<<<<<<" not in merged.stdout, merged.stdout + merged.stderr
    git(root, "switch", "-q", "a")
    git(root, "merge", "-q", "--no-edit", "b")
    assert uncited((root / FILTER).read_text(encoding="utf-8"), SNAPSHOT) == []
    assert removed_without_tombstone(base_text(root, FILTER, fork), (root / FILTER).read_text(encoding="utf-8")) == []


def test_contrast_two_prs_editing_one_shared_table_do_conflict(repo):
    """Control: the old shape (each PR appends to the same adjacent table lines) is what conflicted."""
    root, base = repo
    for branch in ("a", "b"):
        git(root, "switch", "-q", "-c", branch, base)
        text = (root / FILTER).read_text(encoding="utf-8").replace("  - 'z/**'\n", f"  - 'z/**'\n  - 'new/{branch}'\n")
        (root / FILTER).write_text(text, encoding="utf-8")
        git(root, "commit", "-q", "-am", branch)
    merged = git(root, "merge-tree", base, "a", "b", check=False)
    assert "<<<<<<<" in merged.stdout, "the known-bad shape stopped conflicting; the planted pair proves nothing"
