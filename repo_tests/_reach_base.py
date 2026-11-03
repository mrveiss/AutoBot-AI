# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A reach floor computed from the base commit, not committed as a literal (#19676).

A committed ``floor=`` pins a guard against a population (all tracked Python, say) that
moves whenever any file is added, so unrelated PRs went stale on it and trains carried
re-pin commits across many test files (#19673). The floor has to come from somewhere the
PR under test cannot move: a floor taken from the live tree would follow a narrowed
``discover`` down and prove nothing. So it comes from the base commit, the same one the
other down-only ratchets judge against (:func:`repo_tests._ratchet_base.base_commit`):

    floor = population at the base - skips - growth

which is the bottom of the window a pinned floor had to sit in, so the meaning is kept: the
PR may shrink the population by up to ``growth``, and ``completed()`` must still reach the
floor. A base that cannot be read raises :class:`BaseUnavailable`; it is never a pass.

The base tree is one detached ``git worktree`` under the system temp dir, created on first
use and removed (then pruned) when the process exits, failure included. It is checked out
with ``read-tree``, so the repository's checkout hooks (symlink repair, ``node_modules``
links) never run on it.

A guard whose ``discover`` reads untracked or generated files sees a different population
at the base, so it keeps an explicit ``floor=`` (see :data:`PINNED_BY_DESIGN`).
"""

from __future__ import annotations

import atexit
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repo_tests._ratchet_base import BaseUnavailable, base_commit

from autobot_shared.paths import scrubbed_git_env

if TYPE_CHECKING:
    from repo_tests._reach import Reach

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Declarations that keep an explicit ``floor=``, each with why its population cannot be
#: measured at the base. Filled as the pins are retired; empty until a guard needs it.
PINNED_BY_DESIGN: dict[str, str] = {}

_TREE: dict[str, Path] = {}
_BASE_COUNT: dict[str, int] = {}


def _git(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=600, env=scrubbed_git_env()
    )


def _checked(out: subprocess.CompletedProcess[str], what: str) -> None:
    if out.returncode != 0:
        raise BaseUnavailable(f"{what} failed ({out.stderr.strip()}); refusing to compute a floor without the base.")


def base_tree() -> Path:
    """The base commit checked out once for this process, under the system temp dir."""
    if "tree" in _TREE:
        return _TREE["tree"]
    sha = base_commit(REPO_ROOT)
    tree = Path(tempfile.mkdtemp(prefix="autobot-reach-base-")) / "tree"
    _checked(_git("worktree", "add", "--detach", "--no-checkout", str(tree), sha), "git worktree add")
    atexit.register(remove_base_tree, tree)
    _checked(_git("read-tree", "-u", "--reset", "HEAD", cwd=tree), "checking out the base")
    _TREE["tree"] = tree
    return tree


def remove_base_tree(tree: Path) -> None:
    """Remove the base worktree, then prune its record, so nothing is left in the repo's inventory."""
    try:
        _git("worktree", "remove", str(tree))
    finally:
        _git("worktree", "prune")
        _TREE.pop("tree", None)
        if tree.parent.is_dir() and not any(tree.parent.iterdir()):
            tree.parent.rmdir()


def base_population(reach: "Reach[Any]") -> int:
    """How many items *reach* discovers at the base commit, measured once per process."""
    if reach.name not in _BASE_COUNT:
        _BASE_COUNT[reach.name] = len(reach.population(base_tree()))
    return _BASE_COUNT[reach.name]


def computed_floor(reach: "Reach[Any]") -> int:
    """``population at the base - skips - growth``: the bottom of the pinned-floor window, never below 1."""
    return max(1, base_population(reach) - reach.skips - reach.growth)


class BaseFloor:
    """Gives :class:`~repo_tests._reach.Reach` its ``floor``: the pinned one, or the base's."""

    pinned_floor: int
    min_fraction: float | None

    @property
    def floor(self) -> int:
        """The declared ``floor=`` when one was pinned, else the floor computed from the base.

        A ``min_fraction`` declaration has no count floor at all (its bound is a fraction), so 0.
        """
        if self.pinned_floor or self.min_fraction is not None:
            return self.pinned_floor
        return computed_floor(self)  # type: ignore[arg-type]

    @property
    def computed(self) -> bool:
        """True for a count floor that nothing pinned: there is no constant to go stale."""
        return not self.pinned_floor and self.min_fraction is None
