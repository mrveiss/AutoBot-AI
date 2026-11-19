# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Measured duration of a tool call, from the end of its BEFORE hook to its AFTER hook (#21879).

Every tool site emits ``BEFORE_TOOL_EXECUTE``, runs the tool, then emits ``AFTER_TOOL_EXECUTE`` (or ``TOOL_ERROR``).
``mark_tool_started`` returns a token naming THAT call; the token rides a ``ContextVar`` of the task running the
call, so two concurrent calls of one tool in one session each read their own start (a shared first-in-first-out
queue swapped their durations). A start that is never closed (an after-hook that never fired) is dropped once it is
older than ``TOOL_TIMING_MAX_AGE_SECONDS``. A call with no start has no duration: ``None``, never ``0``.
"""

from __future__ import annotations

import contextvars
import itertools
import time
from collections import OrderedDict
from typing import Dict, Tuple

from autobot_shared.env_utils import env_float

#: Seconds after which an unclosed start is discarded, so a missed after-hook leaves no stale entry (#21879).
TOOL_TIMING_MAX_AGE_SECONDS: float = env_float("AUTOBOT_TOOL_TIMING_MAX_AGE_SECONDS", default=3600.0)

#: Open starts, oldest first; also bounded in count (a cancelled turn closes nothing).
_MAX_OPEN_CALLS = 1024

_tokens = itertools.count(1)
_open_calls: "OrderedDict[int, float]" = OrderedDict()
#: (session, tool) -> token, as seen by the task that marked the call.
_current: "contextvars.ContextVar[Dict[Tuple[str, str], int]]" = contextvars.ContextVar("tool_timing_current")


def _expire(now: float) -> None:
    while _open_calls:
        token, started = next(iter(_open_calls.items()))
        if now - started <= TOOL_TIMING_MAX_AGE_SECONDS and len(_open_calls) <= _MAX_OPEN_CALLS:
            break
        del _open_calls[token]


def mark_tool_started(session_id: str | None, tool_name: str) -> int:
    """Record that *tool_name* began executing in *session_id* just now; returns the call's token."""
    now = time.monotonic()
    _expire(now)
    token = next(_tokens)
    _open_calls[token] = now
    _current.set({**_current.get({}), (session_id or "", tool_name): token})
    return token


def take_tool_elapsed(session_id: str | None, tool_name: str, token: int | None = None) -> float | None:
    """Seconds since the call's start, closing it; None when it was never marked or its start expired.

    *token* names the call; without one the token the calling task marked for this session and tool is used.
    """
    key = (session_id or "", tool_name)
    if token is None:
        token = _current.get({}).get(key)
    if token is not None:
        _current.set({k: v for k, v in _current.get({}).items() if v != token})
    started = _open_calls.pop(token, None) if token is not None else None
    return None if started is None else time.monotonic() - started


def tool_outcome_fields(elapsed: float | None, success: bool | None) -> dict[str, float | bool]:
    """The ``execution_time`` / ``success`` hook-data keys for the values that are known; unknown ones are omitted."""
    fields: dict[str, float | bool] = {}
    if elapsed is not None:
        fields["execution_time"] = elapsed
    if success is not None:
        fields["success"] = success
    return fields
