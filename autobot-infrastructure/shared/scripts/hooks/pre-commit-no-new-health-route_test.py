# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-new-health-route (#3333, GH#14151 fail-closed
guard).

Issue #14151: see pre-commit-no-direct-redis_test.py's module docstring for
the shared background. This hook doesn't use get_staged_files() — it pipes
`git diff --cached -U0` straight into an awk collector, and the result is
captured with a bare top-level `violations=$(collect_violations)`, so
`set -e` alone (no lib/_common.sh change needed) is enough to make a git
failure abort. Its opening banner already references an unbound color
variable under `set -u`, which independently closed the "missing
lib/_common.sh" case pre-fix — only the git-failure path is the genuine,
newly-fixed defect here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-new-health-route"


def _test_git_env() -> dict[str, str]:
    """#15246: env for every git subprocess this suite spawns.

    Scrubbed rather than os.environ: the pre-push hook runs this suite with
    GIT_DIR pointing at the worktree it is pushing (every checkout here is
    one), and an unscrubbed `git init`/`git add`/`git commit` in a
    fixture then operates on THAT repository instead of tmp_path's. See
    autobot_shared/paths_test.py and #15246 for the reproduced incident.
    """
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=_test_git_env())


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _stage_health_route(repo: Path) -> None:
    f = repo / "autobot-backend" / "api" / "foo.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text('@router.get("/health")\nasync def h():\n    return {}\n', encoding="utf-8")
    _git(repo, "add", "autobot-backend/api/foo.py")


def test_blocks_new_health_route(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage_health_route(repo)
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode != 0, result.stdout + result.stderr


def test_allows_ordinary_route(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    f = repo / "autobot-backend" / "api" / "foo.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("def h():\n    return {}\n", encoding="utf-8")
    _git(repo, "add", "autobot-backend/api/foo.py")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode == 0, result.stdout + result.stderr


class TestFailsClosedOnGitFailure:
    """GH#14151: a corrupted `.git/index` used to be indistinguishable from
    "no new /health routes" — reproduced with a genuinely staged violation.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _stage_health_route(repo)
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"


def _stage(repo: Path, body: str) -> subprocess.CompletedProcess:
    """Stage *body* as an API module and run the hook against it."""
    f = repo / "autobot-backend" / "api" / "foo.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")
    _git(repo, "add", "autobot-backend/api/foo.py")
    return subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())


def test_a_comment_warning_against_the_pattern_is_not_a_violation(tmp_path: Path) -> None:
    """The matcher was unanchored, so prose containing the pattern was reported (#16011).

    The sentence most likely to contain `@router.get("/health")` is one WARNING
    against it, so the guard punished documenting the rule it enforces. This is
    a plain comment, not even a docstring — strictly easier to trigger than the
    docstring case that started the enumeration.
    """
    result = _stage(tmp_path_repo(tmp_path), '# Never add @router.get("/health") - use the shared health router\n')
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_real_decorator_is_still_a_violation(tmp_path: Path) -> None:
    """The contrast. Without it, anchoring is satisfied by matching nothing.

    A guard that reports no violations and a guard that cannot report one
    produce the same clean run, which is the failure this whole family is about.
    """
    result = _stage(tmp_path_repo(tmp_path), '@router.get("/health")\nasync def h():\n    return {}\n')
    assert result.returncode != 0, result.stdout + result.stderr


def test_an_indented_decorator_is_still_a_violation(tmp_path: Path) -> None:
    """The anchor allows leading whitespace — a decorator inside a class body."""
    body = 'class R:\n    @router.get("/health")\n    async def h(self):\n        return {}\n'
    assert _stage(tmp_path_repo(tmp_path), body).returncode != 0


def test_a_docstring_mention_is_not_a_violation(tmp_path: Path) -> None:
    """A one-line docstring mentioning the pattern starts with a quote, not `@`."""
    result = _stage(tmp_path_repo(tmp_path), '"""Do not add @router.get("/health") here."""\n')
    assert result.returncode == 0, result.stdout + result.stderr


def tmp_path_repo(tmp_path: Path) -> Path:
    """A fresh repository per test, since each stages the same path."""
    return _init_repo(tmp_path)
