# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical monotonic clock for in-process TTL and elapsed-time decisions (#18888).

``time.time()`` follows the wall clock, which can step backward (NTP, VM
host sync). An elapsed-time check built on it can then keep a TTL entry
alive past its expiry. Use ``monotonic_now`` for any value that is only
ever compared against another reading from the same process. Persisted or
cross-process timestamps stay wall time (``time.time()`` / ``utc_timestamp``).

Tests inject a ``Clock`` (a zero-argument callable returning seconds, e.g.
``FakeClock``) instead of sleeping.
"""

import time
from typing import Callable

Clock = Callable[[], float]


def monotonic_now() -> float:
    """Return the current monotonic time in seconds (default ``Clock``)."""
    return time.monotonic()


def elapsed_since(start: float, clock: Clock = monotonic_now) -> float:
    """Return seconds elapsed since ``start`` (a reading from ``clock``)."""
    return clock() - start


class FakeClock:
    """Manually advanced clock for tests; satisfies the ``Clock`` protocol."""

    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        """Move the clock forward by ``seconds``."""
        self._now += seconds
