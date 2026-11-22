# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for tools/lint/_check_harness.py (#14896)."""

from __future__ import annotations

import logging
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _check_harness as harness  # noqa: E402
from _scan_helpers import EmptyEnumeration, GitEnumerationFailed, tracked_modes  # noqa: E402

from autobot_shared.isolated_git import isolated_git_env  # noqa: E402

_NAME = "probe"


def _git(repo: Path, *args: str) -> None:
    env = isolated_git_env()
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)  # nosec B603 B607


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    _git(tmp_path, "init", "-q")
    (tmp_path / "tools" / "lint").mkdir(parents=True)
    anchor = tmp_path / "tools" / "lint" / "x.py"
    anchor.write_text("", encoding="utf-8")
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    _git(tmp_path, "add", "-A")
    return tmp_path


def _ok(reached: int, findings: list[str]):
    return lambda argv, root: (reached, findings)


def test_exit_codes_are_the_documented_triple() -> None:
    assert (harness.EXIT_CLEAN, harness.EXIT_FOUND, harness.EXIT_VACUOUS) == (0, 1, 2)
    assert issubclass(harness.VacuousScan, RuntimeError)


def test_format_finding_matches_the_checkers_shape() -> None:
    assert harness.format_finding("a/b.py", 7, "bad thing") == "a/b.py:7: bad thing"


def test_the_cwd_policy_is_off_and_isolated(repo: Path) -> None:
    assert harness.REQUIRE_CWD_AT_ROOT is False
    assert harness.cwd_policy_ok(repo) is True


@pytest.mark.parametrize(
    "boom",
    [
        harness.VacuousScan("v"),
        EmptyEnumeration("e"),
        GitEnumerationFailed("f"),
        harness.GitRepoRootUnavailable("g"),
    ],
)
def test_a_scan_that_raises_is_vacuous(boom: Exception, repo: Path) -> None:
    def scan(argv, root):
        raise boom

    assert harness.run_check(_NAME, scan, [], root=repo) == 2


@pytest.mark.parametrize("bug", [RuntimeError("r"), RecursionError("deep"), NotImplementedError("todo")])
def test_a_checker_bug_propagates_instead_of_reading_as_vacuous(bug: Exception, repo: Path) -> None:
    def scan(argv, root):
        raise bug

    with pytest.raises(type(bug)):
        harness.run_check(_NAME, scan, [], root=repo)


def test_nothing_reached_in_a_full_repo_sweep_is_vacuous(repo: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger=_NAME):
        assert harness.run_check(_NAME, _ok(0, []), [], root=repo) == 2
    assert "nothing was scanned" in caplog.text


def test_nothing_reached_from_an_explicit_argv_is_clean(repo: Path) -> None:
    assert harness.run_check(_NAME, _ok(0, []), ["f.py"], root=repo) == 0


def test_a_floor_applies_to_a_full_repo_sweep_only(repo: Path) -> None:
    assert harness.run_check(_NAME, _ok(3, []), [], root=repo, floor=10) == 2
    assert harness.run_check(_NAME, _ok(3, []), ["f.py"], root=repo, floor=10) == 0
    assert harness.run_check(_NAME, _ok(10, []), [], root=repo, floor=10) == 0


def test_flags_alone_are_still_a_full_repo_sweep_when_the_checker_says_so(repo: Path) -> None:
    flags_only = ["--changed-lines-only"]
    # the bare default reads a non-empty argv as scoped and skips the floor ...
    assert harness.run_check(_NAME, _ok(3, []), flags_only, root=repo, floor=10) == 0
    # ... a checker that keys off its parsed file list enforces it.
    sweep = lambda argv: not [a for a in argv if not a.startswith("--")]  # noqa: E731
    assert harness.run_check(_NAME, _ok(3, []), flags_only, root=repo, floor=10, full_repo_of=sweep) == 2
    assert harness.run_check(_NAME, _ok(0, []), flags_only, root=repo, full_repo_of=sweep) == 2
    assert harness.run_check(_NAME, _ok(3, []), [*flags_only, "f.py"], root=repo, floor=10, full_repo_of=sweep) == 0


def test_findings_are_logged_and_exit_one(repo: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger=_NAME):
        rc = harness.run_check(_NAME, _ok(5, ["a.py:1: bad"]), [], root=repo, summary=lambda n: f"{n} found")
    assert rc == 1
    assert "a.py:1: bad" in caplog.text and "1 found" in caplog.text


def test_resolve_root_names_the_toplevel_two_levels_up(repo: Path) -> None:
    assert harness.resolve_root(repo / "tools" / "lint" / "x.py") == repo.resolve()


def test_resolve_root_refuses_a_non_toplevel(repo: Path) -> None:
    nested = repo / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (nested / "x.py").write_text("", encoding="utf-8")
    with pytest.raises(harness.VacuousScan):
        harness.resolve_root(nested / "x.py")  # parents[2] is repo/a, inside the checkout


def test_resolve_root_refuses_a_non_git_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    (tmp_path / "tools" / "lint").mkdir(parents=True)
    with pytest.raises(harness.VacuousScan):
        harness.resolve_root(tmp_path / "tools" / "lint" / "x.py")


def test_tracked_modes_returns_mode_and_path(repo: Path) -> None:
    assert ("100755", "run.sh") in tracked_modes(repo)
    assert tracked_modes(repo, "*.sh") == [("100755", "run.sh")]


def test_tracked_modes_raises_on_git_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    with pytest.raises(GitEnumerationFailed, match="failed"):
        tracked_modes(tmp_path)


def test_tracked_modes_raises_on_an_empty_listing(repo: Path) -> None:
    with pytest.raises(EmptyEnumeration):
        tracked_modes(repo, "*.no-such-suffix")


def test_tracked_modes_ignores_an_inherited_git_dir(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_DIR", str(repo / "nowhere"))
    assert tracked_modes(repo, "*.sh")
