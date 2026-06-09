# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Chat Workflow Stop Hook — Issue #5073

Fires when an agent turn completes and enqueues all memory Celery tasks
in a fire-and-forget fashion so the user-facing response stream is never
blocked.

Responsibilities:
- Enqueue ``memory.write_verbatim`` for both user and assistant turns.
- Enqueue ``memory.extract_facts`` for the full turn pair.
- ``memory.update_graph`` is NOT enqueued here — graph population is driven
  by the fact-extraction pipeline inside the Celery worker.

All ``.delay()`` calls are synchronous and non-blocking; they only publish
a message to Redis.  The actual work happens in background Celery workers.
"""

from datetime import datetime, timezone

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def on_turn_complete(
    session_id: str,
    user_message: str,
    assistant_response: str,
    user_id: str | None,
    turn_number: int,
) -> None:
    """Enqueue memory tasks for a completed chat turn (fire-and-forget).

    This coroutine is called via ``asyncio.create_task()`` from
    ``ChatWorkflowManager._execute_llm_workflow`` so it never blocks
    the response stream.

    Args:
        session_id: Chat session identifier.
        user_message: Raw user message text.
        assistant_response: Full assembled assistant response text.
        user_id: Optional user identifier for privacy scoping.
        turn_number: Zero-based turn counter within the session.
    """
    # Late imports keep this module free of circular deps at load time.
    # Test code may patch ``stop_hook.write_verbatim_task`` /
    # ``stop_hook.extract_facts_task`` by assigning to this module's namespace.
    _wv = globals().get("write_verbatim_task")
    _ef = globals().get("extract_facts_task")
    if _wv is None or _ef is None:
        from tasks.memory_tasks import extract_facts_task as _ef  # type: ignore[assignment]
        from tasks.memory_tasks import write_verbatim_task as _wv  # type: ignore[assignment]

    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        # Verbatim store writes — one task per role for parallelism
        _wv.delay(session_id, turn_number, "user", user_message, timestamp, user_id)
        _wv.delay(
            session_id,
            turn_number,
            "assistant",
            assistant_response,
            timestamp,
            user_id,
        )

        # Fact extraction over the combined turn text
        combined_text = f"User: {user_message}\nAssistant: {assistant_response}"
        _ef.delay(session_id, combined_text, user_id)

        logger.debug(
            "stop_hook.on_turn_complete: enqueued 3 memory tasks " "(session=%s turn=%d)",
            session_id,
            turn_number,
        )
    except Exception as exc:
        # Never raise from a fire-and-forget hook — log and continue.
        logger.warning(
            "stop_hook.on_turn_complete failed to enqueue tasks " "(session=%s turn=%d): %s",
            session_id,
            turn_number,
            exc,
        )


__all__ = ["on_turn_complete"]
