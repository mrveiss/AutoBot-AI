# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tool-call loop detection helpers for the chat graph (#3254).

Split out of ``chat_workflow/graph.py`` (#20195) to keep it under its size ceiling; ``graph`` re-exports
both helpers and the window constant, so ``graph._detect_tool_call_loop`` keeps working.
"""

import hashlib
import json
from typing import Any, Dict, List, Tuple

# Number of identical-fingerprint iterations required to declare a loop.
_LOOP_DETECTION_WINDOW: int = 3


def _fingerprint_tool_call(tool_call: Dict[str, Any]) -> str:
    """Return a stable string fingerprint for one tool call.

    The fingerprint is built from the tool name plus a SHA-1 digest of the
    canonically sorted JSON-serialised params dict.  Using a digest (rather
    than the raw params string) keeps fingerprints constant-length and avoids
    false negatives caused by key-ordering differences.

    Issue #3254: content-aware detection — two calls are considered identical
    when *both* the tool name and the arguments are the same.

    Args:
        tool_call: A parsed tool-call dict with at least a "name" key and an
                   optional "params" key (dict or scalar).

    Returns:
        A short string of the form ``"<name>:<hex_digest>"``.
    """
    name = tool_call.get("name", "")
    params = tool_call.get("params", {})
    try:
        canonical = json.dumps(params, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        canonical = str(params)
    digest = hashlib.sha1(canonical.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{name}:{digest}"


def _detect_tool_call_loop(
    new_fingerprints: List[str],
    history: List[str],
    window: int = _LOOP_DETECTION_WINDOW,
) -> Tuple[bool, List[str]]:
    """Detect whether the current iteration is a repetition of recent ones.

    A loop is declared when the last ``window - 1`` entries in ``history``
    are all identical to the current set of fingerprints.  This requires at
    least ``window`` consecutive identical iterations before triggering.

    Issue #3254: content-aware (not just count-based) — two iterations are
    considered identical only when they produce *the same tool calls in the
    same order*.

    Args:
        new_fingerprints: Fingerprint strings for the current iteration's
                          tool calls (one entry per tool call).
        history:          Accumulated per-iteration fingerprint strings from
                          previous iterations (each entry is one iteration's
                          comma-joined fingerprints).
        window:           How many identical consecutive iterations trigger
                          the loop alarm (default: ``_LOOP_DETECTION_WINDOW``).

    Returns:
        ``(is_loop, updated_history)`` where ``updated_history`` has the new
        iteration's fingerprint appended.
    """
    current_key = ",".join(new_fingerprints)
    updated = (list(history) + [current_key])[-window:]

    if len(updated) < window:
        return False, updated

    recent = updated[-(window):]
    is_loop = len(set(recent)) == 1 and recent[0] != ""
    return is_loop, updated
