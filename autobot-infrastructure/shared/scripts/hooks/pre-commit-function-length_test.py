# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-function-length (#620, GH#14151 fail-closed guard).

Issue #14151: see pre-commit-no-direct-redis_test.py's module docstring for
the shared background. This hook's opening banner already references an
unbound color variable under `set -u` (independently closing the
"missing lib/_common.sh" case pre-fix), so only the git-failure path is the
genuine, newly-fixed defect here.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-function-length"


def _test_git_env() -> dict[str, str]:
    """#15246: env for every git subprocess this suite spawns.

    Scrubbed rather than os.environ: the pre-push hook runs this suite with
    GIT_DIR pointing at the worktree it is pushing (every checkout here is
    one), and an unscrubbed `git init`/`git add`/`git commit` in a
    fixture then operates on THAT repository instead of tmp_path's. See
    autobot_shared/paths_test.py and #15246 for the reproduced incident.
    """
    env = {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    # A pre-push run exports pre-commit's own range. Carried into this suite's
    # throwaway repos it names a commit they do not have, and the hook, which
    # now scopes to that range, would fail on it (#16191). Tests set it themselves.
    return {name: value for name, value in env.items() if not name.startswith("PRE_COMMIT")}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=_test_git_env())


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _long_function_source(lines: int = 80) -> str:
    body = "\n".join(f"    x{i} = {i}" for i in range(lines))
    return f"def big():\n{body}\n"


def test_blocks_overlong_function(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "bad.py").write_text(_long_function_source(), encoding="utf-8")
    _git(repo, "add", "bad.py")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode != 0, result.stdout + result.stderr


def test_allows_short_function(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "ok.py").write_text("def small():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", "ok.py")
    result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
    assert result.returncode == 0, result.stdout + result.stderr


class TestFailsClosedOnGitFailure:
    """GH#14151: a corrupted `.git/index` used to be indistinguishable from
    "nothing staged" — reproduced with a genuinely staged violation.
    """

    def test_a_git_failure_does_not_report_clean(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        (repo / "bad.py").write_text(_long_function_source(), encoding="utf-8")
        _git(repo, "add", "bad.py")
        # Corrupt the index so git errors rather than returning an empty answer.
        (repo / ".git" / "index").write_text("garbage", encoding="utf-8")

        result = subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())
        assert result.returncode != 0, "a git failure was indistinguishable from 'no violation'"


class TestArgvModeIsNotSilentlyIgnored:
    """GH#14163: neither the get_staged_python_files() wrapper nor its call
    site in main() forwarded "$@" the way every sibling hook's
    get_staged_*_files() does (#6785 convention: no-args -> git diff
    --cached, argv -> explicit file list, so the same script works as a
    local hook AND a CI wrapper). A CI wrapper's explicit file list was
    silently discarded and the hook fell back to `git diff --cached`
    against whatever happened to be staged in that invocation's working
    tree instead -- a different bug shape than #13936 (argv accepted but
    the pattern filter silently bypassed); this one is argv accepted but
    discarded entirely. Reproduced by committing (nothing left staged)
    and then invoking the hook in argv mode with an explicit path to a
    file with a real violation, mirroring
    pre-commit-no-tracked-symlink_test.py's
    test_argv_mode_ignores_paths_not_passed.
    """

    def test_argv_mode_scopes_to_the_passed_file(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        (repo / "bad.py").write_text(_long_function_source(), encoding="utf-8")
        _git(repo, "add", "bad.py")
        _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed violation")
        # Nothing staged now -- git diff --cached is empty.

        result = subprocess.run(
            ["bash", str(HOOK_PATH), "bad.py"], cwd=repo, capture_output=True, text=True, env=_test_git_env()
        )
        assert result.returncode != 0, (
            "argv mode was ignored -- fell back to the (empty) staged set: "
            + result.stdout
            + result.stderr
        )


def _commit(repo: Path, message: str) -> None:
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-qam", message)


def _legacy_file(repo: Path) -> Path:
    """A committed file holding a >65-line legacy function and a short one beside it."""
    path = repo / "legacy.py"
    path.write_text(_long_function_source() + "\n\ndef small():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", "legacy.py")
    _commit(repo, "legacy")
    return path


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture drifted: {old!r} is not in {path.name}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _run_hook(repo: Path, *files: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOK_PATH), *files], cwd=repo, capture_output=True, text=True, env={**_test_git_env(), **env}
    )


