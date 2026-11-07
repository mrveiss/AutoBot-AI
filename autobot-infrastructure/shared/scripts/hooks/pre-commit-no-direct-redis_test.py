# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-direct-redis (#1086, GH#14151 fail-closed guard).

Issue #14151: 13 of the 14 hooks in this directory shared the
`set -uo pipefail` (no `-e`) + unguarded `source lib/_common.sh` shape
found and fixed in #14150 for two other hooks — a broken dependency or a
`git diff --cached` failure degraded to "nothing staged" and the hook
reported clean. This hook's own get_staged_files()-based file discovery had
no other git touchpoint, so a git failure there was invisible to `set -e`
alone: get_staged_files()'s own former `|| true` masked it before the
caller ever saw a non-zero status. Fixed in lib/_common.sh directly.

This hook's opening banner already references an unbound color variable
under `set -u`, which independently closed the "missing lib/_common.sh"
case even before this fix — only the git-failure path is a genuine,
newly-fixed defect here, so that is the only reproduction below (see
pre-commit-no-tag-pinned-action_test.py for a hook where BOTH reproduce,
since it has no such banner).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from autobot_shared.isolated_git import isolated_git_env

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-direct-redis"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=isolated_git_env())


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


_BAD = "import redis\nr = redis.Redis()\n"


def _stage(repo: Path, rel: str, text: str) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text, encoding="utf-8")
    _git(repo, "add", rel)


def _run_hook(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=isolated_git_env())


def test_blocks_direct_redis_instantiation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "scripts/bad.py", _BAD)
    result = _run_hook(repo)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "NEW scripts/bad.py" in result.stdout


def test_blocks_the_constructors_the_old_regex_missed(tmp_path: Path) -> None:
    """#18553: `from_url` and a pool were invisible to the regex hook, and `autobot-infrastructure/` was skipped."""
    repo = _init_repo(tmp_path)
    _stage(repo, "autobot-infrastructure/x/probe.py", "import redis\nc = redis.from_url('u')\n")
    result = _run_hook(repo)
    assert result.returncode != 0, result.stdout + result.stderr


def test_noqa_redis_is_no_longer_an_opt_out(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "scripts/bad.py", "import redis\nr = redis.Redis()  # noqa: redis\n")
    assert _run_hook(repo).returncode != 0


def test_a_shell_script_embedding_a_constructor_is_read(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "scripts/probe.sh", "python3 -c 'import redis; redis.Redis()'\n")
    assert _run_hook(repo).returncode != 0


def test_a_mention_in_a_docstring_or_a_test_file_is_not_a_site(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "scripts/doc.py", '"""redis.Redis() is forbidden."""\n')
    _stage(repo, "scripts/a_test.py", _BAD)
    result = _run_hook(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_allows_clean_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "scripts/ok.py", "x = 1\n")
    result = _run_hook(repo)
    assert result.returncode == 0, result.stdout + result.stderr


class TestFailsClosedOnGitFailure:
    """GH#14151: a corrupted `.git/index` used to be indistinguishable from
    "nothing staged" — reproduced with a genuinely staged violation.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _stage(repo, "scripts/bad.py", _BAD)
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = _run_hook(repo)
        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"
