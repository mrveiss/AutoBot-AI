# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Memory Background Tasks for AutoBot

Celery tasks for off-hot-path memory operations: verbatim store writes,
fact extraction, memory graph updates, and pre-compaction snapshots.

Issue #5073: Moves memory write-path off the chat turn hot path via
stop hook (on_turn_complete) and pre-compact hook (on_pre_compact).

Design decisions:
- acks_late=True on all tasks — message is only removed from queue after
  successful completion, preventing data loss on worker crash.
- max_retries + retry(countdown=N) — all tasks are idempotent so safe retry.
- run_or_schedule() — Celery workers are synchronous; the shared helper from
  ``autobot_shared.async_compat`` defends against re-entrancy if a worker
  ever runs inside an already-active event loop (#7469).
- Deferred imports inside task bodies to avoid circular-import issues at
  module load time (Celery autodiscovers this module before the app is fully
  initialised).
"""

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from celery_app import celery_app

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Async helpers (called via asyncio.run from sync Celery task bodies)
# ---------------------------------------------------------------------------


async def _async_write_verbatim(
    session_id: str,
    turn: int,
    role: str,
    text: str,
    timestamp_iso: str,
    user_id: str | None,
) -> str:
    """Obtain VerbatimStore singleton and append one turn chunk."""
    from datetime import datetime, timezone

    from memory.verbatim_store import get_verbatim_store

    ts = datetime.fromisoformat(timestamp_iso).replace(tzinfo=timezone.utc)
    store = await get_verbatim_store()
    return await store.append(
        session_id=session_id,
        turn=turn,
        role=role,
        text=text,
        timestamp=ts,
        user_id=user_id,
    )


async def _async_extract_facts(session_id: str, conversation_text: str, user_id: str | None) -> int:
    """Run KnowledgeExtractionAgent on the turn text."""
    from agents.knowledge_extraction_agent import KnowledgeExtractionAgent

    agent = KnowledgeExtractionAgent()
    messages = [{"role": "conversation", "content": conversation_text}]
    result = await agent.extract_facts_from_messages(
        messages=messages,
        session_id=session_id,
        user_id=user_id,
    )
    return result.get("facts_count", 0) if isinstance(result, dict) else 0


async def _async_update_graph(session_id: str, entities: list, relations: list) -> dict:
    """Write entities and relations into AutoBotMemoryGraph."""
    from autobot_memory_graph import AutoBotMemoryGraph

    graph = AutoBotMemoryGraph()
    await graph.initialize()

    entities_written = 0
    relations_written = 0

    for entity in entities:
        try:
            await graph.add_or_update_entity(
                name=entity.get("name", ""),
                entity_type=entity.get("type", "unknown"),
                properties=entity.get("properties", {}),
                session_id=session_id,
            )
            entities_written += 1
        except Exception as ent_exc:
            logger.warning(
                "memory.update_graph: entity write failed (%s): %s",
                entity.get("name"),
                ent_exc,
            )

    for relation in relations:
        try:
            await graph.add_relation(
                source=relation.get("source", ""),
                target=relation.get("target", ""),
                relation_type=relation.get("relation_type", "related_to"),
                properties=relation.get("properties", {}),
                session_id=session_id,
            )
            relations_written += 1
        except Exception as rel_exc:
            logger.warning(
                "memory.update_graph: relation write failed (%s→%s): %s",
                relation.get("source"),
                relation.get("target"),
                rel_exc,
            )

    return {
        "status": "ok",
        "entities_written": entities_written,
        "relations_written": relations_written,
    }


async def _async_compact_snapshot(session_id: str, conversation_snapshot: str, user_id: str | None) -> None:
    """Persist pre-compaction snapshot to verbatim store."""
    from datetime import datetime, timezone

    from memory.verbatim_store import get_verbatim_store

    store = await get_verbatim_store()
    ts = datetime.now(tz=timezone.utc)
    await store.append(
        session_id=session_id,
        turn=-1,  # -1 sentinel = pre-compaction snapshot
        role="assistant",
        text=f"[PRE-COMPACT SNAPSHOT]\n{conversation_snapshot}",
        timestamp=ts,
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Observability helper
# ---------------------------------------------------------------------------


def _log_queue_depth(task_name: str) -> None:
    """Log current memory queue depth (best-effort, Issue #5073).

    Provides visibility into memory task backlog without blocking the task.
    Failures are silently swallowed so they never affect task completion.
    """
    try:
        inspection = celery_app.control.inspect(timeout=0.5)
        reserved = inspection.reserved() or {}
        depth = sum(
            len(tasks) for worker_tasks in reserved.values() for tasks in [worker_tasks] if isinstance(tasks, list)
        )
        logger.info("memory task queue depth after %s: ~%d reserved", task_name, depth)
    except Exception:
        pass  # observability is best-effort


# ---------------------------------------------------------------------------
# Celery task definitions
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="memory.write_verbatim",
    max_retries=3,
    acks_late=True,
)
def write_verbatim_task(
    self,
    session_id: str,
    turn: int,
    role: str,
    text: str,
    timestamp: str,
    user_id: str | None,
) -> dict:
    """Write one conversation turn to the verbatim store.

    Idempotent: ChromaDB add uses a stable chunk_id derived from
    (session_id, turn, role) so duplicate Celery deliveries are safe.

    Args:
        session_id: Chat session identifier.
        turn: Zero-based turn counter within the session.
        role: ``"user"`` or ``"assistant"``.
        text: Raw text of the turn.
        timestamp: ISO-8601 UTC timestamp string.
        user_id: Optional user identifier for privacy scoping.

    Returns:
        Dict with ``chunk_id`` and ``status``.
    """
    try:
        chunk_id = run_or_schedule(_async_write_verbatim(session_id, turn, role, text, timestamp, user_id))
        logger.debug(
            "memory.write_verbatim: stored chunk %s (session=%s turn=%d role=%s)",
            chunk_id,
            session_id,
            turn,
            role,
        )
        _log_queue_depth("memory.write_verbatim")
        return {"status": "ok", "chunk_id": chunk_id}
    except Exception as exc:
        logger.warning(
            "memory.write_verbatim failed (session=%s turn=%d role=%s): %s — retrying",
            session_id,
            turn,
            role,
            exc,
        )
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(
    bind=True,
    name="memory.extract_facts",
    max_retries=3,
    acks_late=True,
)
def extract_facts_task(
    self,
    session_id: str,
    conversation_text: str,
    user_id: str | None,
) -> dict:
    """Run fact extraction for a completed turn.

    Delegates to KnowledgeExtractionAgent which already exists in the
    codebase.  The extracted facts are persisted into the knowledge base.

    Args:
        session_id: Chat session identifier (used for logging / scoping).
        conversation_text: Combined user + assistant turn text.
        user_id: Optional user identifier.

    Returns:
        Dict with ``status`` and ``facts_count``.
    """
    try:
        facts_count = run_or_schedule(_async_extract_facts(session_id, conversation_text, user_id))
        logger.info(
            "memory.extract_facts: extracted %d facts (session=%s)",
            facts_count,
            session_id,
        )
        _log_queue_depth("memory.extract_facts")
        return {"status": "ok", "facts_count": facts_count}
    except Exception as exc:
        logger.warning(
            "memory.extract_facts failed (session=%s): %s — retrying",
            session_id,
            exc,
        )
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    bind=True,
    name="memory.update_graph",
    max_retries=2,
    acks_late=True,
)
def update_graph_task(
    self,
    session_id: str,
    entities: list,
    relations: list,
) -> dict:
    """Update the memory graph with entities and relations from a turn.

    The caller (stop hook) is responsible for extracting entities/relations
    before enqueueing; this task only performs the graph write.

    Args:
        session_id: Chat session identifier.
        entities: List of entity dicts (keys: ``name``, ``type``,
            ``properties``).
        relations: List of relation dicts (keys: ``source``, ``target``,
            ``relation_type``, ``properties``).

    Returns:
        Dict with ``status``, ``entities_written``, ``relations_written``.
    """
    try:
        result = run_or_schedule(_async_update_graph(session_id, entities, relations))
        logger.info(
            "memory.update_graph: wrote %d entities, %d relations (session=%s)",
            result.get("entities_written", 0),
            result.get("relations_written", 0),
            session_id,
        )
        _log_queue_depth("memory.update_graph")
        return result
    except Exception as exc:
        logger.warning(
            "memory.update_graph failed (session=%s): %s — retrying",
            session_id,
            exc,
        )
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    bind=True,
    name="memory.compact_snapshot",
    max_retries=2,
    acks_late=True,
)
def compact_snapshot_task(
    self,
    session_id: str,
    conversation_snapshot: str,
    user_id: str | None,
) -> dict:
    """Save a conversation snapshot before context compaction.

    Stores the snapshot in the verbatim store so it survives the context
    window reset.  Idempotent: the turn=-1 sentinel can appear multiple
    times per session without causing data loss.

    Args:
        session_id: Chat session identifier.
        conversation_snapshot: Truncated conversation text (last N turns).
        user_id: Optional user identifier.

    Returns:
        Dict with ``status`` and ``session_id``.
    """
    try:
        run_or_schedule(_async_compact_snapshot(session_id, conversation_snapshot, user_id))
        logger.info(
            "memory.compact_snapshot: saved snapshot for session=%s (%d chars)",
            session_id,
            len(conversation_snapshot),
        )
        _log_queue_depth("memory.compact_snapshot")
        return {"status": "ok", "session_id": session_id}
    except Exception as exc:
        logger.warning(
            "memory.compact_snapshot failed (session=%s): %s — retrying",
            session_id,
            exc,
        )
        raise self.retry(exc=exc, countdown=30)


__all__ = [
    "write_verbatim_task",
    "extract_facts_task",
    "update_graph_task",
    "compact_snapshot_task",
]
