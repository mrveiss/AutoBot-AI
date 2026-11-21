# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The trailer gate scans only the PR's own commits, as GitHub counts them (#22001).

PR #21833 failed "scanned 11 commits but GitHub reports 7" on a PR with 7 commits. The
event's base was the current main tip, so the base was not stale: in a depth-100 clone a
head that had merged OLD main reaches those commits through its own history, while the
base side is cut off, so they were counted as the PR's own. These tests build temp repos
(an origin plus a shallow clone, as `actions/checkout` produces) and run
`scripts/ci/trailer_gate_range.sh`: an over-count is deepened away, a truncated scan
still fails, and the two failures say which one it is.
"""

from __future__ import annotations

import subprocess  # nosec B404  # fixed argv, no shell
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import git, isolated_git_env, make_repo

SCRIPT = repo_root() / "scripts" / "ci" / "trailer_gate_range.sh"
_SHALLOW_DEPTH = "5"
_DEEPEN_START = "50"


def _git(cwd: Path, *args: str) -> str:
    return git(cwd, *args).stdout.strip()


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


def _origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin"
    make_repo(origin, default_branch="main")
    _git(origin, "config", "uploadpack.allowAnySHA1InWant", "true")
    return origin


def _pr_with_merged_main(origin: Path, *, main_after: int) -> tuple[str, str, str]:
    """main m0..m29; a PR forks at m2, merges m10, and has 3 own commits + the merge (4)."""
    shas = [_commit(origin, f"m{i}") for i in range(30)]
    _git(origin, "checkout", "-q", "-b", "pr", shas[2])
    _commit(origin, "p1")
    _git(origin, "merge", "-q", "--no-ff", "-m", "merge main", shas[10])
    _commit(origin, "p2")
    head = _commit(origin, "p3")
    _git(origin, "checkout", "-q", "main")
    for i in range(main_after):
        _commit(origin, f"later{i}")
    return head, shas[29], shas[10]


def _own_commits(origin: Path, head: str) -> int:
    return int(_git(origin, "rev-list", "--count", head, "--not", "main"))


def _clone(tmp_path: Path, origin: Path, head: str, depth: str, *extra: str) -> Path:
    clone = tmp_path / "clone"
    make_repo(clone)
    _git(clone, "remote", "add", "origin", origin.as_uri())
    _git(clone, "fetch", "-q", "--no-tags", f"--depth={depth}", "origin", head, *extra)
    return clone


def _run(clone: Path, tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
    out = tmp_path / "gh_output"
    out.write_text("", encoding="utf-8")
    full = {
        **isolated_git_env(),
        "GITHUB_OUTPUT": str(out),
        "TRAILER_GATE_DEEPEN_START": _DEEPEN_START,
        "RELEASE_BASE_SHA": "",
        "RELEASE_NEW_COMMITS": "",
        **env,
    }
    return subprocess.run(["bash", str(SCRIPT)], cwd=clone, env=full, capture_output=True, text=True)  # nosec B603 B607


def _base_output(tmp_path: Path) -> str:
    line = (tmp_path / "gh_output").read_text(encoding="utf-8").strip()
    assert line.startswith("base-sha="), line
    return line.split("=", 1)[1]


def test_old_range_overcounts_a_head_that_merged_old_main(tmp_path: Path) -> None:
    """The failure #22001 reports: event base..head in a shallow clone is not the PR's count."""
    origin = _origin(tmp_path)
    head, base, _ = _pr_with_merged_main(origin, main_after=0)
    clone = _clone(tmp_path, origin, head, _SHALLOW_DEPTH)
    _git(clone, "fetch", "-q", "--no-tags", "--depth=1", "origin", base)
    old = int(_git(clone, "rev-list", "--count", f"{base}..{head}"))
    assert old > _own_commits(origin, head) == 4


