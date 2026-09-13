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
from tools.lint._scan_helpers import EmptyEnumeration, logical_lines, tracked_paths

from ._paths import repo_root
from ._reach import declare

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


def _scanned_files(root: Path) -> list[str]:
    """Tracked files this guard reads, enumerated through the canonical helper.

    The `EmptyEnumeration` catch is required by the declaration contract, not a
    convenience. `tracked_paths` refuses to report an empty enumeration as a clean
    tree, which is right for a guard that would otherwise pass on nothing — but
    `reach_declarations_test` hands every declaration an empty repository on
    purpose and demands `ReachFloorError` **specifically**, because that is the
    only exception the floor itself raises. Letting `EmptyEnumeration` escape
    means the guard fails loudly while saying nothing about whether its floor
    binds, which is the distinction that test exists to draw. Returning an empty
    result puts the refusal back where the floor can make it.

    Same reason `excluded_tree_size_debt_test` catches it (#16068).
    """
    try:
        globbed = list(tracked_paths(root, *SCANNED))
    except EmptyEnumeration:
        return []
    return sorted(set(globbed) | set(_shell_scripts_without_an_extension(root)))


#: Shebang forms that mean "this is a shell script whatever it is called".
SHELL_SHEBANG = ("sh", "bash", "dash", "zsh", "ksh")


def _shell_scripts_without_an_extension(root: Path) -> list[str]:
    """Tracked files with no suffix whose shebang says shell (#16139).

    `SCANNED` is four globs, and **a git hook carries no suffix** by git's own
    convention. So `pre-commit`, `pre-push`, `post-commit-doc-sync` and 26 more
    sat outside the population entirely -- the guard existed to police hook
    configuration and could not read a single hook. Not a gap at the edge: the
    guard's own subject, outside its reach, reporting clean about files it never
    opened.

    Detected by shebang rather than by listing the hook directories. A path
    allowlist works today and is walked past by the next hook directory,
    silently, which is the failure mode this file is about.
    """
    found = []
    for rel in tracked_paths(root, "*"):
        if "." in Path(rel).name:
            continue
        try:
            with (root / rel).open(encoding="utf-8") as handle:
                first = handle.readline(200)
        except (OSError, UnicodeDecodeError):
            continue
        if first.startswith("#!") and any(sh in first for sh in SHELL_SHEBANG):
            found.append(rel)
    return found


#: `tracked_paths` already raises when git lists **nothing**, so total collapse was
#: covered. This is the other half, raised in review on #16097 and merged without it:
#: narrowing `SCANNED` from four globs to one -- or moving a directory -- drops
#: thousands of files while the enumeration stays non-empty, so the guard keeps
#: passing having read a fraction of its population. A floor below the population
#: catches only the collapse; partial loss is the failure that actually happens.
#:
#: `skips=1` is **measured, not named by inference**: the one skip is THIS FILE,
#: which exempts itself at `EXEMPT` below so its own fixtures do not read as
#: offenders. It is an exclusion BY DESIGN, not a read failure -- 0 of the
#: other 6412 raise OSError or UnicodeDecodeError, so that branch is currently
#: dead. Saying "cannot be completed" would describe incapacity where the
#: mechanism is a deliberate exemption, and a skip nobody can name is a guess
#: wearing a measurement's clothes. `completed()` therefore reports 6412. The floor sits at what the
#: guard FINISHES, not at what it finds -- the number that would have been wrong
#: here, and the reason the first ratchet attempt raised ReachFloorError. Every other
#: reads cleanly as UTF-8, so the `except (OSError, UnicodeDecodeError)` branch is
#: currently dead and nothing legitimately goes unread. If that stops being true the
#: number has to move, and saying it is zero is what makes that visible.
#: `growth=400` is the judgement call -- roughly a week of this repo's growth -- and
#: is the only figure here not taken from a measurement.
REACH = declare(
    "hooks-path-override",
    discover=_scanned_files,
    floor=6412,
    growth=400,
    skips=1,
    what="tracked shell, python and YAML files, plus extensionless shell scripts",
)


def _offending_lines(text: str) -> list[tuple[int, str]]:
    """Override invocations in ``text``, ignoring comment lines.

    A comment explaining the footgun is documentation, not an invocation. The
    distinction is the point of #15756: a guard that matches the *text* of a
    command refuses commit messages and docs that merely discuss it.

    Lines are folded through `tools.lint._scan_helpers.logical_lines` before
    matching, not read physically: a shell continuation puts `git config` on
    one physical line and `core.hooksPath <value>` on the next, and a matcher
    that never joins them inspects two lines that each look innocent.
    """
    out = []
    for number, line in logical_lines(text):
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
    read = 0
    for rel in REACH.examined(root):
        if rel in EXEMPT:
            continue
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        read += 1
        offenders += [(rel, n, line) for n, line in _offending_lines(text)]

    # Candidates are not coverage: `examined` bounds what was listed, this bounds
    # what was actually opened. Without it a sweep could list 6,413 files, fail to
    # read 6,300 of them, and still report the same green as a clean tree.
    REACH.completed(read)

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
        # A shell continuation must not hide either spelling: physical-line
        # matching would see `git config \` with no key on one line and
        # `core.hooksPath ...` with no `git config` on the next.
        "git config \\\n  core.hooksPath /tmp/nowhere",
        "git -c \\\n  core.hooksPath=/tmp/nowhere commit",
        # A comment's trailing backslash is not a continuation in bash, so the
        # command after it is live and must not be skipped as part of the
        # comment (#16414 review).
        "# see the note above \\\ngit config core.hooksPath /tmp/nowhere",
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
        # Folding a continuation must not turn a legal read into a match.
        "git config \\\n  --get core.hooksPath",
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


def test_the_sweep_reaches_the_hooks_it_exists_to_police() -> None:
    """#16139: extension-based discovery reached zero git hooks.

    `REACH` bounds the population by COUNT, which is necessary and not
    sufficient here: 6,413 files can be discovered with every hook missing, and
    the number would look healthy. `core.hooksPath` is a hook setting, so the
    files most likely to carry an override are exactly the ones a suffix filter
    cannot see -- the count stays large while the subject is absent.

    So this asserts the canonical hooks are present BY NAME. A floor on the
    population catches the collapse; naming catches the case that actually
    happened.
    """
    hooks = _shell_scripts_without_an_extension(repo_root())
    names = {Path(rel).name for rel in hooks}
    missing = {"pre-commit", "pre-push"} - names
    assert not missing, (
        f"the sweep no longer reaches {sorted(missing)}. These carry no suffix by git's "
        "own convention, so a suffix-based discovery drops them while the file count "
        "stays healthy — which is #16139 exactly."
    )
