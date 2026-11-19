# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Measured duration of a tool call, from the end of its BEFORE hook to its AFTER hook (#21879).

Every tool site emits ``BEFORE_TOOL_EXECUTE``, runs the tool, then emits
``AFTER_TOOL_EXECUTE`` (or ``TOOL_ERROR``). The emitters in ``llm_handler`` mark the start
and read the elapsed time here, so each call site reports a real duration without carrying a
timer of its own. A call whose start was never marked has no duration: ``None``, never ``0``.
"""

from __future__ import annotations

import time
from collections import OrderedDict

#: Calls marked but never closed (a cancelled turn) are evicted oldest-first beyond this many.
_MAX_OPEN_CALLS = 1024

_open_calls: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()


def mark_tool_started(session_id: str | None, tool_name: str) -> None:
    """Record that *tool_name* began executing in *session_id* just now."""
    _open_calls.setdefault((session_id or "", tool_name), []).append(time.monotonic())
    while len(_open_calls) > _MAX_OPEN_CALLS:
        _open_calls.popitem(last=False)


def take_tool_elapsed(session_id: str | None, tool_name: str) -> float | None:
    """Seconds since the oldest open start of *tool_name* in *session_id*, closing it; None when none was marked."""
    key = (session_id or "", tool_name)
    starts = _open_calls.get(key)
    if not starts:
        return None
    started = starts.pop(0)
    if not starts:
        del _open_calls[key]
    return time.monotonic() - started


def tool_outcome_fields(elapsed: float | None, success: bool | None) -> dict[str, float | bool]:
    """The ``execution_time`` / ``success`` hook-data keys for the values that are known; unknown ones are omitted."""
    fields: dict[str, float | bool] = {}
    if elapsed is not None:
        fields["execution_time"] = elapsed
    if success is not None:
        fields["success"] = success
    return fields