def test_overcount_from_old_main_is_deepened_and_passes(tmp_path: Path) -> None:
    origin = _origin(tmp_path)
    head, base, _ = _pr_with_merged_main(origin, main_after=0)
    clone = _clone(tmp_path, origin, head, _SHALLOW_DEPTH)
    done = _run(clone, tmp_path, HEAD_SHA=head, BASE_SHA=base, BASE_REF="main", EXPECTED_COMMITS="4")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(clone, "rev-list", "--count", f"{_base_output(tmp_path)}..{head}") == "4"


def test_stale_event_base_uses_the_current_base_tip(tmp_path: Path) -> None:
    """main moved after the event; the head merged a main commit newer than the event's base."""
    origin = _origin(tmp_path)
    head, _, merged = _pr_with_merged_main(origin, main_after=3)
    stale = _git(origin, "rev-parse", f"{merged}~5")
    tip = _git(origin, "rev-parse", "main")
    clone = _clone(tmp_path, origin, head, _SHALLOW_DEPTH)
    done = _run(clone, tmp_path, HEAD_SHA=head, BASE_SHA=stale, BASE_REF="main", EXPECTED_COMMITS="4")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _base_output(tmp_path) == tip


def test_truncated_scan_still_fails_and_says_shallow(tmp_path: Path) -> None:
    origin = _origin(tmp_path)
    base = _commit(origin, "base")
    _git(origin, "checkout", "-q", "-b", "pr")
    for i in range(10):
        head = _commit(origin, f"own{i}")
    _git(origin, "checkout", "-q", "main")
    clone = _clone(tmp_path, origin, head, _SHALLOW_DEPTH)
    done = _run(clone, tmp_path, HEAD_SHA=head, BASE_SHA=base, BASE_REF="main", EXPECTED_COMMITS="10")
    assert done.returncode == 1
    assert "too shallow" in done.stdout
    assert "base mismatch" not in done.stdout


def test_extra_commits_with_full_history_say_base_mismatch(tmp_path: Path) -> None:
    origin = _origin(tmp_path)
    head, base, _ = _pr_with_merged_main(origin, main_after=0)
    clone = _clone(tmp_path, origin, head, "1000", base)
    done = _run(clone, tmp_path, HEAD_SHA=head, BASE_SHA=base, EXPECTED_COMMITS="1")
    assert done.returncode == 1
    assert "base mismatch" in done.stdout
    assert "too shallow" not in done.stdout


def test_normal_pr_passes_and_merge_group_has_no_expected_count(tmp_path: Path) -> None:
    origin = _origin(tmp_path)
    base = _commit(origin, "base")
    _git(origin, "checkout", "-q", "-b", "pr")
    head = _commit(origin, "own")
    _git(origin, "checkout", "-q", "main")
    clone = _clone(tmp_path, origin, head, _SHALLOW_DEPTH)
    pull = _run(clone, tmp_path, HEAD_SHA=head, BASE_SHA=base, BASE_REF="main", EXPECTED_COMMITS="1")
    assert pull.returncode == 0, pull.stdout + pull.stderr
    group = _run(clone, tmp_path, HEAD_SHA=head, BASE_SHA=base, BASE_REF="", EXPECTED_COMMITS="")
    assert group.returncode == 0 and _base_output(tmp_path) == base


def test_release_promotion_base_is_used_as_given(tmp_path: Path) -> None:
    origin = _origin(tmp_path)
    head, _, merged = _pr_with_merged_main(origin, main_after=0)
    main_tip = _git(origin, "rev-parse", "main")
    clone = _clone(tmp_path, origin, head, "1000", main_tip)
    done = _run(
        clone,
        tmp_path,
        HEAD_SHA=head,
        BASE_SHA="0" * 40,
        BASE_REF="release",
        EXPECTED_COMMITS="999",
        RELEASE_BASE_SHA=main_tip,
        RELEASE_NEW_COMMITS="4",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert _base_output(tmp_path) == _git(origin, "rev-parse", "main")


@pytest.mark.parametrize("name", ["no_commit_trailers_fetch_depth_test", "no_commit_trailers_anchor_test"])
def test_neighbouring_suites_exist(name: str) -> None:
    assert (repo_root() / "repo_tests" / f"{name}.py").exists()
