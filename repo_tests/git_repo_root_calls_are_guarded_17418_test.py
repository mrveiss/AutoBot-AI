# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every `git_repo_root` call site checks whether it succeeded (#17418).

`git_repo_root` returns 1 with **no stdout** outside a work tree
(`scripts/lib/git-root.sh`). Two shapes get that wrong, in opposite ways:

    cd "$(git_repo_root)" || exit N     the guard CANNOT FIRE. `cd ""` returns 0
                                        and leaves the cwd alone, so execution
                                        continues from wherever it started and
                                        dies later at an unrelated line (#17410).

    ROOT=$(git_repo_root)               a bare failing substitution under
    cd "$ROOT"                          `set -e` aborts immediately with an exit
                                        code the script did not choose -- in
                                        `check-issue-close-refs.sh` that was 1,
                                        which is its own verdict for "closure
                                        blocked", with empty stderr (#17418).

Both end with a script reporting something it never determined. The safe shape
assigns first and checks the assignment:

    repo_root=$(git_repo_root) || { echo "..." >&2; exit N; }

This guard is class-wide on purpose. #17410 fixed three files of the first shape
and #17418 one file of the second; fixing instances without pinning the shape
leaves the next author to rediscover it.
"""

import pathlib
import re

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

#: `repo_root()`, never `__file__.parents[N]` -- #15925 pins one spelling so a
#: guard cannot silently bind a different tree than the rest of the suite.
_ROOT = repo_root()
_SCAN_DIRS = ("scripts", "pipeline-scripts", "tools")

#: `cd "$(git_repo_root)"` in any form -- the guard that cannot fire.
_CD_SUBSTITUTION = re.compile(r'cd\s+"\$\(\s*git_repo_root')

#: An assignment from `git_repo_root` with no `||` on the SAME line.
_BARE_ASSIGNMENT = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*=\$\(\s*git_repo_root[^)]*\)\s*$")


def _code_lines(path: pathlib.Path):
    """(lineno, line) for lines that are not whole-line comments.

    Written the moment this guard's first run flagged three COMMENTS that
    describe the very shape it forbids -- #17410 documents `cd "$(git_repo_root)"`
    at three call sites precisely so nobody reintroduces it. A guard that reads
    its own subject's documentation as a finding is #16750's shape, and it makes
    the correct fix look like a violation.

    LIMIT, stated rather than implied: only whole-line comments are skipped. A
    trailing `# ...` on a code line is not stripped, because doing that properly
    needs quote awareness -- a `#` inside a string is not a comment -- and a
    regex that ignores that would reintroduce the same class one level down.
    No call site currently uses a trailing comment on these lines.
    """
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        yield n, line


def _shell_files() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if base.is_dir():
            found.extend(sorted(base.rglob("*.sh")))
    return found


def _files_calling_git_repo_root(root: str | pathlib.Path | None = None) -> tuple[str, ...]:
    """Every shell file that calls `git_repo_root`, relative to *root*."""
    base = pathlib.Path(root) if root else _ROOT
    hits: list[str] = []
    for d in _SCAN_DIRS:
        top = base / d
        if not top.is_dir():
            continue
        for path in sorted(top.rglob("*.sh")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "git_repo_root" in text:
                hits.append(str(path.relative_to(base)))
    return tuple(hits)


#: The floor exists so "no unguarded call sites" cannot be satisfied by reading
#: no files. Measured at 8 when this landed; the population is call sites, not
#: findings, which is the distinction a findings-floor cannot make.
CALL_SITE_FILES = declare(
    "git-repo-root-call-site-files",
    discover=_files_calling_git_repo_root,
    floor=5,
    growth=10,
    what="shell files calling `git_repo_root` (#17418)",
)


def test_the_sweep_actually_reaches_the_tree() -> None:
    """`no unguarded sites` must be distinguishable from `no files read`."""
    CALL_SITE_FILES.verify_floor(_ROOT)


def test_no_call_site_uses_the_guard_that_cannot_fire() -> None:
    """`cd "$(git_repo_root)" || ...` -- `cd ""` returns 0, so the `||` is dead."""
    offenders = [
        f"{p.relative_to(_ROOT)}:{n}"
        for p in _shell_files()
        for n, line in _code_lines(p)
        if _CD_SUBSTITUTION.search(line)
    ]
    assert not offenders, (
        '`cd "$(git_repo_root)"` cannot fail: an empty substitution runs `cd ""`, which '
        f"returns 0 and leaves the cwd unchanged, so the `||` never runs (#17410): {offenders}"
    )


def test_no_call_site_assigns_without_checking() -> None:
    """A bare `X=$(git_repo_root)` aborts with an exit code the script did not pick."""
    offenders = [
        f"{p.relative_to(_ROOT)}:{n}"
        for p in _shell_files()
        for n, line in _code_lines(p)
        if _BARE_ASSIGNMENT.match(line)
    ]
    assert not offenders, (
        "a bare `X=$(git_repo_root)` under `set -e` aborts with an exit code the script never "
        "chose, and empty stderr -- indistinguishable from its own domain verdict. Use "
        f"`X=$(git_repo_root) || {{ echo ... >&2; exit N; }}`: {offenders}"
    )


@pytest.mark.parametrize(
    "line,matcher,name",
    [
        ('cd "$(git_repo_root)" || exit 0', _CD_SUBSTITUTION, "cd-substitution"),
        ('  cd "$( git_repo_root )"', _CD_SUBSTITUTION, "cd-substitution-spaced"),
        ("ROOT=$(git_repo_root)", _BARE_ASSIGNMENT, "bare-assignment"),
        ("  REPO_ROOT=$(git_repo_root)  ", _BARE_ASSIGNMENT, "bare-assignment-indented"),
    ],
)
def test_the_detectors_recognise_the_shapes_they_forbid(line: str, matcher: re.Pattern, name: str) -> None:
    """A detector is worth what it detects.

    Asserted through the module's own compiled patterns, which is what the two
    sweeps above use -- not a contrast re-written here, which would pass against
    a pattern that can no longer see the shape.
    """
    assert matcher.search(line) or matcher.match(line), f"{name} no longer matches its own shape"


def test_a_comment_describing_the_forbidden_shape_is_not_a_finding() -> None:
    """#16750: a comment quoting what a guard forbids must not trip it.

    Three call sites document `cd "$(git_repo_root)"` so nobody reintroduces it.
    Reading those as violations would make the fix look like the defect.
    """
    documented = '# Two steps, never `cd "$(git_repo_root)" || ...`: an empty substitution'
    assert _CD_SUBSTITUTION.search(documented), "precondition: the raw pattern does match it"
    assert documented.lstrip().startswith("#"), "and _code_lines is what must skip it"


def test_the_safe_shape_is_not_flagged() -> None:
    """Positive control: a detector that matched everything would satisfy the
    two sweeps above only because the tree happens to be clean."""
    safe = 'repo_root=$(git_repo_root) || { echo "not a git repo" >&2; exit 2; }'
    assert not _BARE_ASSIGNMENT.match(safe)
    assert not _CD_SUBSTITUTION.search(safe)
