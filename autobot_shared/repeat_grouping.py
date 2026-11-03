# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Group repeated audit records: one record per key per window, carrying the repeats it absorbed.

Used where a caller can trigger an audit row on every request, so repeats can't flood the store
while each refusal is still counted: the SLM's refused sessions (#20664) and the backend's
role denials (#16333). Per process, so rows are bounded by workers x keys x windows. The tracked
set is capped; when it is full, the keys dropped to make room lose their unreported counts and may
get an extra record, which is the safe way round.
"""

from __future__ import annotations

import time
from collections.abc import Hashable

DEFAULT_MAX_TRACKED = 10_000


class RepeatGrouper:
    """Decides whether a repeat of *key* gets its own record, and how many repeats it carries."""

    def __init__(self, window_s: float, max_tracked: int = DEFAULT_MAX_TRACKED) -> None:
        self.window_s = window_s
        self.max_tracked = max_tracked
        # key -> (when its last record was written, repeats since that weren't recorded)
        self._recent: dict[Hashable, tuple[float, int]] = {}

    def _forget_old(self, now: float) -> None:
        for key in [k for k, (at, _) in self._recent.items() if now - at >= self.window_s]:
            del self._recent[key]

    def repeats_to_record(self, key: Hashable) -> int | None:
        """Repeats since the last record if this one should be written, else None."""
        now = time.monotonic()
        seen = self._recent.get(key)
        if seen and now - seen[0] < self.window_s:
            self._recent[key] = (seen[0], seen[1] + 1)
            return None
        if len(self._recent) >= self.max_tracked:
            self._forget_old(now)
        if len(self._recent) >= self.max_tracked:
            self._recent.pop(next(iter(self._recent)))
        self._recent[key] = (now, 0)
        return seen[1] if seen else 0
