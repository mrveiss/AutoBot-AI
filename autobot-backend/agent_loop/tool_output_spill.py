# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Context offload for oversized tool output — spill and anchor (#13692, step 1).

Tool output enters the model's context whole and stays there for the rest of the
run. Nothing puts a large observation somewhere else and leaves a reference
behind: every ``offload`` in the backend is *compute* offload
(``services/npu_client.py``, ``services/execution/modal_backend.py``), and
``agent_loop/loop.py`` fingerprints observations for novelty (#6627) but never
for size.

What this does: a tool result above a threshold is written to a run-scoped
artifact on disk, and what enters context is a bounded excerpt plus a stable
anchor the agent can re-read on demand.

What this deliberately does **not** do, per #13692's two-step split:

* no task-state canvas and no compaction changes — step 2, gated on measuring
  step 1, and only if the measurement justifies coupling to the compactor;
* no new service, no LLM call, no summarisation. An excerpt is a slice, not a
  summary, so nothing here can hallucinate.

Off by default, following #12555's precedent: a context mechanism ships
flag-off until a benchmark shows the win.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Env-tunable, never hard-coded (CLAUDE.md).
SPILL_ENABLED: bool = os.environ.get("AUTOBOT_TOOL_OUTPUT_SPILL", "").lower() in ("1", "true", "yes")
SPILL_THRESHOLD_CHARS: int = int(os.environ.get("AUTOBOT_TOOL_OUTPUT_SPILL_THRESHOLD", "8000"))
SPILL_EXCERPT_CHARS: int = int(os.environ.get("AUTOBOT_TOOL_OUTPUT_SPILL_EXCERPT", "2000"))
SPILL_ROOT: str = os.environ.get("AUTOBOT_TOOL_OUTPUT_SPILL_ROOT", "data/tool_output_spill")

_ANCHOR_PREFIX = "autobot:spill"


def _anchor(task_id: str, tool_name: str, payload: str) -> str:
    """Stable, collision-resistant anchor for one spilled observation.

    Content-addressed on the payload so an identical result re-spilled in the
    same run reuses its artifact instead of accumulating duplicates.
    """
    digest = hashlib.sha256(f"{tool_name}:{payload}".encode("utf-8")).hexdigest()[:16]
    return f"{_ANCHOR_PREFIX}:{task_id}:{tool_name}:{digest}"


def _artifact_path(anchor: str) -> Path:
    """Filesystem location for an anchor. Never trusts the anchor's own text."""
    digest = hashlib.sha256(anchor.encode("utf-8")).hexdigest()
    # The anchor is not a path component: hashing it means a tool name
    # containing "../" cannot escape the spill root.
    return Path(SPILL_ROOT) / digest[:2] / f"{digest}.json"


def _serialise(result: Any) -> str:
    """Render a tool result as the text that would have entered context."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)


def spill_if_oversized(task_id: str, tool_name: str, result: Any) -> Tuple[Any, bool]:
    """Return ``(context_value, spilled)`` for one tool result.

    When the rendered result is under the threshold — or the feature is off —
    the original object is returned untouched, so a run that never trips the
    threshold is byte-identical to one without this module.

    Spill failure is non-fatal: the full result is returned and the turn
    proceeds. Losing the offload is always better than losing the observation.
    """
    if not SPILL_ENABLED:
        return result, False

    payload = _serialise(result)
    if len(payload) <= SPILL_THRESHOLD_CHARS:
        return result, False

    anchor = _anchor(task_id, tool_name, payload)
    try:
        path = _artifact_path(anchor)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"anchor": anchor, "task_id": task_id, "tool": tool_name, "output": payload}),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Tool-output spill failed for %s (keeping full output): %s", tool_name, exc)
        return result, False

    logger.info(
        "Spilled %s output: %d -> %d chars, anchor=%s (#13692)",
        tool_name,
        len(payload),
        SPILL_EXCERPT_CHARS,
        anchor,
    )
    return _excerpt_payload(anchor, tool_name, payload), True


def _excerpt_payload(anchor: str, tool_name: str, payload: str) -> Dict[str, Any]:
    """What enters context in place of the full output."""
    return {
        "spilled": True,
        "tool": tool_name,
        "anchor": anchor,
        "excerpt": payload[:SPILL_EXCERPT_CHARS],
        "omitted_chars": len(payload) - SPILL_EXCERPT_CHARS,
        "note": (
            f"Output truncated to {SPILL_EXCERPT_CHARS} of {len(payload)} chars. "
            f"Read the full output with the read_spilled_output tool using anchor {anchor!r}."
        ),
    }


def read_spilled(anchor: str) -> str | None:
    """Return the full spilled output for *anchor*, or None.

    This is what makes the anchor a reference rather than a deletion — the AC
    requires the agent to be able to retrieve the full output within the run.
    """
    if not isinstance(anchor, str) or not anchor.startswith(_ANCHOR_PREFIX):
        return None
    try:
        path = _artifact_path(anchor)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("output")
    except Exception as exc:
        logger.warning("Failed to read spilled output for %s: %s", anchor, exc)
        return None


def spill_results(task_id: str, tool_results: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """Apply :func:`spill_if_oversized` across a tool-result mapping.

    Returns the (possibly rewritten) mapping and how many entries were spilled,
    so the caller can report the reduction rather than shrinking the context
    silently.
    """
    if not SPILL_ENABLED or not tool_results:
        return tool_results, 0

    rewritten: Dict[str, Any] = {}
    spilled_count = 0
    for name, value in tool_results.items():
        rewritten[name], was_spilled = spill_if_oversized(task_id, name, value)
        spilled_count += int(was_spilled)
    return rewritten, spilled_count


__all__ = [
    "SPILL_ENABLED",
    "SPILL_EXCERPT_CHARS",
    "SPILL_THRESHOLD_CHARS",
    "read_spilled",
    "spill_if_oversized",
    "spill_results",
]
