# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two ambient-git-var scrub lists must actually mirror (#15877).

`scripts/lib/git-root.sh` carried a comment saying it mirrored
`autobot_shared.paths.AMBIENT_GIT_VARS` and warning that *"a variable added to
one side and not the other reopens the hole on whichever language was missed"*.

That is exactly what happened. `GIT_OBJECT_DIRECTORY` and
`GIT_ALTERNATE_OBJECT_DIRECTORIES` were added to the Python tuple and not to the
shell array, so every shell caller of `git_repo_root` ran git with two ambient
variables still set -- the hole #15176 closed, reopened on one side only.

The comment was accurate when written, described the right risk, named the right
consequence, and prevented nothing, because **a comment has no way to fail.**
This file is that comment with a failure mode attached: the same claim, checked.

Both lists are parsed from source rather than imported. Importing the Python
side would test one list against itself, and the shell side cannot be imported
at all -- so the parse is the only thing that reads what a reviewer reads.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SHELL = _ROOT / "scripts" / "lib" / "git-root.sh"
_PYTHON = _ROOT / "autobot_shared" / "paths.py"

#: Every ambient var git reads is a `GIT_`-prefixed name; the floor stops an
#: empty parse on either side from reading as agreement. Four was the shell
#: list's size when it was already WRONG, so the floor is deliberately above it.
_MIN_VARS = 5


def _shell_vars() -> set[str]:
    """Parse `GIT_ROOT_AMBIENT_VARS=( ... )`, honouring backslash continuations."""
    text = _SHELL.read_text(encoding="utf-8")
    match = re.search(r"GIT_ROOT_AMBIENT_VARS=\((.*?)\)", text, re.S)
    assert match, f"{_SHELL.name}: GIT_ROOT_AMBIENT_VARS array not found — the parse read nothing"
    return set(re.findall(r"GIT_[A-Z_]+", match.group(1)))


def _python_vars() -> set[str]:
    """Read the AMBIENT_GIT_VARS tuple literal without importing the module."""
    tree = ast.parse(_PYTHON.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "AMBIENT_GIT_VARS" for t in node.targets):
            continue
        value = ast.literal_eval(node.value)
        return {str(v) for v in value}
    raise AssertionError(f"{_PYTHON.name}: AMBIENT_GIT_VARS not found — the parse read nothing")


def test_both_lists_were_actually_read() -> None:
    """Positive assertion first: an empty parse on both sides compares equal.

    Two empty sets are identical, so the mirror check below would pass loudest
    exactly when it had read nothing at all.
    """
    shell, python = _shell_vars(), _python_vars()
    assert len(shell) >= _MIN_VARS, f"shell list parsed as {sorted(shell)} — too few to be the real list"
    assert len(python) >= _MIN_VARS, f"python list parsed as {sorted(python)} — too few to be the real list"


def test_the_shell_and_python_scrub_lists_are_identical() -> None:
    """The claim the comment made, now able to fail."""
    shell, python = _shell_vars(), _python_vars()
    only_python = sorted(python - shell)
    only_shell = sorted(shell - python)
    assert not (only_python or only_shell), (
        "the ambient-git-var scrub lists have diverged, so a git subprocess is "
        "unscrubbed on one side (#15176, #15877):\n"
        f"  only in autobot_shared/paths.py : {only_python or '—'}\n"
        f"  only in scripts/lib/git-root.sh : {only_shell or '—'}\n"
        "Add the missing name to BOTH; whichever side is short runs git with the "
        "ambient variable still set."
    )

# --- the class, not the two lists ------------------------------------------
#
# The mirror above closes the divergence between `git-root.sh` and `paths.py`.
# It does not close the reason the divergence happened: SEVEN shell sites
# hand-maintain this list, and #15783 added two variables to the Python tuple
# and to none of them. Five scrubbed four vars; one scrubbed five, and that odd
# one out is the tell -- the change was propagated into shell and stopped one
# variable in.
#
# `tools/lint/check_git_toplevel_env_scrubbed.py` was built to enforce exactly
# this invariant and contains no reference to AMBIENT_GIT_VARS,
# GIT_OBJECT_DIRECTORY or GIT_ALTERNATE_OBJECT_DIRECTORIES at all. Its allowlist
# exempts sites on the written reasoning that the four-variable unset covers
# "every git call the script makes" -- true when written, false since #15783.
# The checker built to enforce the invariant is why nobody saw it break.
#
# So this discovers rather than enumerates: any shell file that unsets GIT_DIR
# is *claiming to scrub*, and a partial claim is the dangerous one. Enumerating
# the seven would leave the eighth unguarded, and a partial fix reads as a
# disconfirmation of the whole hypothesis.

_SHELL_GLOBS = ("scripts/**/*.sh", ".claude/hooks/*.sh", "autobot-infrastructure/**/*.sh")

#: Seven sites exist today. A floor of 4 fails loudly if the globs stop matching,
#: rather than reporting every site compliant having found none.
_MIN_SCRUB_SITES = 4

_UNSET = re.compile(r"^[ \t]*unset[ \t]+((?:GIT_[A-Z_]+[ \t]*)+)", re.M)


def _scrub_sites():
    """Yield `(path, set-of-vars)` for every shell `unset` naming GIT_DIR."""
    # Only the literal `unset GIT_...` form. `git-root.sh` uses the array
    # (`unset "${GIT_ROOT_AMBIENT_VARS[@]}"`) and is covered directly by the
    # mirror test above, so it is not double-counted here -- six sites are
    # discovered, seven exist. A NEW file copying the array form would be
    # sourcing git-root.sh and inheriting the correct list; a new file copying
    # the literal form is what this catches.
    for pattern in _SHELL_GLOBS:
        for path in sorted(_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in _UNSET.finditer(text):
                names = set(match.group(1).split())
                if "GIT_DIR" in names:
                    yield path.relative_to(_ROOT).as_posix(), names


def test_the_discovery_found_the_scrub_sites() -> None:
    """Positive assertion first: a regex matching nothing exempts everything."""
    sites = list(_scrub_sites())
    assert len(sites) >= _MIN_SCRUB_SITES, (
        f"found only {len(sites)} shell scrub site(s) (floor {_MIN_SCRUB_SITES}); "
        "the discovery matched almost nothing, so the rule below would clear the tree "
        "by never reading it"
    )


def test_every_shell_scrub_site_unsets_the_whole_list() -> None:
    """A site that unsets GIT_DIR claims to scrub, so it must scrub all of them.

    A partial unset is worse than none: it looks handled. #15783 added two vars
    to the Python tuple and to no shell site, and the four-variable unsets went
    on reading as complete for months.
    """
    required = _python_vars()
    short = [(p, sorted(required - names)) for p, names in _scrub_sites() if required - names]
    assert not short, (
        "these shell sites unset GIT_DIR but not the whole ambient set, so git still "
        "reads the caller's environment there (#15783, #15893):\n"
        + "\n".join(f"  {p} is missing {missing}" for p, missing in short)
    )
