# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`-c core.hooksPath=<relative>` is `--no-verify` that leaves no trace (#15961).

Inside a worktree ``.git`` is a *file* holding a ``gitdir:`` pointer, not a
directory, so the relative path ``.git/hooks`` resolves to nothing. Git finds no
hooks, runs none, and the commit succeeds. There is no warning, no non-zero exit
and no output: **the commit is byte-identical to one where every hook passed.**

Why this is worse than the flag it imitates. ``--no-verify`` is a string a
reviewer, a log or a grep can find, and it means what it says. ``-c
core.hooksPath=…`` reads as configuration hygiene, and it produces a commit that
*appears* hook-verified. CLAUDE.md forbids the first and had nothing to say about
the second.

**The premise that motivates the flag is false, and that is the substance of the
fix.** The override tends to be added out of caution — a belief that a worktree
needs help finding the main checkout's hooks. Git already shares them: hook
lookup goes through ``$GIT_COMMON_DIR/hooks``, which for every worktree *is* the
main checkout's hooks directory. The repository's own shared ``commit-msg`` hook
records the same fact in its header. So the override is not a restatement of the
default; it is the only thing that can defeat it.

``test_git_shares_hooks_with_worktrees_by_default`` and
``test_a_relative_hookspath_defeats_hooks_in_a_worktree`` pin both halves against
a throwaway repository, so the claim cannot rot into a comment nobody rechecks.

**Where the detection lives, and why the flag cannot reach it.** In CI, over
tracked files. A client-side ``-c`` affects one invocation on one machine; it
cannot alter what the pushed tree contains, so a guard that reads the tree is
outside its blast radius. What this cannot do is detect that some *past* commit
was made with the flag — nothing in a commit records which hooks ran. That is a
real limit, stated rather than papered over: this guard stops the pattern from
being written down, so it is not copied from a script into a habit.

**The matcher refuses both ways of overriding, and that is a review finding
rather than the first design.** ``-c core.hooksPath=…`` is transient — one
invocation. ``git config core.hooksPath <value>`` writes to ``.git/config`` and
applies to every later command in the repository. The first version caught only
the transient form, so it refused the milder spelling and permitted the worse
one; merged, it would have made "hooksPath overrides are guarded" true-sounding
and false, and a passing guard is not re-read.

