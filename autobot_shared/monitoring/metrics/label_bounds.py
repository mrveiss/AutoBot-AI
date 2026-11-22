# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bound the label values a metric may take from untrusted input (#18368).

Every distinct label value is a new Prometheus series, held in the process
registry until restart and in the TSDB for its retention. The frontend RUM
recorder takes its labels from ``POST /api/rum/metrics``, which is open by
design (#16375), so an anonymous caller choosing values would choose how many
series exist. These bounds make that number fixed:

* a value that is empty, longer than ``AUTOBOT_RUM_LABEL_MAX_CHARS`` or not
  plain printable text records as ``other``;
* a label with a known vocabulary (HTTP method) records anything outside it as
  ``other``;
* every other label admits its first ``AUTOBOT_RUM_LABEL_MAX_VALUES`` distinct
  values and records each later new one as ``other``.

So each label has at most ``AUTOBOT_RUM_LABEL_MAX_VALUES + 1`` values, whatever
is sent. The cost is stated rather than hidden: a flood that arrives before
legitimate traffic fills the vocabulary, and later legitimate values then read
as ``other`` -- a degraded dashboard, never an unbounded registry.
"""

from __future__ import annotations

import re
import threading
from typing import Dict, FrozenSet, Set

OTHER = "other"

_PRINTABLE = re.compile(r"[\x21-\x7e][\x20-\x7e]*")

#: Labels whose whole vocabulary is known; anything else is ``other``.
CLOSED_VOCABULARIES: Dict[str, FrozenSet[str]] = {
    "method": frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}),
}


def _limit(name: str) -> int:
    """A registered int setting, imported late: the registry's import chain loads
    ``logging_manager``, which this module -- imported by every metrics manager --
    must not drag into processes and test harnesses that never record RUM."""
    from autobot_shared.env_registry import env

    return int(env(name))


class BoundedLabels:
    """Map untrusted label values onto a per-label vocabulary of fixed size."""

    def __init__(self) -> None:
        self._seen: Dict[str, Set[str]] = {}
        self._lock = threading.Lock()

    def bound(self, label: str, value: object) -> str:
        """The value to record for *label*: *value* itself, or ``other``."""
        text = str(value if value is not None else "").strip()
        if len(text) > _limit("AUTOBOT_RUM_LABEL_MAX_CHARS") or not _PRINTABLE.fullmatch(text):
            return OTHER
        closed = CLOSED_VOCABULARIES.get(label)
        if closed is not None:
            return text if text.upper() in closed else OTHER
        return self._admit(label, text)

    def _admit(self, label: str, text: str) -> str:
        with self._lock:
            seen = self._seen.setdefault(label, set())
            if text in seen:
                return text
            if len(seen) >= _limit("AUTOBOT_RUM_LABEL_MAX_VALUES"):
                return OTHER
            seen.add(text)
            return text


__all__ = ["BoundedLabels", "CLOSED_VOCABULARIES", "OTHER"]
