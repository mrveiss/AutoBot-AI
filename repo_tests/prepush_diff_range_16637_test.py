# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Phase 0c's changed-file range must be the PR's own diff, not remote_sha..local_sha (#16637).

The existing-remote-branch path used a raw two-dot range,
``${remote_sha}..${local_sha}``, unconditionally -- correct only for a first
push, where ``remote_sha`` really is the branch's entire history (0000...).
After a ``git rebase origin/main`` + force-push, ``remote_sha`` is the
branch's *old, pre-rebase* tip, so that range spans everything `origin/main`
changed since the branch's last push, on top of the branch's own commits --
not just the branch's own diff. #16413 hit this directly: an inflated range
pulled in an unrelated `initialization/lifespan_test.py`, which then failed
on the interpreter-floor mismatch tracked by #16510.

These tests build a real throwaway repo and exercise the real merge-base
computation and `git diff --name-only`, not just grep the script's text --
the #15985 test file's docstring gives the reason: a defect in what happens
at runtime is invisible to a check of what the script merely says.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_HOOK = repo_root() / "tools" / "git-hooks" / "pre-push"

_HARNESS = """
set -uo pipefail
ZERO=0000000000000000000000000000000000000000
warn() {{ printf "[WARN] %s\\n" "$*" >&2; }}
cd "{repo}" || exit 99
local_sha={local_sha}
remote_sha={remote_sha}
for _once in 1; do
{body}
done
echo "DIFF_RANGE=${{diff_range:-<unset>}}"
if [ -n "${{diff_range:-}}" ]; then
  git diff --name-only "$diff_range"
fi
"""


def _phase_0c_range_body() -> str:
    """The diff_range computation, lifted from the hook so the test runs the real thing."""
    text = _HOOK.read_text(encoding="utf-8")
    start = text.index("# Phase 0c (#5142)")
    end = text.index('changed=$(git diff --name-only "$diff_range"', start)
    return text[start:end]


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """#15246: env scrubbed -- an inherited GIT_DIR would point these calls at the
    real repository instead of the throwaway one under tmp_path."""
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=scrubbed_git_env())


def _sha(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", ref).stdout.strip()


def _commit(repo: Path, name: str, message: str) -> str:
    (repo / name).write_text(f"{name}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", message)
    return _sha(repo, "HEAD")


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(tmp_path, "init", "--quiet", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _commit(repo, "base.txt", "base")
    return repo


def _set_origin_main(repo: Path, sha: str) -> None:
    """A resolvable ``origin/main`` ref without a real remote (#15246-adjacent:
    this must be a ref git itself resolves, not a string the hook merely echoes)."""
    _git(repo, "update-ref", "refs/remotes/origin/main", sha)


def _run_phase_0c(repo: Path, *, local_sha: str, remote_sha: str) -> subprocess.CompletedProcess[str]:
    script = _HARNESS.format(body=_phase_0c_range_body(), repo=repo, local_sha=local_sha, remote_sha=remote_sha)
    return subprocess.run(  # noqa: S603
        ["bash", "-c", script],  # noqa: S607
        capture_output=True,
        text=True,
        env=scrubbed_git_env(),
        check=False,
    )


def _changed_files(result: subprocess.CompletedProcess[str]) -> set[str]:
    lines = result.stdout.splitlines()
    assert lines and lines[0].startswith("DIFF_RANGE="), f"harness did not report a range:\n{result.stdout}"
    return set(lines[1:])


def test_a_rebased_force_push_selects_only_the_branchs_own_files(tmp_path: Path) -> None:
    """The regression: remote_sha..local_sha pulled in unrelated origin/main history.

    Simulates the exact #16413 shape: a PR branch is pushed once (remote_sha),
    origin/main then gains an unrelated commit, the PR branch rebases onto the
    new origin/main and force-pushes (local_sha). The verified changeset must
    be the PR's own file only.
    """
    repo = _init_repo(tmp_path)
    base = _sha(repo, "HEAD")
    _set_origin_main(repo, base)

    _git(repo, "switch", "--quiet", "-c", "pr")
    remote_sha = _commit(repo, "pr_file.txt", "pr's own change")

    _git(repo, "switch", "--quiet", "-")  # back to the default branch, standing in for origin/main's history
    _set_origin_main(repo, _commit(repo, "unrelated.txt", "unrelated origin/main work"))

    _git(repo, "switch", "--quiet", "pr")
    _git(repo, "rebase", "--quiet", "refs/remotes/origin/main")
    local_sha = _sha(repo, "HEAD")

    result = _run_phase_0c(repo, local_sha=local_sha, remote_sha=remote_sha)
    assert result.returncode == 0, f"harness failed:\n{result.stdout}\n{result.stderr}"
    changed = _changed_files(result)

    assert changed == {"pr_file.txt"}, (
        f"expected only the PR's own file, got {changed} -- remote_sha..local_sha "
        "is pulling in origin/main's own history again"
    )


def test_a_first_push_is_unchanged(tmp_path: Path) -> None:
    """remote_sha is 0000... on a first push; the merge-base fallback must still fire."""
    repo = _init_repo(tmp_path)
    base = _sha(repo, "HEAD")
    _set_origin_main(repo, base)

    _git(repo, "switch", "--quiet", "-c", "pr2")
    local_sha = _commit(repo, "pr2_file.txt", "pr2's own change")

    zero = "0" * 40
    result = _run_phase_0c(repo, local_sha=local_sha, remote_sha=zero)
    assert result.returncode == 0, f"harness failed:\n{result.stdout}\n{result.stderr}"
    changed = _changed_files(result)

    assert changed == {"pr2_file.txt"}, f"expected only the PR's own file on a first push, got {changed}"


def test_no_merge_base_on_an_existing_branch_falls_back_to_the_old_range(tmp_path: Path) -> None:
    """The last-resort fallback: no merge base at all must not skip verification outright
    on an ordinary push, unlike the first-push case (which warns and skips)."""
    repo = _init_repo(tmp_path)
    _set_origin_main(repo, _sha(repo, "HEAD"))

    # A history with no common ancestor with origin/main: an orphan branch.
    # base.txt tags along from the index git carries into --orphan -- harmless,
    # since it is not origin/main's tip either way and merge-base still finds
    # nothing shared with a ref this branch never descends from.
    _git(repo, "switch", "--quiet", "--orphan", "detached")
    remote_sha = _commit(repo, "orphan_a.txt", "orphan first commit")
    local_sha = _commit(repo, "orphan_b.txt", "orphan second commit")

    result = _run_phase_0c(repo, local_sha=local_sha, remote_sha=remote_sha)
    assert result.returncode == 0, f"harness failed:\n{result.stdout}\n{result.stderr}"
    changed = _changed_files(result)

    # No merge base exists, remote_sha is not ZERO, so the last-resort fallback
    # (the old two-dot range) must still produce a result rather than skip.
    assert changed == {"orphan_b.txt"}, f"expected the last-resort remote_sha..local_sha fallback, got {changed}"
