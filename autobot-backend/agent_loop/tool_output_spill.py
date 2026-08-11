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

import asyncio
import hashlib
import json
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _int_env(name: str, default: int) -> int:
    """Parse an int env var, falling back loudly rather than at import (#13865).

    These are read at module scope, and this module is imported by
    ``agent_loop.loop``. An unparseable value used to raise ``ValueError``
    during import and take down everything importing the agent loop — with the
    feature switched off.
    """
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; using %d", name, raw, default)
        return default


# Env-tunable, never hard-coded (CLAUDE.md).
SPILL_ENABLED: bool = os.environ.get("AUTOBOT_TOOL_OUTPUT_SPILL", "").lower() in ("1", "true", "yes")
SPILL_THRESHOLD_CHARS: int = max(1, _int_env("AUTOBOT_TOOL_OUTPUT_SPILL_THRESHOLD", 8000))
# Rough fixed cost of an excerpt payload. Deliberately an ESTIMATE and
# deliberately NOT the safety mechanism: measured overhead ranges 286-1710 chars
# depending on tool-name length and how much JSON re-escapes the classification
# markers, so no constant can be correct. `spill_if_oversized` measures the real
# replacement and declines to spill if it would not be smaller — this clamp only
# keeps the default configuration sensible so that check rarely has to fire.
_EXCERPT_OVERHEAD_CHARS = 400 + 3 * 200
SPILL_EXCERPT_CHARS: int = max(
    1,
    min(
        _int_env("AUTOBOT_TOOL_OUTPUT_SPILL_EXCERPT", 2000),
        max(1, SPILL_THRESHOLD_CHARS - _EXCERPT_OVERHEAD_CHARS),
    ),
)
# Largest payload written to disk. Above this the stored copy is truncated and
# marked — serialise + json.dumps + utf-8 encode peaks at roughly 3-4x the
# payload, so an unbounded result was an unbounded allocation.
SPILL_MAX_ARTIFACT_CHARS: int = max(1, _int_env("AUTOBOT_TOOL_OUTPUT_SPILL_MAX", 5_000_000))
_TRUNCATION_MARKER = "\n[artifact truncated: output exceeded AUTOBOT_TOOL_OUTPUT_SPILL_MAX]"
# Ceiling on a single re-read. Without it `limit=99999999` hands the whole
# artifact straight back into context, undoing the offload.
SPILL_MAX_WINDOW_CHARS: int = max(1, _int_env("AUTOBOT_TOOL_OUTPUT_SPILL_MAX_WINDOW", 8000))

_ANCHOR_PREFIX = "autobot:spill"

# The run whose artifacts the current execution context may read. Set by the
# agent loop; never taken from tool arguments (#13865). The anchor embeds its
# owning task id in plaintext, so accepting a caller-supplied task_id let anyone
# holding an anchor read the run it came from by echoing back the id inside it.
_current_task_id: ContextVar[str | None] = ContextVar("autobot_spill_task_id", default=None)


def bind_task(task_id: str | None) -> None:
    """Declare which run the current context is executing.

    Called by the agent loop. Reads are scoped to this value.
    """
    _current_task_id.set(task_id)


def current_task_id() -> str | None:
    """The server-side run id, or None when nothing has been bound."""
    return _current_task_id.get()


def _spill_root() -> Path:
    """Absolute spill directory.

    Resolved through the canonical data path rather than a relative literal: a
    relative default resolves against the process CWD, which put artifacts
    inside the deployed install tree for the backend and somewhere else entirely
    for any worker started from a different directory (#13149's class of bug).
    """
    override = os.environ.get("AUTOBOT_TOOL_OUTPUT_SPILL_ROOT")
    if override:
        # Resolved: a relative override would reintroduce the CWD dependency
        # this function exists to remove.
        return Path(override).expanduser().resolve()
    from constants.path_constants import PATH

    return PATH.get_data_path("tool_output_spill")


