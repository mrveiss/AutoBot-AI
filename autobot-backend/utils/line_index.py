# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""O(1) offset-to-line lookup for regex scanners (#12866).

Scanners resolved a match's line number with::

    line_num = content[: match.start()].count("\\n") + 1

which slices the file from the start and rescans it **for every match** — O(n·m)
overall, plus a full string copy per match. On a file that produces many matches
this dominates the scan, and because both the slice and ``str.count`` run in C
it holds the GIL for the whole time with no yield point.

Measured on a synthetic file of repeated matches:

===========  ====================  =============  =======
matches      slice-per-match       precomputed    speedup
===========  ====================  =============  =======
2,000        0.073 s               0.004 s        17x
8,000        1.105 s               0.020 s        56x
20,000       6.928 s               0.040 s        174x
===========  ====================  =============  =======

Nearly 7 s of uninterruptible GIL hold at 20k matches, which is the shape of the
12 s event-loop stalls reported in #12866 (a ThreadPoolExecutor does not help:
the work never releases the GIL).
"""

from __future__ import annotations

from bisect import bisect_right

__all__ = ["LineIndex"]


class LineIndex:
    """Maps character offsets to 1-based line numbers for one piece of content.

    Build once per file, then query per match.
    """

    __slots__ = ("_starts",)

    def __init__(self, content: str) -> None:
        # Offset of the first character of each line. Line 1 starts at 0.
        starts = [0]
        idx = content.find("\n")
        while idx != -1:
            starts.append(idx + 1)
            idx = content.find("\n", idx + 1)
        self._starts = starts

    def line_of(self, offset: int) -> int:
        """Return the 1-based line number containing *offset*."""
        return bisect_right(self._starts, offset)

    def __len__(self) -> int:
        return len(self._starts)
