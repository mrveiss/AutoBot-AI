# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Log-flood guard tests (#15774).

Every fixture here is synthetic: records are constructed in-process and fed to
the filter directly. The guard must never be exercised against live log volume
-- a test seeded from the condition it eliminates stops proving anything the
moment the guard works.
"""

import logging

from autobot_shared.logging_manager import LogFloodSuppressionFilter


def _record(level: int = logging.ERROR, msg: str = "redis unavailable: %s", args=("attempt-1",), lineno: int = 10):
    return logging.LogRecord(
        name="autobot.test",
        level=level,
        pathname="/srv/app/worker.py",
        lineno=lineno,
        msg=msg,
        args=args,
        exc_info=None,
    )


def test_identical_errors_are_bounded_and_counted():
    """10k identical errors emit a bounded number of lines, not 10k."""
    flt = LogFloodSuppressionFilter(threshold=5, window_seconds=3600)

    processed = 0
    emitted = 0
    for _ in range(10_000):
        processed += 1
        if flt.filter(_record()):
            emitted += 1

    # Vacuity floor is bound to records *processed*: if the loop ever stops
    # feeding the filter, this fails instead of passing on an empty run.
    assert processed == 10_000
    assert emitted == 5, f"expected the threshold to cap emission, got {emitted}"


def test_interpolated_ids_collapse_to_one_key():
    """Records differing only in an interpolated arg share one suppression key."""
    flt = LogFloodSuppressionFilter(threshold=2, window_seconds=3600)

    emitted = sum(1 for i in range(50) if flt.filter(_record(args=(f"attempt-{i}",))))

    assert emitted == 2, "the formatted message must not be part of the key"


def test_distinct_call_sites_are_tracked_separately():
    """One noisy site must not silence a different, healthy one."""
    flt = LogFloodSuppressionFilter(threshold=1, window_seconds=3600)

    assert flt.filter(_record(lineno=10)) is True
    assert flt.filter(_record(lineno=10)) is False
    assert flt.filter(_record(lineno=99)) is True


def test_critical_is_never_suppressed():
    """The line that explains an outage always survives."""
    flt = LogFloodSuppressionFilter(threshold=1, window_seconds=3600)

    processed = 0
    emitted = 0
    for _ in range(1_000):
        processed += 1
        if flt.filter(_record(level=logging.CRITICAL)):
            emitted += 1

    assert processed == 1_000
    assert emitted == 1_000


def test_info_is_untouched():
    """Suppression applies to WARNING+ only."""
    flt = LogFloodSuppressionFilter(threshold=1, window_seconds=3600)

    assert all(flt.filter(_record(level=logging.INFO)) for _ in range(100))


def test_window_rollover_reports_the_suppressed_count():
    """The first record of the next window carries what the last one hid."""
    flt = LogFloodSuppressionFilter(threshold=1, window_seconds=0)  # every record starts a new window

    first = _record()
    assert flt.filter(first) is True
    assert not hasattr(first, "flood_suppressed")

    flt_windowed = LogFloodSuppressionFilter(threshold=1, window_seconds=3600)
    assert flt_windowed.filter(_record()) is True
    for _ in range(9):
        assert flt_windowed.filter(_record()) is False

    # Force the window closed without sleeping: the guard keys off a monotonic
    # start stamp, so rewinding it is equivalent to the window elapsing.
    for entry in flt_windowed._state.values():
        entry[0] -= 3601

    reopened = _record()
    assert flt_windowed.filter(reopened) is True
    assert reopened.flood_suppressed == 9
    assert "9 identical records suppressed" in reopened.msg


def test_state_map_is_bounded():
    """The guard cannot itself leak memory on high-cardinality call sites."""
    flt = LogFloodSuppressionFilter(threshold=1, window_seconds=3600, max_keys=16)

    for i in range(500):
        flt.filter(_record(lineno=i))

    assert len(flt._state) <= 16