def sweepable_spill_root() -> Path | None:
    """The spill root, but only when AutoBot owns the directory.

    The nightly cleanup recursively unlinks everything older than its TTL, and
    the other directories it sweeps (``data/cache``, ``TEMP_DIR``) are
    AutoBot-owned by construction. This one is not: the operator picks it. A
    root pointed at a shared scratch directory or a mounted volume would have
    the sweep delete unrelated files on its first run — immediately, since the
    criterion is mtime alone and pre-existing files are already old.

    So an operator-chosen root is never swept automatically. Only the default
    under ``DATA_DIR`` is, and only once the spill has actually created it —
    which also means an operator who sets the root while the feature is off does
    not get their directory swept by a feature that never wrote a byte.
    """
    if os.environ.get("AUTOBOT_TOOL_OUTPUT_SPILL_ROOT"):
        return None
    root = _spill_root()
    return root if root.is_dir() else None


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
    return _spill_root() / digest[:2] / f"{digest}.json"


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

    # MEASURE the replacement; never estimate it. This module's whole purpose is
    # "what enters context is smaller than what it replaced", and that property
    # was broken three times running because each fix reasoned about the *shape*
    # in the last bug report instead of checking the result: the value was copied
    # verbatim, then only `str` was bounded, then the overhead was estimated by a
    # hardcoded constant that is 2-6x too low once JSON re-escapes the markers.
    #
    # A control-char-dense string still inverted at the default configuration
    # (8,001 -> 12,282 chars), because `_serialise` returns a str raw while the
    # excerpt slice gets escaped. One comparison makes every value type, shape,
    # escaping mode and env configuration safe by construction, so there is no
    # round five.
    excerpt = _excerpt_payload(anchor, tool_name, payload, result)
    if len(_serialise(excerpt)) >= len(payload):
        logger.debug(
            "Not spilling %s: the excerpt would not be smaller than the output (%d chars)",
            tool_name,
            len(payload),
        )
        return result, False

    # Marked, not silently sliced: the excerpt's note quotes the *original*
    # length, so an unmarked truncation makes the artifact contradict it.
    truncated = len(payload) > SPILL_MAX_ARTIFACT_CHARS
    stored = payload[:SPILL_MAX_ARTIFACT_CHARS] + _TRUNCATION_MARKER if truncated else payload
    try:
        path = _artifact_path(anchor)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"anchor": anchor, "task_id": task_id, "tool": tool_name, "output": stored},
                ensure_ascii=False,
            ),
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
    return _excerpt_payload(anchor, tool_name, payload, result), True


# Keys that classify a result rather than describe it. They must survive the
# spill: the agent loop decides success (`_should_iterate`) and whether to
# record an observation (`_record_observation_fingerprints`) by looking for
# exactly these, so dropping them turned a large tool *failure* into a success
# and fed it into the novelty window (#13865).
#
# Only `error` is read by the loop today; `status`/`success` are carried for
# consumers that may key on them. Whatever is carried must be BOUNDED — see
# `_classification_marker`.
_CLASSIFYING_KEYS = ("error", "status", "success")


_CLASSIFICATION_MARKER_CHARS = 200


