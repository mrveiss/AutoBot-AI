# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The open-PR cap must actually block a new-branch push at the cap (#17006).

Owner decision, 2026-09-18: cap *open PRs*, not branches -- 58 were open when
the cap of 40 (configurable via ``AUTOBOT_OPEN_PR_CAP``) was set, so a session
must finish and merge/close before starting new work. The gate lives in
``tools/git-hooks/pre-push``, the same chain ``scripts/install-git-hooks.sh``
already copies into the shared ``.git/hooks/`` dir for the main checkout and
every worktree (git-common-dir) -- see ``repo_tests/git_hooks_installer_test.py``
for the installer's own "it actually lands" proof; this suite is about the
check's *behaviour*, not its installation.

This drives the REAL hook script (not a reimplementation of its logic) via
git's own pre-push stdin protocol (``<local-ref> <local-sha> <remote-ref>
<remote-sha>``), with ``gh`` stubbed on ``PATH``. The stub does not
pre-compute the filtered count itself -- it pipes a canned PR-list fixture
through the REAL ``jq`` binary using the ``--jq`` expression the hook script
itself passes, exactly as gh's embedded jq would. So
``test_bot_authored_prs_excluded_from_count`` below is exercising the hook's
own filter, not a Python stand-in for it.

``_pr_list_calls`` (below) counts only the cap check's own ``gh pr list``,
never every ``gh`` invocation the hook makes. Phase 7 (#16859) -- an
unconditional ``gh pr view "$branch_name"`` -- is real, pre-existing
behaviour already on ``origin/main`` before this change
(``git show origin/main:tools/git-hooks/pre-push | grep -n 'Phase 7'``, or
just read the file past the diff hunks: a PR diff view will not show it,
since nothing here touches those lines).

``PATH`` is a curated sandbox (git/bash/coreutils only, no real ``gh``) so a
developer's own authenticated ``gh`` on this machine can never leak into the
test and mask a broken stub wiring.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

HOOK_PATH = repo_root() / "tools" / "git-hooks" / "pre-push"

_JQ = shutil.which("jq")
_BASH = shutil.which("bash")
_GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(
    _JQ is None or _BASH is None or _GIT is None,
    reason="jq/bash/git not found on this machine -- did not look, not a pass (docs/developer/MEASUREMENT_DISCIPLINE.md)",
)

# Curated PATH sandbox: enough for git plumbing + the hook's own coreutils
# calls (Phase 6 / Phase 0c), deliberately WITHOUT a real `gh` -- only the
# stub below, or nothing at all for the "gh missing" case.
_SANDBOX_TOOLS = (
    "bash",
    "git",
    "sed",
    "grep",
    "head",
    "tail",
    "cut",
    "tr",
    "xargs",
    "sort",
    "uniq",
    "cat",
    "timeout",
    "sleep",
    "wc",
    "date",
    "printf",
    "mkdir",
    "dirname",
    "basename",
    "env",
    # #16728's prepush_selection error-capture path (pre-push:387,395) needs
    # these three -- missing from this list until the vehicle merge that
    # first combined it with this test exercised that path. Without python3,
    # `python3 -m tools.lint.prepush_selection` exits 127 unconditionally,
    # which the hook treats as "selection failed" regardless of whether the
    # synthetic repo has any Python files changed.
    "mktemp",
    "rm",
    "python3",
)

_GH_STUB = """#!/usr/bin/env bash
# One line per invocation, "<subcommand> <verb>" only -- never "$*", which
# would embed the (multi-line) --jq expression itself into the call log.
printf '%s %s\\n' "$1" "$2" >> "$STATE/gh_calls"

if [ "$1" = "pr" ] && [ "$2" = "list" ]; then
  if [ "${GH_FAIL:-0}" = "1" ]; then
    echo "gh: could not connect to api.github.com" >&2
    exit 1
  fi
  if [ "${GH_HANG:-0}" = "1" ]; then
    # Outlives the hook's own `timeout "$OPEN_PR_CAP_TIMEOUT"` wrapper on
    # purpose, so the kill (exit 124) comes from the hook, not this stub.
    exec sleep 30
  fi
  jq_expr=""
  prev=""
  for arg in "$@"; do
    if [ "$prev" = "--jq" ]; then jq_expr="$arg"; fi
    prev="$arg"
  done
  exec "__JQ_BIN__" -r "$jq_expr" < "$GH_FIXTURE_JSON"
fi

if [ "$1" = "pr" ] && [ "$2" = "view" ]; then
  # Real gh's message for a branch with no open PR yet -- Phase 7 (#16859) in
  # the hook itself matches this exact substring. Unaffected by GH_FAIL: that
  # flag targets the cap check's own `pr list` call, not Phase 7's `pr view`.
  echo "no pull requests found for branch \\"$3\\"" >&2
  exit 1
fi

echo "fake gh: unexpected invocation: $*" >&2
exit 2
"""


def _make_sandbox(tmp_path: Path, *, include_gh: bool) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in _SANDBOX_TOOLS:
        real = shutil.which(name)
        if real is None:
            continue
        link = bin_dir / name
        if not link.exists():
            os.symlink(real, link)
    if include_gh:
        stub = bin_dir / "gh"
        stub.write_text(_GH_STUB.replace("__JQ_BIN__", _JQ), encoding="utf-8")
        stub.chmod(0o755)
    return bin_dir


_BASE_CREATED_AT = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _pr(number: int, days_ago: int, *, login: str = "mrveiss", is_bot: bool = False, cross_repo: bool = False) -> dict:
    """`days_ago` is real date arithmetic (not a clamped day-of-month), so distinct
    values never collide regardless of magnitude -- `sort_by(.createdAt)` in the
    hook's own jq filter needs a real, unambiguous ordering to test truncation."""
    created = _BASE_CREATED_AT - timedelta(days=days_ago)
    return {
        "number": number,
        "title": f"pr {number}",
        "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "author": {"login": login, "is_bot": is_bot},
        "isCrossRepository": cross_repo,
    }


def _git(cwd: Path, *args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True, env=env)


def _base_env(tmp_path: Path, bin_dir: Path) -> dict:
    """A hand-built env, deliberately NOT derived from `os.environ` -- the whole
    point of the PATH sandbox is that nothing ambient (a real `gh`, a real
    `GITHUB_TOKEN`) can leak in. #15246: still routed through
    `scrubbed_git_env()` so a `git init`/`add`/`commit` this suite runs under
    this repo's own pre-push hook (which exports GIT_DIR with no
    GIT_WORK_TREE) can never be redirected at the live repo -- moot here since
    the dict below carries none of AMBIENT_GIT_VARS, but that is exactly the
    case the helper is a no-op for, not a case for skipping it.
    """
    return scrubbed_git_env(
        {
            "PATH": str(bin_dir),
            "HOME": str(tmp_path),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            # #16728's `python3 -m tools.lint.prepush_selection` call resolves
            # `tools` via PYTHONPATH, not cwd -- cwd is the synthetic repo
            # below, which has no `tools/` package of its own. Runs the REAL
            # selection tool's code against the synthetic repo's git state,
            # same split as HOOK_PATH itself (real script, fake repo).
            "PYTHONPATH": str(repo_root()),
        }
    )


def _seed_repo(tmp_path: Path, env: dict, branch: str, *, second_commit: bool) -> tuple[Path, str, str]:
    """A real repo with `origin/main` and a feature branch, so Phase 0c's
    `git merge-base "$local_sha" origin/main` always resolves regardless of
    what remote_sha a test feeds the hook on stdin.

    Returns (local_repo, sha_of_first_feature_commit, sha_of_second_or_same).
    """
    bare = tmp_path / "origin.git"
    local = tmp_path / "local"
    _git(tmp_path, "init", "--quiet", "--bare", str(bare), env=env)
    _git(tmp_path, "init", "--quiet", "-b", "main", str(local), env=env)
    _git(local, "config", "user.email", "t@t", env=env)
    _git(local, "config", "user.name", "t", env=env)
    (local / "README.md").write_text("seed\n", encoding="utf-8")
    # prepush_selection.py's main() reads `(Path.cwd() / "pytest.ini")` --
    # needs SOME pytest.ini in the synthetic repo, or it raises before ever
    # looking at PYTHONPATH. Real defaults so the selection logic behaves
    # like this repo's own.
    (local / "pytest.ini").write_text("[pytest]\npython_files = test_*.py *_test.py\n", encoding="utf-8")
    _git(local, "add", "README.md", "pytest.ini", env=env)
    _git(local, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "seed", env=env)
    _git(local, "remote", "add", "origin", str(bare), env=env)
    _git(local, "push", "-q", "origin", "main", env=env)

    _git(local, "checkout", "-q", "-b", branch, env=env)
    (local / "first.txt").write_text("first\n", encoding="utf-8")
    _git(local, "add", "first.txt", env=env)
    _git(local, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "first", env=env)
    sha_first = _git(local, "rev-parse", "HEAD", env=env).stdout.strip()

    sha_second = sha_first
    if second_commit:
        (local / "second.txt").write_text("second\n", encoding="utf-8")
        _git(local, "add", "second.txt", env=env)
        _git(local, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "second", env=env)
        sha_second = _git(local, "rev-parse", "HEAD", env=env).stdout.strip()

    return local, sha_first, sha_second


def _run_hook(
    tmp_path: Path,
    *,
    include_gh: bool,
    prs: list[dict] | None,
    cap: str | None,
    gh_fail: bool = False,
    gh_hang: bool = False,
    new_branch: bool,
    ref_prefix: str = "refs/heads/",
    subprocess_timeout: int = 60,
) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir = _make_sandbox(tmp_path, include_gh=include_gh)
    env = _base_env(tmp_path, bin_dir)
    if cap is not None:
        env["AUTOBOT_OPEN_PR_CAP"] = cap
    if gh_fail:
        env["GH_FAIL"] = "1"
    if gh_hang:
        env["GH_HANG"] = "1"

    state = tmp_path / "state"
    state.mkdir()
    env["STATE"] = str(state)

    if prs is not None:
        fixture = tmp_path / "prs.json"
        fixture.write_text(json.dumps(prs), encoding="utf-8")
        env["GH_FIXTURE_JSON"] = str(fixture)

    branch = "open-pr-cap-gate-test"
    local, sha_first, sha_second = _seed_repo(tmp_path, env, branch, second_commit=not new_branch)

    zero = "0" * 40
    if new_branch:
        local_sha, remote_sha = sha_first, zero
    else:
        local_sha, remote_sha = sha_second, sha_first  # already on the remote

    # `ref_prefix` lets a test push a TAG (refs/tags/...) instead of a branch
    # -- `local_ref`, not just a zero `remote_sha`, is a distinct thing to
    # target: the fake `branch` name is reused as the tag name too, which is
    # fine since nothing here cares about tag-name syntax.
    local_ref = f"{ref_prefix}{branch}"
    remote_ref = local_ref
    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        cwd=local,
        input=f"{local_ref} {local_sha} {remote_ref} {remote_sha}\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=subprocess_timeout,
    )
    calls_file = state / "gh_calls"
    calls = calls_file.read_text(encoding="utf-8").splitlines() if calls_file.exists() else []
    return result, calls


