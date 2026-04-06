# Copyright (c) mrveiss. All rights reserved.
"""
knowledge.memory_graph.graph_store — entity/relation CRUD and BFS traversal.

All public functions are async and accept an explicit *redis_client* parameter
so they remain independently testable.  Callers that want a shared client
should call ``get_redis_client(async_client=True, database="knowledge")`` once
and pass it through.

Public API
----------
create_entity(redis_client, entity_type, name, observations, metadata) -> dict
get_entity(redis_client, entity_id) -> dict | None
create_relation(redis_client, from_id, to_id, rel_type, metadata) -> bool
get_outgoing_relations(redis_client, entity_id) -> list[dict]
get_incoming_relations(redis_client, entity_id) -> list[dict]
traverse_relations(redis_client, entity_id, relation_type, max_depth) -> list[dict]
"""

import asyncio
import logging
import uuid
from collections import deque
from time import time
from typing import Any, Dict, List, Optional

from .schema import (
    ENTITY_KEY_PREFIX,
    ENTITY_TYPES,
    RELATION_TYPES,
    RELATIONS_IN_PREFIX,
    RELATIONS_OUT_PREFIX,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    """Return current Unix time in milliseconds."""
    return int(time() * 1000)


def _entity_key(entity_id: str) -> str:
    return f"{ENTITY_KEY_PREFIX}{entity_id}"


def _out_key(entity_id: str) -> str:
    return f"{RELATIONS_OUT_PREFIX}{entity_id}"


def _in_key(entity_id: str) -> str:
    return f"{RELATIONS_IN_PREFIX}{entity_id}"


async def _init_relation_doc(redis_client: Any, key: str, owner_id: str) -> None:
    """Create an empty relation document at *key* if it does not exist (atomic NX)."""
    import json as _json
    await redis_client.execute_command(
        "JSON.SET", key, "$", _json.dumps({"entity_id": owner_id, "relations": []}), "NX"
    )


# ---------------------------------------------------------------------------
# Entity CRUD
# ---------------------------------------------------------------------------


async def create_entity(
    redis_client: Any,
    entity_type: str,
    name: str,
    observations: List[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create and persist a new memory-graph entity.

    Args:
        redis_client: Async redis-py client (knowledge DB).
        entity_type: One of the values in ENTITY_TYPES.
        name: Human-readable entity name.
        observations: Initial observations list.
        metadata: Optional dict merged into entity ``metadata`` field.

    Returns:
        The persisted entity document (dict).

    Raises:
        ValueError: *entity_type* is not recognised or *name* is blank.
        RuntimeError: Redis write failed.
    """
    if entity_type not in ENTITY_TYPES:
        raise ValueError("Invalid entity_type %r; expected one of %s" % (entity_type, sorted(ENTITY_TYPES)))
    if not name or not name.strip():
        raise ValueError("Entity name must not be empty")

    entity_id = str(uuid.uuid4())
    now = _now_ms()
    base_metadata: Dict[str, Any] = {
        "priority": "medium",
        "status": "active",
        "tags": [],
        "session_id": "",
    }
    if metadata:
        base_metadata.update(metadata)

    entity: Dict[str, Any] = {
        "id": entity_id,
        "type": entity_type,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "observations": list(observations),
        "metadata": base_metadata,
    }

    try:
        await redis_client.json().set(_entity_key(entity_id), "$", entity)
    except Exception as exc:
        logger.error("Failed to persist entity %s: %s", entity_id, exc)
        raise RuntimeError("Entity creation failed") from exc

    logger.info("Created entity id=%s type=%s name=%r", entity_id[:8], entity_type, name)
    return entity


async def get_entity(
    redis_client: Any,
    entity_id: str,
) -> Optional[Dict[str, Any]]:
    """Fetch a single entity by UUID.

    Args:
        redis_client: Async redis-py client (knowledge DB).
        entity_id: UUID of the entity.

    Returns:
        Entity dict, or ``None`` if not found.
    """
    try:
        return await redis_client.json().get(_entity_key(entity_id))
    except Exception as exc:
        logger.error("Failed to fetch entity %s: %s", entity_id, exc)
        return None


# ---------------------------------------------------------------------------
# Relation CRUD
# ---------------------------------------------------------------------------


async def create_relation(
    redis_client: Any,
    from_id: str,
    to_id: str,
    rel_type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Create a bidirectional relation between two entities.

    The outgoing document at ``memory:relations:out:{from_id}`` and the
    incoming document at ``memory:relations:in:{to_id}`` are both updated
    atomically inside a Redis pipeline.

    Args:
        redis_client: Async redis-py client (knowledge DB).
        from_id: Source entity UUID.
        to_id: Target entity UUID.
        rel_type: One of the values in RELATION_TYPES.
        metadata: Optional dict stored on the outgoing relation edge.

    Returns:
        ``True`` on success, ``False`` on error.

    Raises:
        ValueError: *rel_type* is not recognised.
    """
    if rel_type not in RELATION_TYPES:
        raise ValueError("Invalid rel_type %r; expected one of %s" % (rel_type, sorted(RELATION_TYPES)))

    now = _now_ms()
    outgoing_rel = {
        "to": to_id,
        "type": rel_type,
        "created_at": now,
        "metadata": metadata or {},
    }
    incoming_rel = {
        "from": from_id,
        "type": rel_type,
        "created_at": now,
    }

    try:
        out_k = _out_key(from_id)
        in_k = _in_key(to_id)
        await asyncio.gather(
            _init_relation_doc(redis_client, out_k, from_id),
            _init_relation_doc(redis_client, in_k, to_id),
        )
        pipe = redis_client.pipeline()
        pipe.json().arrappend(out_k, "$.relations", outgoing_rel)
        pipe.json().arrappend(in_k, "$.relations", incoming_rel)
        await pipe.execute()
    except Exception as exc:
        logger.error("Failed to create relation %s-[%s]->%s: %s", from_id, rel_type, to_id, exc)
        return False

    logger.info(
        "Created relation %s-[%s]->%s", from_id[:8], rel_type, to_id[:8]
    )
    return True


async def get_outgoing_relations(
    redis_client: Any,
    entity_id: str,
) -> List[Dict[str, Any]]:
    """Return all outgoing relation edges for *entity_id*.

    Args:
        redis_client: Async redis-py client (knowledge DB).
        entity_id: UUID of the source entity.

    Returns:
        List of outgoing relation dicts (``{"to": ..., "type": ..., ...}``).
    """
    try:
        doc = await redis_client.json().get(_out_key(entity_id))
        return doc.get("relations", []) if doc else []
    except Exception as exc:
        logger.debug("Could not read outgoing relations for %s: %s", entity_id, exc)
        return []


async def get_incoming_relations(
    redis_client: Any,
    entity_id: str,
) -> List[Dict[str, Any]]:
    """Return all incoming relation edges for *entity_id*.

    Args:
        redis_client: Async redis-py client (knowledge DB).
        entity_id: UUID of the target entity.

    Returns:
        List of incoming relation dicts (``{"from": ..., "type": ..., ...}``).
    """
    try:
        doc = await redis_client.json().get(_in_key(entity_id))
        return doc.get("relations", []) if doc else []
    except Exception as exc:
        logger.debug("Could not read incoming relations for %s: %s", entity_id, exc)
        return []


# ---------------------------------------------------------------------------
# Graph traversal
# ---------------------------------------------------------------------------


async def traverse_relations(
    redis_client: Any,
    entity_id: str,
    relation_type: Optional[str] = None,
    max_depth: int = 3,
) -> List[Dict[str, Any]]:
    """BFS traversal starting from *entity_id* following outgoing edges.

    Args:
        redis_client: Async redis-py client (knowledge DB).
        entity_id: UUID of the starting entity.
        relation_type: When set, only edges of this type are followed.
        max_depth: Maximum hop count (1 = direct neighbours only).

    Returns:
        Ordered list of entity dicts encountered during traversal
        (excluding the root entity itself).
    """
    visited: set = {entity_id}
    queue: deque = deque([(entity_id, 0)])
    result: List[Dict[str, Any]] = []

    while queue:
        current_id, depth = queue.popleft()
        if depth >= max_depth:
            continue

        relations = await get_outgoing_relations(redis_client, current_id)
        next_ids = [
            r["to"]
            for r in relations
            if (relation_type is None or r.get("type") == relation_type)
            and r["to"] not in visited
        ]

        if not next_ids:
            continue

        entities = await asyncio.gather(
            *[get_entity(redis_client, nid) for nid in next_ids],
            return_exceptions=True,
        )

        for nid, entity in zip(next_ids, entities):
            if isinstance(entity, BaseException) or entity is None:
                continue
            visited.add(nid)
            result.append(entity)
            queue.append((nid, depth + 1))

    return result