def _classification_marker(value: Any) -> Any:
    """Preserve what a value *means*, never how big it is.

    Two earlier versions of this got it wrong the same way. The first copied the
    value verbatim, so ``{"error": <26KB traceback>}`` put the whole traceback
    back beside the excerpt — a spilled failure was *larger* than not spilling
    (27,649 -> 30,023 chars). The second bounded only ``str``, which left every
    structured error unbounded — and ``{"error": {"code", "message", "trace"}}``
    is the standard shape for HTTP, API and subprocess failures, so that was the
    mainline case rather than a corner (31,254 -> 33,585 measured).

    Bounded by **serialised size**, not by type. Scalars pass through untouched
    because the loop reads them for truth, not text: `_should_iterate` tests key
    presence and `_record_observation_fingerprints` tests truthiness, so
    ``{"error": None}`` and ``{"success": False}`` must stay falsy rather than
    becoming the truthy strings ``"None"`` / ``"False"``.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = value if isinstance(value, str) else _serialise(value)
    return text[:_CLASSIFICATION_MARKER_CHARS]


def _excerpt_payload(anchor: str, tool_name: str, payload: str, original: Any = None) -> Dict[str, Any]:
    """What enters context in place of the full output.

    Invariant: this must always be smaller than what it replaces. That is the
    one property the module exists to provide, and it is asserted in the tests.
    """
    excerpt: Dict[str, Any] = {
        "spilled": True,
        "tool": tool_name,
        "anchor": anchor,
        "excerpt": payload[:SPILL_EXCERPT_CHARS],
        "omitted_chars": max(0, len(payload) - SPILL_EXCERPT_CHARS),
        "note": (
            f"Output truncated to {SPILL_EXCERPT_CHARS} of {len(payload)} chars. "
            f"Read the full output with the read_spilled_output tool using anchor {anchor!r}."
        ),
    }
    if isinstance(original, dict):
        for key in _CLASSIFYING_KEYS:
            if key in original:
                excerpt[key] = _classification_marker(original[key])
    return excerpt


def read_spilled(anchor: str, task_id: str | None = None) -> str | None:
    """Return the full spilled output for *anchor*, or None.

    This is what makes the anchor a reference rather than a deletion.

    ``task_id`` scopes the read to one run (#13754). It is optional so
    in-process callers that already hold the artifact can omit it, but the
    agent-facing tool always passes it: without the check, an anchor leaked
    into one run could read another run's observations, since the anchor alone
    is a bearer token.
    """
    if not isinstance(anchor, str) or not anchor.startswith(_ANCHOR_PREFIX):
        return None
    try:
        path = _artifact_path(anchor)
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if task_id is not None and record.get("task_id") != task_id:
            logger.warning("Refusing cross-run spilled read for anchor %s (#13754)", anchor)
            return None
        return record.get("output")
    except Exception as exc:
        logger.warning("Failed to read spilled output for %s: %s", anchor, exc)
        return None


def read_spilled_window(anchor: str, offset: int = 0, limit: int | None = None) -> Dict[str, Any]:
    """Return a bounded window of a spilled output (#13754).

    A window, not the whole artifact: handing back the full 78,000 chars would
    undo the offload that put it aside in the first place. Re-reading is a
    seek, not an undo.

    The run is taken from the bound execution context, never from an argument.
    Nothing is readable until the loop has declared which run is executing, so
    an anchor on its own is not a bearer token (#13865).
    """
    task_id = current_task_id()
    if not task_id:
        logger.warning("Refusing spilled read: no run bound to this context (#13865)")
        return {"found": False, "anchor": anchor, "reason": "no_run_bound"}

    full = read_spilled(anchor, task_id=task_id)
    if full is None:
        return {"found": False, "anchor": anchor}

    try:
        requested = SPILL_EXCERPT_CHARS if limit is None else int(limit)
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        # These come from a model-authored tool call, so they are arbitrary.
        return {"found": False, "anchor": anchor, "reason": "invalid_window"}

    limit = min(SPILL_MAX_WINDOW_CHARS, max(1, requested))
    window = full[offset : offset + limit]
    return {
        "found": True,
        "anchor": anchor,
        "offset": offset,
        "limit": limit,
        "total_chars": len(full),
        "content": window,
        "has_more": offset + limit < len(full),
    }


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


async def spill_results_async(task_id: str, tool_results: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """:func:`spill_results` off the event loop.

    The write is by definition large — that is the trigger condition — and the
    agent loop calls this from an async path, where a blocking ``write_text``
    stalls every other coroutine in the process (CLAUDE.md: async-first).
    """
    if not SPILL_ENABLED or not tool_results:
        return tool_results, 0
    return await asyncio.to_thread(spill_results, task_id, tool_results)


__all__ = [
    "SPILL_ENABLED",
    "SPILL_EXCERPT_CHARS",
    "SPILL_MAX_ARTIFACT_CHARS",
    "SPILL_MAX_WINDOW_CHARS",
    "SPILL_THRESHOLD_CHARS",
    "bind_task",
    "current_task_id",
    "read_spilled",
    "sweepable_spill_root",
    "read_spilled_window",
    "spill_if_oversized",
    "spill_results",
    "spill_results_async",
]
