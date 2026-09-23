# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The commit-msg hook strips trailers and enforces the subject convention (#17029).

The convention in CLAUDE.md, `<type>(scope): <description> (#NNNN)`, was enforced
nowhere. `scripts/lint-conventions.sh --commit-msg` implements it, but the
pre-commit framework's commit-msg stage is not installed by default, and the hook
that did sit in the shared hooks dir was a hand-installed file that only stripped
trailers. `tools/git-hooks/commit-msg` is now tracked, installed by
`scripts/install-git-hooks.sh`, and runs that one implementation.

Every test runs the real hook and the real lint script in a throwaway repository.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_ROOT = repo_root()
_HOOK = _ROOT / "tools" / "git-hooks" / "commit-msg"
_LINT_SCRIPT = "scripts/lint-conventions.sh"

# #15473: derived, not listed. The hardcoded tuple went stale the moment the
# script gained a dependency it did not name -- lib/commit-subject.ere, the
# shared commit-subject rule -- and the fixture then built a repo that was not a
# checkout. The script correctly refused to run against it ("FATAL cannot read
# the commit-subject rule"), and six tests read that refusal as the hook being
# broken. scripts/lint_conventions_test.py already derives its fixture this way
# for exactly this reason (#15245); this file is the second fixture with the
# same shape and did not.
_LIB_REF = re.compile(r"lib/([A-Za-z0-9_.-]+\.(?:sh|ere))")


def _lint_files() -> tuple[str, ...]:
    src = (_ROOT / _LINT_SCRIPT).read_text(encoding="utf-8")
    names = sorted(set(_LIB_REF.findall(src)))
    assert names, f"{_LINT_SCRIPT} reads nothing from scripts/lib/ -- the pattern has drifted"
    rels = (_LINT_SCRIPT, *(f"scripts/lib/{n}" for n in names))
    missing = [r for r in rels if not (_ROOT / r).is_file()]
    assert not missing, f"{_LINT_SCRIPT} reads files that do not exist: {missing}"
    return rels


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, env=scrubbed_git_env())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway repo carrying the real lint script, its libraries and the hook."""
    repo = tmp_path / "repo"
    for rel in _lint_files():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_ROOT / rel, repo / rel)
    _git(tmp_path, "init", "--quiet", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    return repo


def _run_hook(repo: Path, message: str) -> tuple[subprocess.CompletedProcess, str]:
    msg = repo / "MSG"
    msg.write_text(message, encoding="utf-8")
    result = subprocess.run(
        ["bash", str(_HOOK), str(msg)], cwd=repo, capture_output=True, text=True, env=scrubbed_git_env()
    )
    return result, msg.read_text(encoding="utf-8")


def test_a_conventional_subject_with_an_issue_reference_passes(repo: Path) -> None:
    assert _run_hook(repo, "fix(hooks): enforce the subject (#17029)\n")[0].returncode == 0


@pytest.mark.parametrize(
    "subject",
    ["fix(hooks): enforce the subject", "Enforce the subject (#17029)"],
    ids=["no issue reference", "no type"],
)
def test_a_subject_off_the_convention_is_rejected(repo: Path, subject: str) -> None:
    result, _ = _run_hook(repo, subject + "\n")
    assert result.returncode != 0, result.stdout
    assert "FAIL" in result.stdout


@pytest.mark.parametrize("subject", ["Merge branch 'main' into feature", 'Revert "fix(x): y (#1234)"'])
def test_the_lint_scripts_own_exemptions_apply(repo: Path, subject: str) -> None:
    assert _run_hook(repo, subject + "\n")[0].returncode == 0


def test_trailers_are_still_stripped(repo: Path) -> None:
    message = (
        "fix(hooks): enforce the subject (#17029)\n\nbody\n\n"
        "Co-authored-by: Someone <s@example.com>\n🤖 Generated with [Claude Code](https://claude.com)\n"
    )
    result, kept = _run_hook(repo, message)
    assert result.returncode == 0
    assert "Co-authored-by" not in kept and "Generated with" not in kept
    assert kept.startswith("fix(hooks): enforce the subject (#17029)\n\nbody")


def test_a_checkout_without_the_lint_script_is_not_blocked(repo: Path) -> None:
    (repo / "scripts" / "lint-conventions.sh").unlink()
    result, _ = _run_hook(repo, "anything goes here\n")
    assert result.returncode == 0
    assert "not checked" in result.stderr


def test_a_real_commit_is_refused_then_accepted(repo: Path) -> None:
    """End to end: git itself runs the installed hook and aborts on a bad subject."""
    hooks = repo / ".git" / "hooks"
    shutil.copy2(_HOOK, hooks / "commit-msg")
    (hooks / "commit-msg").chmod(0o755)

    refused = _git(repo, "commit", "--allow-empty", "-m", "fix(hooks): no reference")
    accepted = _git(repo, "commit", "--allow-empty", "-m", "fix(hooks): with reference (#17029)")

    assert refused.returncode != 0, refused.stdout + refused.stderr
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
