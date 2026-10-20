# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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


async def _upsert_graph_entity(graph, entity: dict, session_id: str, owner) -> None:
    """Atomically get-or-create the entity, then append observations if it existed (#18417).

    A lookup error propagates (the caller counts it as a failure); it is never read as absence.
    """
    name = entity.get("name", "")
    observations = [f"{k}: {v}" for k, v in (entity.get("properties") or {}).items()]
    _, created = await graph.get_or_create_entity(
        entity_type=entity.get("type", "unknown"),
        name=name,
        observations=observations,
        metadata={"session_id": session_id},
        owner=owner,  # #18825: the session owner, so scoped reads can see what this task wrote
    )
    if not created and observations:
        await graph.add_observations(entity_name=name, observations=observations)


MAX_REPORTED_GRAPH_FAILURES = 20


def _record_failure(failures: list, kind: str, item: str, exc: Exception) -> None:
    """Keep a capped {kind, item, error} list so the task result says what failed."""
    if len(failures) < MAX_REPORTED_GRAPH_FAILURES:
        failures.append({"kind": kind, "item": item, "error": str(exc)})


async def _write_graph_entities(graph, entities: list, session_id: str, failures: list, owner) -> int:
    """Write entities; every failure is logged with the item name and recorded."""
    written = 0
    for entity in entities:
        try:
            await _upsert_graph_entity(graph, entity, session_id, owner)
            written += 1
        except Exception as ent_exc:
            _record_failure(failures, "entity", str(entity.get("name")), ent_exc)
            logger.warning("memory.update_graph: entity write failed (%s): %s", entity.get("name"), ent_exc)
    return written


async def _write_graph_relations(graph, relations: list, session_id: str, failures: list) -> int:
    """Write relations; every failure is logged with both endpoints and recorded."""
    written = 0
    for relation in relations:
        try:
            await graph.create_relation(
                from_entity=relation.get("source", ""),
                to_entity=relation.get("target", ""),
                relation_type=relation.get("relation_type", "related_to"),
                metadata={**(relation.get("properties") or {}), "session_id": session_id},
            )
            written += 1
        except Exception as rel_exc:
            _record_failure(failures, "relation", f"{relation.get('source')}->{relation.get('target')}", rel_exc)
            logger.warning(
                "memory.update_graph: relation write failed (%s->%s): %s",
                relation.get("source"),
                relation.get("target"),
                rel_exc,
            )
    return written


async def _async_update_graph(
    session_id: str, entities: list, relations: list, user_id: str | None = None, org_id: str | None = None
) -> dict:
    """Write entities and relations into AutoBotMemoryGraph under the session owner's scope (#18825).

    Raises ``OwnerScopeRequired`` when ``user_id`` is missing: no owner, no write.
    """
    from autobot_memory_graph import AutoBotMemoryGraph
    from autobot_memory_graph.owner_scope import OwnerScope

    owner = OwnerScope.for_user(user_id, org_id)  # fails closed before any connection is opened
    graph = AutoBotMemoryGraph()
    await graph.initialize()

    failures: list = []
    entities_written = await _write_graph_entities(graph, entities, session_id, failures, owner)
    relations_written = await _write_graph_relations(graph, relations, session_id, failures)
    entities_failed = len(entities) - entities_written
    relations_failed = len(relations) - relations_written

    return {
        "status": "partial" if entities_failed or relations_failed else "ok",
        "entities_written": entities_written,
        "relations_written": relations_written,
        "entities_failed": entities_failed,
        "relations_failed": relations_failed,
        "failures": failures,
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
    user_id: str | None = None,
    org_id: str | None = None,
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
        user_id: Session owner (scalar id of the authenticated principal); required.
        org_id: Owner's organisation id, if any.

    Returns:
        Dict with ``status``, ``entities_written``, ``relations_written``.
        ``status == "rejected"`` (nothing written, no retry) when ``user_id`` is missing.
    """
    from autobot_memory_graph.owner_scope import OwnerScopeRequired

    try:
        result = run_or_schedule(_async_update_graph(session_id, entities, relations, user_id, org_id))
        logger.info(
            "memory.update_graph: wrote %d entities, %d relations (session=%s)",
            result.get("entities_written", 0),
            result.get("relations_written", 0),
            session_id,
        )
        _log_queue_depth("memory.update_graph")
        return result
    except OwnerScopeRequired as exc:  # a retry cannot conjure an owner
        logger.warning("memory.update_graph rejected (session=%s): %s", session_id, exc)
        return {"status": "rejected", "reason": str(exc), "entities_written": 0, "relations_written": 0}
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
