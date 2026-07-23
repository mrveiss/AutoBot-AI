# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10601: the async feedback endpoints must not call the synchronous
FeedbackTracker (blocking `with self.SessionLocal()`) directly on the event
loop. Every blocking tracker call is offloaded via asyncio.to_thread. This guard
fails if an offload is dropped, re-introducing event-loop blocking."""

from __future__ import annotations

import re
from pathlib import Path

_SRC = (Path(__file__).parent / "feedback.py").read_text(encoding="utf-8")

# Tracker methods that open a blocking sync-DB session — must never run inline
# on the event loop. mark_retrain_completed runs inside a BackgroundTasks worker
# (already off-loop), so it is intentionally excluded.
_BLOCKING = {"record_feedback", "get_acceptance_metrics", "get_recent_feedback"}


def test_asyncio_imported():
    assert "import asyncio" in _SRC


def test_blocking_tracker_methods_never_called_inline():
    # A direct call is `_get_feedback_tracker().<method>(`; an offloaded call
    # passes the bound method as a reference (`.<method>,`) to to_thread.
    direct_calls = set(re.findall(r"_get_feedback_tracker\(\)\.(\w+)\(", _SRC))
    leaked = direct_calls & _BLOCKING
    assert not leaked, f"blocking tracker methods called inline on the loop: {sorted(leaked)}"


def test_each_blocking_method_is_offloaded_via_to_thread():
    for method in _BLOCKING:
        assert re.search(
            rf"to_thread\(\s*_get_feedback_tracker\(\)\.{method}\b", _SRC
        ), f"{method} is not offloaded via asyncio.to_thread"