class TestScopedToTheFunctionsAChangeTouches:
    """#16191: a legacy long function no longer holds every change to its file hostage.

    The evidence each acceptance criterion asks for, through the real hook: green
    for a one-line change beside the legacy function, red for an edit inside it,
    red for a new long function, and the same answers under the range a
    ``--from-ref`` run exports in place of a staged diff.
    """

    def test_a_one_line_change_beside_a_legacy_long_function_lands(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        path = _legacy_file(repo)
        _edit(path, "return 1", "return 2")
        _git(repo, "add", "legacy.py")

        result = _run_hook(repo)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "did not touch" in result.stdout, "the untouched legacy function must be reported, not silently passed"

    def test_editing_the_long_function_itself_still_fails(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        path = _legacy_file(repo)
        _edit(path, "    x5 = 5\n", "    x5 = 55\n")
        _git(repo, "add", "legacy.py")

        assert _run_hook(repo).returncode != 0

    def test_adding_a_new_long_function_still_fails(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        path = _legacy_file(repo)
        added = "\n\n" + _long_function_source().replace("def big", "def bigger")
        path.write_text(path.read_text(encoding="utf-8") + added, encoding="utf-8")
        _git(repo, "add", "legacy.py")

        assert _run_hook(repo).returncode != 0

    def test_a_pre_commit_range_scopes_the_same_way(self, tmp_path: Path) -> None:
        """enforce-precommit's ``--from-ref`` run stages nothing; the exported range stands in for it."""
        repo = _init_repo(tmp_path)
        path = _legacy_file(repo)
        base = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _edit(path, "return 1", "return 2")
        _commit(repo, "beside")

        assert _run_hook(repo, "legacy.py", PRE_COMMIT="1", PRE_COMMIT_FROM_REF=base).returncode == 0

        _edit(path, "    x5 = 5\n", "    x5 = 55\n")
        _commit(repo, "inside")

        assert _run_hook(repo, "legacy.py", PRE_COMMIT="1", PRE_COMMIT_FROM_REF=base).returncode != 0

    def test_a_range_left_in_a_shell_does_not_rescope_a_plain_run(self, tmp_path: Path) -> None:
        """Without pre-commit's own PRE_COMMIT=1 a stray range is ignored, and an unstaged file is judged whole."""
        repo = _init_repo(tmp_path)
        path = _legacy_file(repo)
        base = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _edit(path, "return 1", "return 2")
        _commit(repo, "beside")

        result = _run_hook(repo, "legacy.py", PRE_COMMIT_FROM_REF=base)

        assert result.returncode != 0 and "judged whole" in result.stdout, result.stdout + result.stderr

    def test_a_range_git_cannot_read_fails_closed(self, tmp_path: Path) -> None:
        """A git failure is not "this change touched nothing": the run must not report clean."""
        repo = _init_repo(tmp_path)
        _legacy_file(repo)

        result = _run_hook(repo, "legacy.py", PRE_COMMIT="1", PRE_COMMIT_FROM_REF="0" * 40)

        assert result.returncode != 0 and "refusing to report clean" in result.stdout, result.stdout + result.stderr

    def test_whole_file_mode_judges_a_legacy_function_the_change_did_not_touch(self, tmp_path: Path) -> None:
        """The enumeration mode, run directly as documented: the same staged change the scope passes is red here."""
        repo = _init_repo(tmp_path)
        path = _legacy_file(repo)
        _edit(path, "return 1", "return 2")
        _git(repo, "add", "legacy.py")
        checker = [sys.executable, str(HOOK_PATH.parent / "function_length_checker.py")]

        def _checker(*flags: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [*checker, *flags], cwd=repo, input="legacy.py\n", capture_output=True, text=True, env=_test_git_env()
            )

        assert _checker().returncode == 0, "scoped, the untouched legacy function is skipped"
        assert _checker("--whole-file").returncode != 0, "--whole-file must judge it anyway"
