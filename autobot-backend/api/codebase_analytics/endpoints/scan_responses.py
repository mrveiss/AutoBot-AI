# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Terminal responses for a duplicate scan that produced no analysis.

#18013: there are two reasons ``_run_duplicate_analysis`` yields nothing, and
until now both were signalled by ``None``. Every caller therefore reported the
*timeout* reason, including for requests that returned in 0.2s because a scan
was already in flight -- a message asserting a 120-second deadline that had not
elapsed, with advice (raise ``min_similarity``) that cannot help a caller who is
merely behind a running scan.

The two live here together so the pair stays visibly a pair: adding a third
outcome means adding it next to these, not inventing a second ``None``.
"""

from constants.threshold_constants import AnalyticsConfig


def build_timeout_response() -> dict:
    """The scan started, ran, and exceeded ``DUPLICATE_DETECTION_TIMEOUT``."""
    return {
        "status": "partial",
        "message": (
            f"Analysis timed out after {AnalyticsConfig.DUPLICATE_DETECTION_TIMEOUT}s. "
            "Try a higher min_similarity threshold."
        ),
        "duplicates": [],
        "total_count": 0,
        "storage_type": "timeout",
    }


def build_busy_response(elapsed_seconds: float | None) -> dict:
    """No scan was started: one was already in flight (#12779 single-flight).

    ``elapsed_seconds`` is how long the holding scan has been running, or None
    when that is not known to the caller. It is reported because it is the only
    way to tell a scan that is merely slow from a guard that is never released
    -- a distinction this endpoint previously made impossible to observe, since
    both looked like an instant "timed out after 120s".
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
