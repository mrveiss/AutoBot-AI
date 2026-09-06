# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A guard declares what it examined, so the claim can be checked (#15826).

A tree-scanning guard that finds no violations is only good news if it looked.
A glob that stops matching, a root that moves, a filter inverted, a shallow
checkout — each turns the guard into a function that returns "clean" without
reading anything, and the clean line is byte-identical to the honest one.

WHY THIS IS NOT `enforce_reach`
-------------------------------
``tools/lint/_scan_helpers.enforce_reach`` is the same idea for a *hook*: it
takes ``full_repo`` and returns an exit code. A pytest guard cannot use it
naturally, and the census that motivated this issue counted its callers — which
measured which dialect a file was written in, not whether the property held.
Guards in ``repo_tests/`` already express it as ``assert len(found) >= _MIN_X``;
what they cannot do is prove that assertion *fires*, because nothing drives
their discovery against an empty tree.

WHAT THIS ADDS
--------------
Declaring reach as data rather than as an assertion inside one test makes it
enumerable, so ``reach_declarations_test.py`` can take every declaration in the
suite, run its discovery against an empty directory, and **require the
failure**. That is the mutation half — applied once, mechanically, instead of
one hand-written mutation per guard that nobody maintains.

A floor without a test proving it fires is decoration; this is the machinery
that makes the proof automatic rather than a promise.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

#: Every declaration made by an imported guard module. Populated by ``declare``
#: at import time so the meta-test can enumerate without importing by path.
REGISTRY: dict[str, "Reach"] = {}


@dataclass(frozen=True)
class Reach:
    """What one guard examines, and the least it may find and still be believed.

    ``floor`` is bound to what the sweep **discovered**, never to what it
    reported. A floor on findings says "the tree is clean" twice and checks
    neither; that is the failure this exists to separate from an honest pass.
    """

    name: str
    discover: Callable[[Path], Sequence[object]]
    floor: int
    what: str

    def examined(self, root: Path) -> Sequence[object]:
        """Discover under *root*, or fail loudly having found implausibly little.

        This bounds the sweep's **input**. It is not sufficient on its own: a
        guard that lists 1,000 candidates and then silently skips 997 of them
        clears this and still speaks for a tree it never read. Pair it with
        :meth:`completed`.
        """
        found = self.discover(root)
        self._require(len(found), "reached", self.what)
        return found

    def completed(self, processed: Sequence[object] | int) -> None:
        """Apply the same floor to what the guard actually **finished**.

        Candidates are not coverage (#15826 review). Both guards converted in
        this slice skip items on failure — an unreadable file, a source that
        will not parse — after the input floor has already cleared, so without
        this the floor measured how much work was *available* rather than how
        much was done. A skip is not a clean file.
        """
        count = processed if isinstance(processed, int) else len(processed)
        self._require(count, "completed", self.what)

    def _require(self, count: int, verb: str, what: str) -> None:
        if count < self.floor:
            raise AssertionError(
                f"[{self.name}] {verb} {count} {what}; floor is {self.floor}. "
                f"Fix the sweep, not the tree — a clean result below this floor asserts nothing."
            )


def declare(name: str, *, discover: Callable[[Path], Sequence[object]], floor: int, what: str) -> Reach:
    """Register a reach declaration and return it.

    Registration is the point: an undeclared guard is invisible to the meta-test
    and its floor is unproven, so adoption is measurable rather than assumed.
    """
    reach = Reach(name=name, discover=discover, floor=floor, what=what)
    REGISTRY[name] = reach
    return reach
