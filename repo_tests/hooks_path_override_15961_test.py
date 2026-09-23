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
#: Re-pinned 6412 -> 6421 (#17133): measured population 6821 exceeded the
#: declared allowance (skips=1 + growth=400 = 401) by 8. Population minus the
#: unchanged growth allowance, per that same growth judgement call above.
#: Re-pinned 6421 -> 6473 (#17134): measured population 6873 after the security train
#: merged main and the command-approvals branch. Population minus the unchanged growth
#: allowance, same formula as the #17133 re-pin.
#: Re-pinned 6473 -> 6481 (#17072): measured population 6881 after #17072's own file
#: additions (8 net over main, 7 more than the allowance absorbs). Same formula again.
#: Re-pinned 6481 -> 6484 (#17138): measured population 6884 after merging main (the
#: #17043-17056 approval-consolidation vehicle's own files) plus this PR's own 3 new
#: test files -- this guard's SCANNED glob has no _test.py exclusion, unlike the
#: prompt-injection-detector-strict-mode floor checked in the same push. Same formula.
#: Re-pinned 6484 -> 6486 (#17147): measured population 6886 once #17139, #17140,
#: #17145 and #17146 were consolidated. Each fit on its own -- #17145 measured 6884
#: and re-pinned to 6484 for it -- but their added files combine, and the allowance
#: had one file of headroom. Population minus the unchanged growth allowance.
#: Re-pinned 6486 -> 6488 (#17154): measured 6888 once #17148 and #16937 were
#: consolidated. #17148 adds no counting files and #16937 adds two; each fit
#: alone against the 6487 allowance, the pair does not. Sixth re-pin of this
#: floor in one night and the second caused purely by combining PRs that each
#: measured correctly -- see #17142.
#: Re-pinned 6488 -> 6491 (#17153): on `main` the population measured 6891 after
#: #17153 and #17184 landed -- three new counting files between them
#: (locale_html_entity_leak_test.py, ansible_shared_cert_become_16020_test.py,
#: ansible_nginx_cert_before_install_17172_test.py) -- and floor 6488 left a gap
#: of 403 against the 401 allowance, so every PR touching repo_tests went red.
#: Same #17142 shape a third time: each of those PRs fit alone against the 6889
#: allowance, the pair did not, and neither author could see the other's
#: contribution.
#:
#: Landing from this vehicle branch the population is 6885, not 6891 -- the
#: consolidation nets out six counting files -- so the floor is pinned ABOVE
#: `population - growth` (6485) on purpose. Re-derived on the tree this actually
#: merges from, not on `main`, because a floor computed against a different tree
#: is the mistake this comment already records twice. A higher floor is the
#: stricter direction: it narrows the gap, leaving 7 files of headroom here
#: rather than the 1 that 6491 leaves against `main`'s larger population.
#: Re-pinned 6509 -> 6511 (#17256): measured 6911 on the tree that merges this
#: branch with main. Two new files -- api/knowledge_code_indexing.py and
#: repo_tests/code_graph_writer_reader_agree_17254_test.py -- put it one past the
#: 401 allowance. Ninth re-pin; the population was verified by enumerating the
#: same globs the discover uses (6880 globbed + 31 extensionless shell scripts)
#: rather than by adding two to the number CI last reported.
#:
#: Re-pinned 6507 -> 6509 (#17241): measured 6909. The previous pin was taken at
#: 6907 and tolerates 401 (growth 400 + skips 1); this branch adds two guard
#: files -- ansible_code_source_delegation_17243 and
#: ai_stack_manifest_agreement_17242 -- which puts the population 402 above the
#: floor and one file past the tolerance. Eighth re-pin, and the fifth where the
#: branch measured correctly on its own and only collides once combined (#17142).
#: Raising a reach FLOOR is the stricter direction: it asserts the sweep must
#: reach MORE, unlike a size ceiling, which may only come down.
#:
#: Re-pinned 6491 -> 6507 (vehicle v0.9.1): measured 6907 on the tree that
#: merges #16974, #17125, #17156, #17168, #17182 and #17186 together. Each
#: fit alone against main's 6891; the six together do not. Seventh re-pin of
#: this floor and the fourth caused purely by combining PRs that each
#: measured correctly -- #17142. Consolidating them into one vehicle is what
#: made the collision surface once here instead of six times in sequence.
#: Re-pinned 6511 -> 6523 (#16230): measured 6923 on the tree that merges this
#: branch with main, not on main -- a floor computed against a different tree is
#: the mistake this comment already records twice. Floor = population - growth.
#: Tenth re-pin. This branch's own contribution is eight counting files
#: (sync_cache_scheduler.py and its test, analytics_cost_pricing.py,
#: schemas_analytics_pricing.py, calculators_test.py, _pricing_seed.py,
#: pricing_refresh_baseline_fallback_test.py, no_new_hardcoded_price_table_16233_test.py)
#: against 401 of allowance that main had already used 404 of on its own -- so
#: this branch did not cause the red and could not have avoided it. That is the
#: #17142 shape once more, and at ten re-pins the allowance is the thing to
#: question, not the floor: 400 has not tracked how fast this tree adds files.
REACH = declare(
    "hooks-path-override",
    discover=_scanned_files,
    # Re-pinned 6523 -> 6525 (#16230): measured 6925 on the merged tree, two files
    # after the 6523 pin taken earlier in the same session. Eleventh re-pin, second
    # within one branch. Filed as its own issue rather than absorbed again: a floor
    # that needs re-pinning twice in one day is telling you the growth allowance is
    # wrong, not that the floor is.
    # Re-pinned 6525 -> 6527 (#17300): measured 6927 on the merged tree. TWELFTH
    # re-pin, and the third inside a single day. This branch adds two counting
    # files (two security regression tests); main had already consumed the rest
    # of the allowance. See #17142 -- at this cadence the 400-file growth
    # allowance, 5.8% of a ~6900-file tree, is the thing that is wrong.
    # Re-pinned 6527 -> 6529 (#17304): measured 6929 on the merged tree. THIRTEENTH
    # re-pin, fourth in two days. This branch adds two files. See #17142.
    # Re-pinned 6529 -> 6531 (#15473): measured 6931. FOURTEENTH re-pin, FIFTH in
    # two days. This branch adds exactly two counting files
    # (check_codeql_alert_ceiling.sh and its test) out of 401 of allowance, and
    # main had consumed the other 399 before this branch existed -- so once again
    # the branch that pays for the re-pin is not the branch that caused it. Five
    # re-pins in two days, every one of them this same shape, is not a floor that
    # keeps being set wrong: it is a growth allowance that does not describe how
    # fast this tree adds files. #17142 has the standing argument; this is its
    # fifth data point in 48 hours.
    # Re-pinned 6531 -> 6536 (#16415 batch): measured 6936. FIFTEENTH re-pin,
    # SIXTH in two days. This branch's own contribution is 4 counting files
    # (path_http.py + its test, the durations guard, the route guard) against
    # 401 of allowance that main had already spent 397 of. Same shape as the
    # previous five and the reason #17142 exists: 400 is 5.8% of a ~6900-file
    # tree and this tree spends it in under a week.
    # Re-pinned 6536 -> 6736 (#17317): SEVENTEENTH re-pin, and deliberately NOT
    # `population - growth` like the sixteen before it. #17142 blames `growth=400`
    # for the treadmill; the measurement says otherwise, and the difference is
    # what stops this recurring.
    #
    # There are two bounds, not one. `verify_floor` needs
    # `population - floor <= skips + growth` (401), so floor >= 6535. `completed()`
    # needs `floor <= what the guard finishes`, and since `skips=1` is this file
    # alone, that is `population - 1` = 6935. The floor may legally sit ANYWHERE
    # in 6535..6935 -- a window 400 wide.
    #
    # `floor = population - growth` pins it at the very BOTTOM of that window, so
    # slack is always exactly `growth` (400) against an allowance of 401. That
    # leaves ONE file of headroom by construction, whatever `growth` is set to --
    # raising `growth` to 800 would re-pin the floor 400 lower and leave the same
    # one file. That is why sixteen re-pins did not help, and why the fix is not a
    # bigger allowance.
    #
    # 6736 is `population - 200`, mid-window: 201 files of headroom before the
    # allowance is breached, and 199 files of shrink before `completed()` is. It is
    # also a STRICTER guard than 6538, not a looser one -- the floor asserts how
    # much of the tree was actually reached, so raising it within the window
    # demands more, and only the allowance check cares about the gap.
    #
    # Measured: main is 6936 (6905 tracked .py/.sh/.yml/.yaml plus extensionless
    # shell), confirmed by two independent branches -- #17323 adds 3 counted files
    # and CI read 6939, #17330 adds 2 and read 6938. Counted additions in flight
    # total +22 (#17327 +14, #17323 +3, #17330 +2, this +2, #17335 +1, #17341 +0);
    # 6538 had 3 files of headroom and #17327 alone would have breached it four
    # times over. Credit to autobot-ai-87 for the in-flight arithmetic.
    floor=6736,
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