def _pr_list_calls(calls: list[str]) -> int:
    """How many times the cap check's own `gh pr list` ran -- see the module
    docstring for why this is scoped to `pr list` and not every `gh` call
    the hook makes (Phase 7's `pr view` is real, pre-existing, unrelated)."""
    return sum(1 for c in calls if c == "pr list")


def test_below_cap_allows_new_branch_push(tmp_path: Path) -> None:
    prs = [_pr(n, days_ago=n) for n in (1, 2, 3)]  # 3 real, non-bot, non-fork
    result, calls = _run_hook(tmp_path, include_gh=True, prs=prs, cap="5", new_branch=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _pr_list_calls(calls) == 1, f"expected exactly one `gh pr list` call, got {calls}"


def test_at_cap_refuses_new_branch_push_with_count_and_cap_in_message(tmp_path: Path) -> None:
    # 12 real PRs, numbered like real GitHub PRs (ascending number == ascending
    # age), so days_ago must DECREASE as number increases: #100 is oldest (12
    # days ago), #111 is newest (1 day ago).
    prs = [_pr(n, days_ago=112 - n) for n in range(100, 112)]
    result, calls = _run_hook(tmp_path, include_gh=True, prs=prs, cap="3", new_branch=True)

    assert result.returncode != 0, result.stdout + result.stderr
    assert _pr_list_calls(calls) == 1, f"expected exactly one `gh pr list` call, got {calls}"
    assert "pr view" not in calls, "a refused push must short-circuit the rest of the ref's checks"
    assert "12 open PR(s) >= cap of 3" in result.stderr, result.stderr
    # Oldest 10 (by createdAt) are listed; the two newest are not (truncated).
    assert "#100" in result.stderr and "#109" in result.stderr, result.stderr
    assert "#110" not in result.stderr and "#111" not in result.stderr, result.stderr
    # Remediation text: existing-branch pushes are unaffected.
    assert "existing PR branch" in result.stderr.lower() or "existing pr branches" in result.stderr.lower()


def test_existing_branch_push_allowed_even_at_cap(tmp_path: Path) -> None:
    prs = [_pr(n, days_ago=n) for n in range(1, 6)]  # 5 real PRs, way over cap=1
    result, calls = _run_hook(tmp_path, include_gh=True, prs=prs, cap="1", new_branch=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        _pr_list_calls(calls) == 0
    ), f"an existing-branch push must never even attempt the cap's `gh pr list`, got {calls}"


def test_new_tag_push_is_allowed_even_at_cap(tmp_path: Path) -> None:
    """#17008 review: gating on `remote_sha == ZERO` alone also matches a brand-new
    TAG (`git push origin v1.2.3` has a zero remote_sha too), and a tag is never a
    PR head. The gate must additionally require `local_ref` to be `refs/heads/*`."""
    prs = [_pr(n, days_ago=n) for n in range(1, 50)]  # far over any sane cap
    result, calls = _run_hook(tmp_path, include_gh=True, prs=prs, cap="1", new_branch=True, ref_prefix="refs/tags/")

    assert result.returncode == 0, result.stdout + result.stderr
    assert _pr_list_calls(calls) == 0, f"a new-tag push must never invoke the cap's `gh pr list`, got {calls}"


def test_gh_timeout_refuses_and_has_no_override(tmp_path: Path) -> None:
    """#17008 review, LOW: the `gh pr list` call is time-boxed (OPEN_PR_CAP_TIMEOUT)
    and a timeout fails closed like every other undetermined-count case -- and,
    unlike the file's other timeouts, AUTOBOT_PREPUSH_ALLOW_TIMEOUT=1 must NOT
    rescue it: the cap has no bypass besides the cap value itself."""
    bin_dir = _make_sandbox(tmp_path, include_gh=True)
    env = _base_env(tmp_path, bin_dir)
    env["GH_HANG"] = "1"
    env["AUTOBOT_PREPUSH_ALLOW_TIMEOUT"] = "1"  # must be ignored by the cap check

    state = tmp_path / "state"
    state.mkdir()
    env["STATE"] = str(state)

    branch = "open-pr-cap-gate-test"
    local, sha_first, _ = _seed_repo(tmp_path, env, branch, second_commit=False)
    zero = "0" * 40
    ref = f"refs/heads/{branch}"
    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        cwd=local,
        input=f"{ref} {sha_first} {ref} {zero}\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,  # the hook's own internal timeout (10s) fires well inside this
    )
    calls = (state / "gh_calls").read_text(encoding="utf-8").splitlines() if (state / "gh_calls").exists() else []

    assert result.returncode != 0, result.stdout + result.stderr
    assert _pr_list_calls(calls) == 1
    assert "could not determine" in result.stderr.lower(), result.stderr
    assert "timed out" in result.stderr.lower(), result.stderr
    assert "AUTOBOT_PREPUSH_ALLOW_TIMEOUT does not apply" in result.stderr, result.stderr


