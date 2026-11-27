# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Older continuation steps enter the next prompt as a digest plus an anchor, not in full (#16621).

Step k used to be re-sent in full on every later iteration, so a prompt grew roughly quadratically with the
loop. The newest ``KEEP_FULL_STEPS`` steps stay whole; each older one keeps its status and return code, the head
and the tail of its output (where a failure usually is), and an anchor. The full output is written to the
tool-output spill artifact store at collapse time, whatever ``AUTOBOT_TOOL_OUTPUT_SPILL`` says, and is read back
with ``read_spilled_output``. A step is left whole when it is already short, when no run is bound to the
context (nothing could read the anchor), or when the artifact could not be written.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

from agent_loop.tool_output_spill import current_task_id, spill_for_collapse
from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Newest steps rendered in full in a continuation prompt (#16621); older ones are collapsed.
KEEP_FULL_STEPS: int = max(1, env_int("AUTOBOT_CHAT_CONTINUATION_FULL_STEPS", 3))
#: Characters of a collapsed step's output kept at EACH end (head and tail).
DIGEST_END_CHARS: int = max(1, env_int("AUTOBOT_CHAT_COLLAPSED_STEP_END_CHARS", 300))

_OUTPUT_KEYS = ("stdout", "stderr", "output", "result", "error", "reason")


def _text(value: Any) -> str:
    if value is None or value == "":
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)


def step_output_text(result: Dict[str, Any]) -> str:
    """Everything a step printed or reported, as the text its anchor will return."""
    return "\n".join(t for t in (_text(result.get(key)) for key in _OUTPUT_KEYS) if t)


def _digest(text: str, anchor: str) -> str:
    head, tail = text[:DIGEST_END_CHARS], text[-DIGEST_END_CHARS:]
    omitted = len(text) - len(head) - len(tail)
    return (
        f"{head}\n[... {omitted} chars collapsed. Read the full output with read_spilled_output, "
        f"anchor {anchor!r} ...]\n{tail}"
    )


def collapse_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """*result* with its output replaced by a digest and anchor; *result* itself when collapsing gains nothing."""
    text = step_output_text(result)
    run = current_task_id()
    if run is None or len(text) <= 2 * DIGEST_END_CHARS + 200:
        return result
    anchor = spill_for_collapse(run, str(result.get("command") or result.get("tool") or "step"), text)
    if anchor is None:
        return result
    cleared = {key: "" for key in _OUTPUT_KEYS}
    return {**result, **cleared, "stdout": _digest(text, anchor)}


def render_history(format_step: Callable[[int, Dict[str, Any]], str], history: List[Dict[str, Any]]) -> List[str]:
    """Each step rendered by *format_step*; all but the newest ``KEEP_FULL_STEPS`` collapsed first."""
    older = len(history) - KEEP_FULL_STEPS
    return [format_step(i, collapse_result(r) if i <= older else r) for i, r in enumerate(history, 1)]
