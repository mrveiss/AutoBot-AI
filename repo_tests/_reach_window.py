# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The legal window a pinned reach floor sits in, and the bottom band it may not (#17356).

Split out of ``_reach.py`` (#19676) so that module stays under the file-size ceiling; the
methods are unchanged and :class:`~repo_tests._reach.Reach` gets them through :class:`FloorWindow`.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

#: How much of ``growth`` must remain unspent for a floor to be accepted (#17356). A tenth:
#: large enough that a floor pinned at the very bottom is refused on the spot, small enough that
#: a deliberate mid-window pin is not re-litigated by the next merge.
_WINDOW_MARGIN = 0.10


class FloorWindow:
    """Window arithmetic for a pinned floor; mixed into ``Reach``, whose fields it reads."""

    name: str
    floor: int
    growth: int
    skips: int

    def population(self, root: Path) -> Sequence[Any]:  # pragma: no cover - provided by Reach
        raise NotImplementedError

    def window(self, root: Path) -> tuple[int, int, int]:
        """``(lowest legal floor, highest legal floor, the value to pin)`` -- #17356.

        BOTH bounds, because a floor has two and every re-pin comment in
        ``hooks_path_override_15961_test.py`` quotes only the first -- which is why there are
        seventeen of them. The lower bound is the gap bound :meth:`verify_floor` enforces; the
        upper is the most :meth:`completed` can clear, since a guard that skips ``skips`` items
        finishes ``population - skips`` of them and a floor above that fails the stronger of the
        two checks while satisfying the weaker.

        The third value is the one to write down. ``population - (skips + growth)`` -- the
        arithmetic every re-pin reached for -- is the BOTTOM of the window and has zero
        tolerance by construction: correct at the instant of measurement, red for every tree
        with one more file.
        """
        return self._bounds(len(self.population(root)))

    def _bounds(self, count: int) -> tuple[int, int, int]:
        """The arithmetic, in ONE place. :meth:`window` and the failure messages had a copy
        each, and two copies of a formula are two chances for a message to recommend a value
        the check would then refuse."""
        highest = count - self.skips
        return highest - self.growth, highest, highest - self.growth // 2

    def _window_sentence(self, count: int) -> str:
        lowest, highest, mid = self._bounds(count)
        return (
            f"the window against a population of {count} is "
            f"[{lowest}, {highest}] -- its bottom is the gap bound "
            f"(skips={self.skips} + growth={self.growth}) and its top is the most completed() "
            f"can clear (population - skips). Pin MID-window, at {mid}."
        )

    def _bottom_band(self, count: int, slack: int) -> str | None:
        """Refuse a floor pinned at the bottom of its own window (#17356).

        A convention was not enough, and that is measured rather than argued: the author who
        wrote up *"`population - growth` has zero tolerance"* pinned two new declarations at
        exactly that value within the hour, and both went red on the next rebase. Seven reds,
        five declarations, one night. A rule its own author violates belongs in the tool.

        The margin is a tenth of ``growth`` -- the band the caller declared as ordinary
        movement, not a number chosen here. ``growth=0`` is exempt: an equality pin is the
        deliberate choice ``growth``'s own docstring asks for when normal work does not move the
        number, and it has no window to sit in the bottom of.
        """
        if not self.growth:
            return None
        margin = max(1, math.ceil(self.growth * _WINDOW_MARGIN))
        if slack <= self.skips + self.growth - margin:
            return None
        return (
            f"[{self.name}] floor {self.floor} sits in the bottom {margin} of its window, which "
            f"is zero tolerance dressed as an allowance: the next "
            f"{self.skips + self.growth - slack} file(s) of ordinary growth turn it red on a PR "
            f"that did not touch this guard.\n"
            f"{self._window_sentence(count)}\n"
            f"Re-measure rather than carrying a number across (#15928): the value above is this "
            f"run's measurement, not a figure from a comment."
        )