def test_gh_failure_refuses_with_could_not_determine_message(tmp_path: Path) -> None:
    """Negative control (#17006 AC): a failed query is refused, never treated as 'under the cap'."""
    result, calls = _run_hook(tmp_path, include_gh=True, prs=[], cap="40", gh_fail=True, new_branch=True)

    assert result.returncode != 0, result.stdout + result.stderr
    assert _pr_list_calls(calls) == 1
    assert "could not determine" in result.stderr.lower(), result.stderr
    assert "under the cap" in result.stderr.lower(), result.stderr


def test_gh_missing_refuses_with_could_not_determine_message(tmp_path: Path) -> None:
    """Fail closed even before any call is attempted: no `gh` on PATH at all."""
    result, calls = _run_hook(tmp_path, include_gh=False, prs=None, cap="40", new_branch=True)

    assert result.returncode != 0, result.stdout + result.stderr
    assert calls == [], "no gh binary exists to have been called"
    assert "could not determine" in result.stderr.lower(), result.stderr


def test_bot_authored_prs_excluded_from_count(tmp_path: Path) -> None:
    """Drives the hook's REAL jq filter (via the stub piping the fixture through real jq) --
    not a Python reimplementation of the exclusion rule.

    #17008 review: the two bot entries use the shape gh actually returns, measured
    against this repo's own dependabot history -- `login: "app/dependabot"`,
    `is_bot: true` (the App-slug form, never a `[bot]`-suffixed login). `is_bot`
    is what excludes those. The third entry is a `[bot]`-suffixed login with
    `is_bot: false`, exercising the filter's defensive fallback for a login
    SHAPE, not a shape this API has been observed to produce.
    """
    prs = [
        _pr(1, days_ago=1),
        _pr(2, days_ago=2),
        _pr(90, days_ago=3, login="app/dependabot", is_bot=True),
        _pr(91, days_ago=4, login="app/github-actions", is_bot=True),
        _pr(92, days_ago=5, login="some-legacy-integration[bot]", is_bot=False),  # defensive-fallback case only
        _pr(93, days_ago=6, login="a-human-fork-contributor", cross_repo=True),
    ]
    # Raw total is 6 (>= cap of 3); the filtered (non-bot, non-fork) count is 2 (< cap).
    result, calls = _run_hook(tmp_path, include_gh=True, prs=prs, cap="3", new_branch=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _pr_list_calls(calls) == 1


def test_default_cap_is_40_when_env_unset(tmp_path: Path) -> None:
    prs = [_pr(n, days_ago=n) for n in range(1, 41)]  # exactly 40 real PRs
    result, calls = _run_hook(tmp_path, include_gh=True, prs=prs, cap=None, new_branch=True)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "cap of 40" in result.stderr, result.stderr
