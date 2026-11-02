# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What a duplicate scan can answer instead of an analysis (#18013).

``_run_duplicate_analysis`` used to signal "no analysis" with ``None`` from two
places -- the single-flight lock being held, and a real deadline expiring -- and
every caller reported the *timeout* reason. A request that returned in 0.2 s
because a scan was already running therefore claimed "timed out after 120s",
with advice (raise ``min_similarity``) that cannot help a caller who is merely
queued behind a running scan.

The two reasons are distinct raised types now, defined together so the pair
stays visibly a pair: a third outcome is added next to these, not as a second
``None``.
"""

from dataclasses import dataclass

from autobot_shared.env_utils import env_float

#: How long an abandoned scan may keep the single-flight lock after it has been
#: told to stop. The lock is released by the executor thread's done-callback
#: (#13602); if that thread never exits, the callback never fires and every later
#: call is declined for the life of the process. Past this lease the lock is
#: treated as leaked and replaced (#18013).
ORPHAN_LEASE_SECONDS = env_float("AUTOBOT_DUPLICATE_ORPHAN_LEASE_SECONDS", 300.0)

#: Upper bound for a scan run by the background (Celery) task. It is a bound on
#: a runaway, not the request deadline: the queued path exists precisely to
#: escape ``DUPLICATE_DETECTION_TIMEOUT``, and applying that cap there made it
#: report ``completed`` for a scan that examined nothing (#18067).
BACKGROUND_SCAN_TIMEOUT_SECONDS = env_float("AUTOBOT_DUPLICATE_BACKGROUND_TIMEOUT_SECONDS", 3600.0)


class ScanUnavailable(Exception):
    """A duplicate scan produced no analysis. Subclasses say why."""


class ScanBusy(ScanUnavailable):
    """No scan was started: one was already in flight (#12779)."""

    def __init__(self, elapsed_seconds: float | None) -> None:
        super().__init__("a duplicate scan is already in flight")
        self.elapsed_seconds = elapsed_seconds


class ScanTimedOut(ScanUnavailable):
    """The scan ran and exceeded its deadline."""

    def __init__(self, deadline_seconds: float) -> None:
        super().__init__(f"duplicate scan exceeded its {deadline_seconds}s deadline")
        self.deadline_seconds = deadline_seconds


@dataclass
class ScanHolder:
    """Who holds the single-flight lock, kept so a refusal can say for how long."""

    started: float
    orphaned_at: float | None = None


def build_timeout_response(deadline_seconds: float) -> dict:
    """The scan started, ran, and exceeded ``deadline_seconds``."""
    return {
        "status": "partial",
        "message": f"Analysis timed out after {deadline_seconds}s. Try a higher min_similarity threshold.",
        "duplicates": [],
        "total_count": 0,
        "storage_type": "timeout",
    }


def build_busy_response(elapsed_seconds: float | None) -> dict:
    """No scan was started: one was already in flight.

    ``elapsed_seconds`` is how long the holding scan has been running. It is
    reported because it is the only way to tell a scan that is merely slow from
    a guard that is never released.
    """
    age = f"for {elapsed_seconds:.0f}s" if elapsed_seconds is not None else "since before this process could tell"
    return {
        "status": "busy",
        "message": (
            f"A duplicate scan has been running {age}; this request was not queued behind it. "
            "Retry shortly. min_similarity does not affect this -- the scan in flight owns the walk."
        ),
        "duplicates": [],
        "total_count": 0,
        "storage_type": "in_flight",
    }


def response_for(exc: ScanUnavailable) -> dict:
    """The terminal payload for a scan that produced no analysis."""
    if isinstance(exc, ScanBusy):
        return build_busy_response(exc.elapsed_seconds)
    if isinstance(exc, ScanTimedOut):
        return build_timeout_response(exc.deadline_seconds)
    raise TypeError(f"no response defined for {type(exc).__name__}") from exc
