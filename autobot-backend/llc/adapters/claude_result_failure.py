# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading a Claude CLI stream-json transcript for a failed run (#20202).

The CLI writes ``subtype="success"`` next to ``is_error=true`` on an API error,
so the subtype alone proves nothing. Detection here reads structured fields,
never message text, and never returns transcript content.
"""

from __future__ import annotations

import json

from .base import BILLING_API, BILLING_SUBSCRIPTION
from .subprocess_support import final_result_event

# Upper bound for the fallback read of a result line larger than the scan tail.
_WIDE_TAIL_BYTES = 1024 * 1024
# The init event is the stream's first line; it is a few KB at most.
_INIT_HEAD_BYTES = 256 * 1024

_AUTH_FAILED_ERROR_CODE = "authentication_failed"
# 401 only. 403 is deliberately not treated as auth: this CLI's own output does not
# establish what a 403 means (expired login vs. a permission or policy refusal), and
# pausing/flagging an agent for re-login on a refusal re-login cannot fix would be wrong.
_AUTH_FAILED_HTTP_STATUS = 401
_MAX_TURNS_SUBTYPE = "error_max_turns"


def read_wide_tail(output_file: str) -> str:
    """Last ``_WIDE_TAIL_BYTES`` of *output_file*; ``""`` when unreadable."""
    try:
        with open(output_file, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - _WIDE_TAIL_BYTES))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def resolve_result_event(output_file: str, tail: str) -> tuple[dict | None, str]:
    """Return ``(result_event, text_it_came_from)``.

    A result line longer than the scan tail fails to parse there and would read as
    "no result" (and so as COMPLETED). Only when the tail has none, re-read wider.
    """
    event = final_result_event(tail)
    if event is not None:
        return event, tail
    wide = read_wide_tail(output_file)
    return final_result_event(wide), wide


def run_billing(output_file: str) -> str | None:
    """How the CLI authenticated this run, from the ``system``/``init`` event (#20266).

    The init event is the first line of the stream and carries ``apiKeySource``:
    ``"none"`` when the CLI holds no API key (it is on a login), else where the key
    came from. ``None`` when the event or field is missing: unknown is not subscription.
    """
    try:
        with open(output_file, "rb") as fh:
            head = fh.read(_INIT_HEAD_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return None
    for line in head.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "system" and event.get("subtype") == "init":
            source = event.get("apiKeySource")
            if not isinstance(source, str):
                return None
            return BILLING_SUBSCRIPTION if source == "none" else BILLING_API
    return None


def is_failed_result_event(result_event: dict | None) -> bool:
    """True for a final result event that reports failure."""
    if not isinstance(result_event, dict):
        return False
    return bool(result_event.get("is_error")) or result_event.get("subtype") != "success"


def is_turn_limit_result(result_event: dict | None) -> bool:
    """True when the run stopped on the CLI's turn limit."""
    return isinstance(result_event, dict) and result_event.get("subtype") == _MAX_TURNS_SUBTYPE


def is_auth_failure_output(text: str, result_event: dict | None = None) -> bool:
    """True when the CLI's structured fields say authentication failed.

    An assistant event carries ``error == "authentication_failed"``; a result
    event carries ``api_error_status == 401``. Lines are parsed, so the code
    appearing inside a quoted string (tool output) does not count.
    """
    if isinstance(result_event, dict) and result_event.get("api_error_status") == _AUTH_FAILED_HTTP_STATUS:
        return True
    for line in text.splitlines():
        if _AUTH_FAILED_ERROR_CODE not in line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("type") == "assistant" and obj.get("error") == _AUTH_FAILED_ERROR_CODE:
            return True
    return False
