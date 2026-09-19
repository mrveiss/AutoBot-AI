# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Local pre-commit dispatches to the pre-commit framework (#16923).

``.pre-commit-config.yaml`` declares black/isort/flake8/autoflake/mypy and this
repo's own local guards, but nothing ran any of them locally: the ``pre-commit``
hook slot held only the Target Branch Guard, a self-contained script with no
pre-commit-framework dispatch at all. The first thing that ever ran black was
CI, one full round-trip after every formatting mistake.

Uses a hand-rolled local hook (``fake-formatter``) instead of the real
black/isort in the fixture's own ``.pre-commit-config.yaml`` — proving the
DISPATCH mechanism (this hook detects staged files and calls
``pre-commit run``, and a hook that modifies a file blocks the commit) does not
require network access to a real formatter's own pre-commit environment,
which a fresh CI runner is not guaranteed to have cached.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_REPO_ROOT = repo_root()
_INSTALLER = _REPO_ROOT / "scripts" / "install-git-hooks.sh"
_TEMPLATE = _REPO_ROOT / "tools" / "git-hooks" / "pre-commit"

# requirements-ci/security.txt declares pre-commit==4.6.2, installed for
# every python-suite run -- but a dev environment or a future CI change
# could lack it. The hook itself skips gracefully (exits 0, does not block)
# when this is absent, which would make every positive test below pass
# vacuously (nothing corrected because nothing ran) rather than failing
# loudly. Skip explicitly instead, with a reason, matching MEASUREMENT_
# DISCIPLINE.md's nothing-found-vs-did-not-look distinction.
if shutil.which("pre-commit") is None:  # pragma: no cover - exercised only when absent
    pytest.skip(
        "'pre-commit' binary not on PATH -- cannot exercise the dispatch this module tests", allow_module_level=True
    )

_FIXTURE_CONFIG = """\
repos:
  - repo: local
    hooks:
      - id: fake-formatter
        name: fake formatter (test fixture)
        entry: python3 -c "import sys,pathlib; p=pathlib.Path(sys.argv[1]); p.write_text(p.read_text().replace('BADFORMAT', 'GOODFORMAT'))"
        language: system
        files: \\.py$
        stages: [pre-commit]
"""


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """#15246: env scrubbed -- an inherited GIT_DIR would point these calls at
    the real repository instead of the throwaway one under tmp_path."""
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check, env=scrubbed_git_env())


def _seed_repo(tmp_path: Path, *, name: str = "main") -> Path:
    """A throwaway repo carrying the real installer, the real pre-commit
    template, and a minimal, network-free .pre-commit-config.yaml."""
    repo = tmp_path / name
    (repo / "tools" / "git-hooks").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    (repo / "tools" / "git-hooks" / "pre-commit").write_bytes(_TEMPLATE.read_bytes())
    (repo / "scripts" / "install-git-hooks.sh").write_bytes(_INSTALLER.read_bytes())
    (repo / ".pre-commit-config.yaml").write_text(_FIXTURE_CONFIG, encoding="utf-8")
    _git(repo.parent, "init", "--quiet", "--initial-branch=main", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "seed")
    _git(repo, "checkout", "--quiet", "-b", "issue-1")
    return repo


