# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Workflow Pre-Compact Hook — Issue #5073

Detects when a conversation is approaching its context window limit and
eagerly snapshots the current session state to persistent memory before
the context is discarded / compacted.

Design:
- ``CONTEXT_LIMIT_THRESHOLD`` (default 0.85) — fire snapshot at 85 % of the
  model's context window.  Set lower if you need more safety margin.
- Token estimation is character-based (÷ 4) — intentionally rough.  Accurate
  tokenisation is expensive; we only need to detect *approaching* the limit.
- The snapshot stores the last ``_SNAPSHOT_TURNS`` message pairs (truncated
  to ``_MAX_CHARS_PER_MSG`` chars each) to stay within a reasonable size.
- ``compact_snapshot_task.delay()`` is synchronous and non-blocking; the hook
  itself is async only to be compatible with the async call sites.
"""

from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Fire snapshot when estimated context usage exceeds this fraction.
CONTEXT_LIMIT_THRESHOLD: float = 0.85

# Number of recent message pairs included in the snapshot.
_SNAPSHOT_TURNS: int = 20

# Maximum characters per message in the snapshot (prevents huge payloads).
_MAX_CHARS_PER_MSG: int = 500

# Known model context sizes (tokens).  Falls back to CHAT_NUM_CTX for
# unrecognised models.
_MODEL_CONTEXT_SIZES: dict[str, int] = {
    # Ollama defaults from constants/model_constants.py
    "default": 8192,
    "llama3": 8192,
    "llama3.1": 8192,
    "llama3.2": 8192,
    "mistral": 8192,
    "mixtral": 32768,
    "codellama": 16384,
    "gemma": 8192,
    "gemma2": 8192,
    "phi3": 4096,
    "qwen2": 32768,
}


def estimate_context_usage(messages: list[dict[str, Any]], model_name: str) -> float:
    """Estimate fraction of the model context window currently consumed.

    Uses character-count ÷ 4 as a cheap token approximation.  Returns a
    value in [0.0, 1.0]; values > 1.0 are clamped to 1.0.

    Args:
        messages: List of message dicts with at least a ``content`` key.
        model_name: Ollama model name (used to look up context window size).

    Returns:
        Estimated usage fraction between 0.0 and 1.0.
    """
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    estimated_tokens = total_chars / 4

    # Normalise model name: strip tags like ':latest', version suffixes, etc.
    base_name = model_name.lower().split(":")[0] if model_name else "default"
    # Try longest matching prefix for models like 'llama3.1:8b-instruct-q4'
    context_size = _MODEL_CONTEXT_SIZES.get(base_name)
    if context_size is None:
        for key in sorted(_MODEL_CONTEXT_SIZES, key=len, reverse=True):
            if base_name.startswith(key):
                context_size = _MODEL_CONTEXT_SIZES[key]
                break
        else:
            context_size = _MODEL_CONTEXT_SIZES["default"]

    if context_size <= 0:
        return 0.0
    return min(estimated_tokens / context_size, 1.0)


async def on_pre_compact(
    session_id: str,
    messages: list[dict[str, Any]],
    user_id: str | None,
    model_name: str,
) -> None:
    """Snapshot current session before context compaction (fire-and-forget).

    Enqueues ``memory.compact_snapshot`` only when estimated context usage
    is at or above ``CONTEXT_LIMIT_THRESHOLD``.  Called as
    ``asyncio.create_task(on_pre_compact(...))`` so it never blocks the
    response path.

    Args:
        session_id: Chat session identifier.
        messages: Full list of current conversation messages (dicts with
            at least ``role`` and ``content`` keys).
        user_id: Optional user identifier for privacy scoping.
        model_name: Active Ollama model name (used for context size lookup).
    """
    usage = estimate_context_usage(messages, model_name)
    if usage < CONTEXT_LIMIT_THRESHOLD:
        logger.debug(
            "compact_hook.on_pre_compact: usage=%.2f < threshold=%.2f — skipping " "(session=%s)",
            usage,
            CONTEXT_LIMIT_THRESHOLD,
            session_id,
        )
        return

    logger.info(
        "compact_hook.on_pre_compact: usage=%.2f >= threshold=%.2f — snapshotting " "(session=%s model=%s)",
        usage,
        CONTEXT_LIMIT_THRESHOLD,
        session_id,
        model_name,  # codeql[py/clear-text-logging-sensitive-data]
    )

    # Build a compact snapshot from the last N messages.
    snapshot_lines = []
    for msg in messages[-_SNAPSHOT_TURNS:]:
        role = msg.get("role", "unknown")
        content = str(msg.get("content", ""))[:_MAX_CHARS_PER_MSG]
        snapshot_lines.append(f"{role}: {content}")
    snapshot = "\n".join(snapshot_lines)

    try:
        # Late import keeps this module free of circular deps at load time.
        # Test code may patch ``compact_hook.compact_snapshot_task`` directly
        # by assigning to this module's namespace before calling on_pre_compact.
        _cs_task = globals().get("compact_snapshot_task")
        if _cs_task is None:
            from tasks.memory_tasks import compact_snapshot_task as _cs_task  # type: ignore[assignment]

        _cs_task.delay(session_id, snapshot, user_id)
        logger.debug(
            "compact_hook.on_pre_compact: enqueued compact_snapshot_task " "(session=%s chars=%d)",
            session_id,
            len(snapshot),
        )
    except Exception as exc:
        # Never raise from a fire-and-forget hook — log and continue.
        logger.warning(
            "compact_hook.on_pre_compact failed to enqueue task " "(session=%s): %s",
            session_id,
            exc,
        )


__all__ = ["on_pre_compact", "estimate_context_usage", "CONTEXT_LIMIT_THRESHOLD"]
