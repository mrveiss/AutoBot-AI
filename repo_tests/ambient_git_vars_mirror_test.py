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