def _install_from(cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["bash", str(cwd / "scripts" / "install-git-hooks.sh")], cwd=cwd, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture(name="seeded")
def _seeded(tmp_path: Path) -> Path:
    assert _INSTALLER.is_file(), f"{_INSTALLER} is missing — this guard has no subject"
    assert _TEMPLATE.is_file(), f"{_TEMPLATE} is missing"
    return _seed_repo(tmp_path)


# ---------------------------------------------------------------------------
# AC1 + AC3: an unformatted .py file is corrected locally, however it was
# created (here, via plain Path.write_text — never touched by an editor tool,
# the shape #16923 names as currently uncovered).
# ---------------------------------------------------------------------------


def test_a_badly_formatted_staged_file_is_corrected_and_the_commit_refused(seeded: Path) -> None:
    _install_from(seeded)
    (seeded / "bad.py").write_text("BADFORMAT = 1\n", encoding="utf-8")
    _git(seeded, "add", "bad.py")

    result = _git(seeded, "commit", "-m", "test", check=False)

    assert result.returncode != 0, "the commit should have been refused pending the formatter's fix"
    assert (seeded / "bad.py").read_text(
        encoding="utf-8"
    ) == "GOODFORMAT = 1\n", "the formatter dispatch did not correct the staged file — #16923 is not fixed"


def test_re_adding_the_corrected_file_lets_the_commit_through(seeded: Path) -> None:
    _install_from(seeded)
    (seeded / "bad.py").write_text("BADFORMAT = 1\n", encoding="utf-8")
    _git(seeded, "add", "bad.py")
    _git(seeded, "commit", "-m", "test", check=False)  # refused; file corrected on disk

    _git(seeded, "add", "bad.py")
    result = _git(seeded, "commit", "-m", "test", check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    log = _git(seeded, "log", "--oneline", "-1").stdout
    assert "test" in log


def test_an_already_well_formatted_commit_is_not_blocked(seeded: Path) -> None:
    """No unnecessary friction: a file the fixture hook would not touch commits cleanly."""
    _install_from(seeded)
    (seeded / "good.py").write_text("GOODFORMAT = 1\n", encoding="utf-8")
    _git(seeded, "add", "good.py")

    result = _git(seeded, "commit", "-m", "test", check=False)
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# AC2: the Target Branch Guard still fires, from the same commit attempt,
# BEFORE the formatter dispatch ever runs.
# ---------------------------------------------------------------------------


def test_the_target_branch_guard_still_blocks_protected_branches(seeded: Path) -> None:
    _install_from(seeded)
    _git(seeded, "checkout", "--quiet", "-b", "release")
    (seeded / "bad.py").write_text("BADFORMAT = 1\n", encoding="utf-8")
    _git(seeded, "add", "bad.py")

    result = _git(seeded, "commit", "-m", "test", check=False)

    assert result.returncode != 0
    assert "COMMIT BLOCKED" in result.stderr, result.stdout + result.stderr
    assert "release" in result.stderr
    assert (seeded / "bad.py").read_text(
        encoding="utf-8"
    ) == "BADFORMAT = 1\n", "the formatter dispatch ran even though the branch guard should have exited first"


def test_the_target_branch_guard_still_blocks_master(seeded: Path) -> None:
    _install_from(seeded)
    _git(seeded, "checkout", "--quiet", "-b", "master")
    result = _git(seeded, "commit", "--allow-empty", "-m", "test", check=False)
    assert result.returncode != 0
    assert "COMMIT BLOCKED" in result.stderr


# ---------------------------------------------------------------------------
# AC4: produced on a fresh clone (plain _seed_repo, above) AND a fresh worktree.
# ---------------------------------------------------------------------------


def test_the_dispatch_also_works_when_installed_from_a_worktree(seeded: Path, tmp_path: Path) -> None:
    worktree = tmp_path / "linked-wt"
    _git(seeded, "worktree", "add", "--quiet", "-b", "issue-2", str(worktree))

    _install_from(worktree)
    (worktree / "bad.py").write_text("BADFORMAT = 1\n", encoding="utf-8")
    _git(worktree, "add", "bad.py")
    result = _git(worktree, "commit", "-m", "test", check=False)

    assert result.returncode != 0
    assert (worktree / "bad.py").read_text(encoding="utf-8") == "GOODFORMAT = 1\n"


# ---------------------------------------------------------------------------
# AC5: negative control. The positive tests above must not be vacuous — this
# proves that against the PRE-#16923 hook (branch guard only, no dispatch),
# the same scenario stays uncorrected. If someone strips the dispatch back
# out of tools/git-hooks/pre-commit, this test starts failing.
# ---------------------------------------------------------------------------


def test_negative_control_the_pre_16923_hook_would_not_have_caught_this(tmp_path: Path) -> None:
    """Reconstructs the branch-guard-only hook (no formatter dispatch) and
    confirms the exact scenario test_a_badly_formatted_staged_file_is_corrected
    ... depends on would NOT have been caught by it -- so that test is not
    passing for an unrelated reason."""
    guard_only = _TEMPLATE.read_text(encoding="utf-8").split("# Formatter dispatch (#16923)")[0]
    guard_only = guard_only.replace(
        "        # Falls through to the formatter dispatch below (#16923) rather than\n"
        "        # exiting here -- the only change to this arm versus the sync source.\n",
        "        exit 0\n",
    )
    assert (
        "pre-commit run" not in guard_only
    ), "the split point did not remove the dispatch — this negative control would pass vacuously"

    repo = tmp_path / "pre16923"
    (repo / "tools" / "git-hooks").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    (repo / "tools" / "git-hooks" / "pre-commit").write_text(guard_only, encoding="utf-8")
    (repo / "scripts" / "install-git-hooks.sh").write_bytes(_INSTALLER.read_bytes())
    (repo / ".pre-commit-config.yaml").write_text(_FIXTURE_CONFIG, encoding="utf-8")
    _git(repo.parent, "init", "--quiet", "--initial-branch=main", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", "seed")
    _git(repo, "checkout", "--quiet", "-b", "issue-1")

    _install_from(repo)
    (repo / "bad.py").write_text("BADFORMAT = 1\n", encoding="utf-8")
    _git(repo, "add", "bad.py")
    result = _git(repo, "commit", "-m", "test", check=False)

    assert result.returncode == 0, "the branch-guard-only hook should not have blocked this commit at all"
    assert (repo / "bad.py").read_text(encoding="utf-8") == "BADFORMAT = 1\n", (
        "the pre-#16923 hook corrected the file — the negative control's reconstruction is wrong, " "not the fix"
    )


# ---------------------------------------------------------------------------
# AC6: legitimate hook-less automation commits are unaffected. Named actor:
# github-actions[bot] via .github/workflows/auto-fix-generated-types.yml,
# which commits inside a fresh Actions checkout that never runs
# scripts/install-git-hooks.sh -- there is no hooks-dir entry to bypass.
# ---------------------------------------------------------------------------


def test_the_bot_commit_workflow_never_installs_local_hooks() -> None:
    workflow = _REPO_ROOT / ".github" / "workflows" / "auto-fix-generated-types.yml"
    assert workflow.is_file(), f"{workflow} is missing — the named exemption's subject vanished"
    text = workflow.read_text(encoding="utf-8")
    assert 'user.name "github-actions[bot]"' in text, "this is not the workflow #16923's exemption names"
    assert "install-git-hooks.sh" not in text, (
        "this workflow now installs local hooks -- github-actions[bot]'s commit is no longer "
        "hook-less by construction, and the #16923 exemption claim is stale"
    )
