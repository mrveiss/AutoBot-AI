# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One spelling of "the repository root" for every guard in ``repo_tests`` (#15925).

161 bindings across 37 distinct expressions used to answer this question
independently. That is not a tidiness problem: ``python_filter_covers_its_guards_test.py``
answers "which trees does this guard read" by *pattern-matching the root binding*,
so every spelling nobody thought of is a guard the coverage instrument cannot see.
Keyed on the identifier ``_REPO_ROOT`` it saw 46 of 131; re-keyed on
``Path(__file__).resolve().parents[N]`` it missed the 12 writing
``.resolve().parent.parent``. Both fixes chase a convention nothing enforces.
With one call, detecting what a guard reads is a search for that call.

**This module is an anchor, not an algorithm.** The algorithm is
:func:`autobot_shared.paths.git_repo_root`, which asks git with
:func:`~autobot_shared.paths.scrubbed_git_env` applied so an inherited hook
environment cannot redirect the answer. Re-deriving the root here would fork the
concept — the thing this issue exists to stop. What this module adds is the one
thing that function cannot supply: *which directory to ask from*.

That matters more than it looks. ``git_repo_root()`` with no argument asks from
the **process working directory**, while every binding it replaces was relative
to the guard's own ``__file__``. Under pytest those usually agree, and when they
disagree — a run from a subdirectory, a worktree, a tmpdir — the cwd-relative
answer is silently a different checkout. This module anchors on its own location
instead, and since every guard lives beside it, one anchor serves all of them.

Git answers when git can (it is what makes a worktree or a nested checkout
resolve to the *right* tree), and this file's own location answers when it
cannot. That fallback is not a weakening: it is precisely what all 161 bindings
did before, so no guard is worse off than it was, and the anchor is knowable
without any subprocess.

Fail-closed belongs one level up, not here. A guard that cannot *enumerate*
tracked files has inspected nothing and must say so (#15176, #15777) — but
"where is the tree" is not that question, and raising it at import time takes
the whole module down before any test can skip. `promtool_rules_test.py` proves
the point: it runs a subprocess with `git` stripped from `PATH` to check that a
developer machine still SKIPS, and a git-only root turned that skip into an
import-time crash.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from autobot_shared.paths import GitRepoRootUnavailable, git_repo_root

__all__ = ["GitRepoRootUnavailable", "repo_root"]


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """The root of the checkout this file belongs to, resolved.

    Asks git first, so a worktree or a nested checkout resolves to its own
    tree. Falls back to this file's location when git cannot answer — the same
    root the hand-rolled bindings computed, and reachable with no subprocess.
    """
    # `.resolve()` because `git rev-parse` returns whatever path it was reached
    # by, and callers compare roots to `Path(...).resolve()` results. Two spellings
    # of one directory compare unequal, and the failure is a guard quietly
    # covering nothing rather than an error.
    anchor = Path(__file__).resolve()
    try:
        return git_repo_root(anchor.parent).resolve()
    except GitRepoRootUnavailable:
        # `repo_tests/_paths.py` -> the tree root. The one hand-rolled binding
        # left in this repository, and the reason it is allowed: the anchor
        # cannot ask anything else where it is.
        return anchor.parents[1]
