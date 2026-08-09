# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Co-change coupling over real git history (#13639).

The property that decides whether this is useful or noise: **a file touched by
every commit must not read as coupled to everything.** A raw co-change count says
the changelog is the most coupled file in the repo. Normalising by the *larger* of
the two change counts is what makes the number mean something, so that is what the
tests here pin — on a real repository built in a tmpdir, because the input is git
and a fake would not exercise the part that costs.
"""

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from code_intelligence.co_change import CoChangeAnalyzer, CoChangePair
from code_intelligence.code_evolution_miner import GitHistoryCrawler


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo: Path, files: dict, message: str) -> None:
    for name, content in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


@pytest.fixture
def repo(tmp_path):
    """A repo whose history contains one genuinely coupled pair and one busy file."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")

    # schema.py and serializer.py always move together — the signal.
    # changelog.md moves in every commit — the noise the formula must reject.
    for i in range(6):
        _commit(
            tmp_path,
            {
                "schema.py": f"schema v{i}\n",
                "serializer.py": f"serializer v{i}\n",
                "changelog.md": f"entry {i}\n",
            },
            f"coupled change {i}",
        )
    # Twenty commits each touching a *different* file alongside the changelog. The
    # changelog therefore co-changes once with each — busy, but coupled to nothing.
    # Pairing it repeatedly with one file would be real coupling by any measure,
    # and would say nothing about whether the formula suppresses noise.
    for i in range(20):
        _commit(tmp_path, {f"solo_{i}.py": f"v{i}\n", "changelog.md": f"entry solo {i}\n"}, f"unrelated {i}")
    return tmp_path


def _pairs(repo_path: Path, **kwargs):
    file_sets, skipped = GitHistoryCrawler(str(repo_path)).get_commit_file_sets()
    return CoChangeAnalyzer(**kwargs).analyze(file_sets), skipped


def _pair_names(pairs):
    return {(p.source, p.target) for p in pairs}


# --------------------------------------------------------------- the signal


def test_a_genuinely_coupled_pair_is_found(repo):
    pairs, _ = _pairs(repo)

    assert ("schema.py", "serializer.py") in _pair_names(pairs)


def test_the_coupled_pair_is_the_strongest(repo):
    pairs, _ = _pairs(repo)

    assert pairs, "no pairs at all"
    assert (pairs[0].source, pairs[0].target) == ("schema.py", "serializer.py")
    assert pairs[0].strength == 1.0, "a pair that only ever moves together is total coupling"


# ------------------------------------------- the noise the formula must reject


def test_a_file_touched_by_every_commit_is_not_coupled_to_everything(repo):
    """The load-bearing property.

    ``changelog.md`` appears in all 26 commits, so a raw count makes it the most
    coupled file in the repo. Dividing by the larger change count gives
    6/26 = 0.23 against ``schema.py`` — below threshold, correctly.
    """
    pairs, _ = _pairs(repo)

    involved = [p for p in pairs if "changelog.md" in (p.source, p.target)]
    assert involved == [], f"the busy file was reported as coupled: {[(p.source, p.target) for p in involved]}"


def test_dividing_by_the_smaller_count_would_have_reported_it(repo):
    """Names the alternative and shows why it was not chosen.

    Under ``min()``, ``changelog.md``/``schema.py`` scores 6/6 = 1.0 — the busiest
    file in the repo, reported as perfectly coupled to something it merely
    outlived.
    """
    pairs, _ = _pairs(repo, min_co_changes=1, strength_threshold=0.0)
    busy = next(p for p in pairs if {"changelog.md", "schema.py"} == {p.source, p.target})

    assert busy.co_changes / min(busy.source_changes, busy.target_changes) == 1.0
    assert busy.strength < 0.3, "the chosen denominator failed to suppress the busy file"


# ------------------------------------------------------- thresholds and caps


def test_a_pair_below_the_minimum_count_is_not_reported(repo):
    pairs, _ = _pairs(repo, min_co_changes=7)

    assert pairs == [], "a pair under the count threshold was reported"


def test_thresholds_are_configurable_not_baked_in(repo):
    strict, _ = _pairs(repo, strength_threshold=0.99)
    loose, _ = _pairs(repo, strength_threshold=0.0, min_co_changes=1)

    assert len(loose) > len(strict)


def test_an_over_cap_commit_is_skipped_and_counted(tmp_path, monkeypatch):
    """A bulk rename must be excluded, and must say so.

    Truncating to the first N files would invent pairs no author ever related —
    worse than admitting the commit was not analysed.
    """
    import code_intelligence.code_evolution_miner as miner

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, {"a.py": "1\n", "b.py": "1\n"}, "small")
    _commit(tmp_path, {f"bulk/f{i}.py": "x\n" for i in range(12)}, "mass rename")

    monkeypatch.setattr(miner, "MAX_FILES_PER_COMMIT", 5)
    file_sets, skipped = GitHistoryCrawler(str(tmp_path)).get_commit_file_sets()

    assert skipped == 1
    assert all(len(s) <= 5 for s in file_sets)
    assert not any(any(p.startswith("bulk/") for p in s) for s in file_sets)


def test_vendored_paths_never_enter_the_analysis(tmp_path):
    """They co-change because a tool wrote them, not because they depend on each other."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    for i in range(5):
        _commit(
            tmp_path,
            {"app.py": f"v{i}\n", "node_modules/pkg/index.js": f"v{i}\n", "helper.py": f"v{i}\n"},
            f"c{i}",
        )

    file_sets, _ = GitHistoryCrawler(str(tmp_path)).get_commit_file_sets()

    assert not any(any("node_modules" in p for p in s) for s in file_sets)


def test_a_single_file_commit_contributes_no_pair(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, {"only.py": "1\n"}, "solo")

    file_sets, skipped = GitHistoryCrawler(str(tmp_path)).get_commit_file_sets()

    assert file_sets == []
    assert skipped == 0


# ------------------------------------------------------------ window and shape


def test_the_window_excludes_older_commits(repo):
    """A pair that co-changed long ago is history, not structure."""
    future = datetime.now(timezone.utc) + timedelta(days=1)

    file_sets, _ = GitHistoryCrawler(str(repo)).get_commit_file_sets(since=future)

    assert file_sets == []


def test_a_missing_repo_degrades_rather_than_raising(tmp_path):
    file_sets, skipped = GitHistoryCrawler(str(tmp_path / "nope")).get_commit_file_sets()

    assert (file_sets, skipped) == ([], 0)


def test_the_edge_is_a_distinct_kind_never_a_call(repo):
    """Persisted beside ``calls`` edges, never merged into them.

    A co-change edge says two files moved together, not that one invokes the
    other. Folding the kinds together would make "who calls X" unanswerable.
    """
    pairs, _ = _pairs(repo)
    edge = pairs[0].as_edge()

    assert edge["kind"] == "co_change"
    assert edge["strength"] == 1.0
    assert {"source", "target", "co_changes"} <= set(edge)


def test_coupled_with_returns_only_pairs_involving_the_path(repo):
    pairs, _ = _pairs(repo)

    for pair in CoChangeAnalyzer().coupled_with("schema.py", pairs):
        assert "schema.py" in (pair.source, pair.target)


def test_the_analyzer_needs_no_git_at_all():
    """Takes file sets, not a repo — so the expensive walk stays a separate step."""
    sets = [{"a.py", "b.py"}, {"a.py", "b.py"}, {"a.py", "b.py"}]

    pairs = CoChangeAnalyzer().analyze(sets)

    assert pairs == [
        CoChangePair(source="a.py", target="b.py", co_changes=3, source_changes=3, target_changes=3, strength=1.0)
    ]