Reading and removing stay legal: ``git config --get core.hooksPath`` and
``--unset core.hooksPath`` are how ``install-git-hooks.sh`` *repairs* a bad
value, and a guard that fired on those would refuse the fix along with the
defect. Prose describing the flag — this docstring included — must also
not trip it. That distinction is not assumed: ``test_the_matcher_ignores_…``
cases pin it, because a guard keyed on a substring reports on the words rather
than the operation (#15756).
"""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env
from tools.lint._scan_helpers import tracked_paths

from ._paths import repo_root

# Two ways to override, and the review that caught the gap is the reason both are
# here. The first version matched only `-c core.hooksPath=…`, which is the
# TRANSIENT form -- one invocation, one process. `git config core.hooksPath <v>`
# writes to `.git/config` and applies to every later command in the repository,
# so the guard refused the milder spelling and permitted the worse one. A guard
# with a hole is worse than no guard: it makes "hooksPath overrides are guarded"
# true-sounding and false, and nobody re-checks a passing guard.
#
# `-c` requires whitespace, and that is checked rather than assumed: git rejects
# the attached form `-ccore.hooksPath=x` with `unknown option`, so `\s+` misses
# nothing.
OVERRIDE_RE = re.compile(r"-c\s+core\.hooksPath\s*=")

#: A `git config` invocation naming the key. Assignment is the default verb, so
#: this is an override UNLESS it carries a read-only or removing flag.
CONFIG_RE = re.compile(r"\bgit\s+config\b[^\n;|&]*\bcore\.hooksPath\b[^\n;|&]*")

#: Reading and unsetting stay legal: `install-git-hooks.sh` REPAIRS a bad value
#: with exactly these, and a guard that refused them would refuse the fix along
#: with the defect.
READ_OR_REMOVE = ("--get", "--get-all", "--get-regexp", "--list", "--unset", "--unset-all")

SCANNED = ("*.sh", "*.py", "*.yml", "*.yaml")

# This guard's own file states the pattern in prose and in its fixtures.
EXEMPT = {"repo_tests/hooks_path_override_15961_test.py"}


def _offending_lines(text: str) -> list[tuple[int, str]]:
    """Override invocations in ``text``, ignoring comment lines.

    A comment explaining the footgun is documentation, not an invocation. The
    distinction is the point of #15756: a guard that matches the *text* of a
    command refuses commit messages and docs that merely discuss it.
    """
    out = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if OVERRIDE_RE.search(line):
            out.append((number, line.strip()))
            continue
        match = CONFIG_RE.search(line)
        if match and not any(flag in match.group(0) for flag in READ_OR_REMOVE):
            out.append((number, line.strip()))
    return out


def test_no_tracked_script_overrides_the_hooks_path() -> None:
    """An override in a tracked script is the pattern becoming a habit."""
    root = repo_root()
    offenders = []
    for rel in tracked_paths(root, *SCANNED):
        if rel in EXEMPT:
            continue
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        offenders += [(rel, n, line) for n, line in _offending_lines(text)]

    assert not offenders, "\n".join(
        f"{rel}:{n}: {line}\n"
        "    Overriding core.hooksPath does not restate git's default — it replaces it. "
        "Inside a worktree `.git` is a file, so a relative value resolves to nothing, "
        "git runs NO hooks, and the commit still succeeds and looks verified. Git "
        "already shares hooks with worktrees via $GIT_COMMON_DIR/hooks; delete the "
        "override rather than correcting it."
        for rel, n, line in offenders
    )


# ------------------------------------------------------- guarding the matcher
#
# Run over the repository alone, a matcher that stopped matching would find zero
# offenders and pass — the same answer a clean tree gives. These pin both
# directions, so it is the operation being detected and not the words.


@pytest.mark.parametrize(
    "line",
    [
        "git -c core.hooksPath=.git/hooks commit -m x",
        "  git -c core.hooksPath=/tmp/nowhere commit",
        "git -c core.hooksPath = .git/hooks commit",
        # The persistent form: this one survives the process and applies to
        # every later git command in the repository.
        "git config core.hooksPath /tmp/nowhere",
        "git config --local core.hooksPath .git/hooks",
    ],
)
def test_the_matcher_catches_an_override_invocation(line: str) -> None:
    assert _offending_lines(line)


@pytest.mark.parametrize(
    "line",
    [
        'configured="$(git config --local --get core.hooksPath)"',
        "git config --local --unset core.hooksPath",
        "# never run git -c core.hooksPath=.git/hooks — it disables every hook",
        "    # -c core.hooksPath=.git/hooks is the footgun this guard refuses",
        "core.hooksPath is set by install-git-hooks.sh",
        "git config --get-all core.hooksPath",
        "git config --unset-all core.hooksPath",
    ],
)
def test_the_matcher_ignores_repair_and_prose(line: str) -> None:
    """The installer's repair and any comment about the flag must survive."""
    assert not _offending_lines(line)


# --------------------------------------------------- the behaviour it rests on


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run git in *cwd* with the ambient git environment removed.

    Not optional, and this test learned it the hard way: a git hook exports
    ``GIT_DIR``, and an inherited ``GIT_DIR`` **outranks** ``cwd=``. Under the
    pre-push hook, ``git init .`` in a temporary directory therefore
    re-initialised the repository named by that variable and created no ``.git``
    in *cwd* at all, so the fixture below failed writing a hook into a directory
    that was never made. The defect these tests are about — a git invocation
    quietly operating on a checkout other than the one named — reached them
    first (#15783, #15506).
    """
    return subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_git_env(),
    )


@pytest.fixture()
def repo_with_a_blocking_hook(tmp_path: Path) -> Path:
    """A throwaway repo whose shared pre-commit hook always refuses, plus a worktree."""
    if shutil.which("git") is None:
        pytest.skip("git is not on PATH in this environment")
    main = tmp_path / "main"
    main.mkdir()
    _git("init", "-q", ".", cwd=main)
    _git("config", "user.email", "t@example.invalid", cwd=main)
    _git("config", "user.name", "t", cwd=main)
    _git("commit", "-q", "--allow-empty", "-m", "init", cwd=main)
    assert (main / ".git").exists(), (
        "`git init` created no .git in the temporary directory — the ambient git "
        "environment reached this subprocess despite scrubbed_git_env(). Fix the "
        "leak; do not mkdir around it, or these tests silently start describing "
        "some other checkout."
    )
    hook = main / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    assert not _git(
        "config", "--get", "core.hooksPath", cwd=main
    ).stdout.strip(), "this fixture must prove git's DEFAULT behaviour; core.hooksPath is set"
    _git("worktree", "add", "-q", str(tmp_path / "wt"), "-b", "wt", cwd=main)
    return tmp_path / "wt"


def test_git_shares_hooks_with_worktrees_by_default(repo_with_a_blocking_hook: Path) -> None:
    """The premise: no override is needed for a worktree to see the hooks.

    If this ever fails, the override stops being pointless and the guard above
    needs rethinking rather than enforcing — which is why it is a test and not a
    sentence in a comment.
    """
    result = _git("commit", "--allow-empty", "-m", "x", cwd=repo_with_a_blocking_hook)
    assert result.returncode != 0, (
        "the main checkout's pre-commit hook did not run in the worktree, so git no "
        "longer shares hooks through $GIT_COMMON_DIR — reassess #15961 before "
        "enforcing the guard above"
    )


def test_a_relative_hookspath_defeats_hooks_in_a_worktree(
    repo_with_a_blocking_hook: Path,
) -> None:
    """The defect: the same commit succeeds, silently, with the override.

    The contrast with the test above is the whole finding. Same repository, same
    refusing hook, same command — one is blocked and one is committed, and the
    only difference is a flag that reads like configuration hygiene.
    """
    result = _git(
        "-c",
        "core.hooksPath=.git/hooks",
        "commit",
        "--allow-empty",
        "-m",
        "bypass",
        cwd=repo_with_a_blocking_hook,
    )
    assert result.returncode == 0, (
        "expected the override to bypass the refusing hook; if git now rejects or "
        "resolves it, #15961's premise has changed"
    )
    assert "bypass" in _git("log", "--oneline", cwd=repo_with_a_blocking_hook).stdout
