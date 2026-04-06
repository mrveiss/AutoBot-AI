# Copyright (c) mrveiss. All rights reserved.
"""
knowledge.memory_graph.schema — Redis key patterns, constants, and index creation.

Implements the schema described in docs/database/REDIS_MEMORY_GRAPH_SPECIFICATION.md.
All data lives in Redis DB 1 (``knowledge``); the existing autobot_memory_graph
package already uses this database so there is no separate DB 2 allocation in the
current redis-databases.yaml.

Key patterns
------------
``memory:entity:{uuid}``        — RedisJSON entity document
``memory:relations:out:{uuid}`` — RedisJSON outgoing-relation list
``memory:relations:in:{uuid}``  — RedisJSON incoming-relation list

Search indexes
--------------
``memory_entity_idx``   — primary filtered / sorted search
``memory_fulltext_idx`` — full-text search with phonetic matching
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key patterns
# ---------------------------------------------------------------------------

ENTITY_KEY_PREFIX: str = "memory:entity:"
RELATIONS_OUT_PREFIX: str = "memory:relations:out:"
RELATIONS_IN_PREFIX: str = "memory:relations:in:"

# ---------------------------------------------------------------------------
# Index names
# ---------------------------------------------------------------------------

PRIMARY_INDEX_NAME: str = "memory_entity_idx"
FULLTEXT_INDEX_NAME: str = "memory_fulltext_idx"

# ---------------------------------------------------------------------------
# Allowed values
# ---------------------------------------------------------------------------

ENTITY_TYPES: frozenset = frozenset(
    {
        "conversation",
        "bug_fix",
        "feature",
        "decision",
        "task",
        "research",
        "implementation",
    }
)

RELATION_TYPES: frozenset = frozenset(
    {
        "fixes",
        "implements",
        "depends_on",
        "relates_to",
        "informs",
        "guides",
        "blocks",
    }
)

# ---------------------------------------------------------------------------
# FT.CREATE argument lists (no raw string commands — args passed to execute_command)
# ---------------------------------------------------------------------------

_PRIMARY_INDEX_ARGS: list = [
    "FT.CREATE",
    PRIMARY_INDEX_NAME,
    "ON",
    "JSON",
    "PREFIX",
    "1",
    ENTITY_KEY_PREFIX,
    "SCHEMA",
    "$.type",
    "AS",
    "type",
    "TAG",
    "SORTABLE",
    "$.name",
    "AS",
    "name",
    "TEXT",
    "WEIGHT",
    "2.0",
    "SORTABLE",
    "$.observations[*]",
    "AS",
    "observations",
    "TEXT",
    "$.created_at",
    "AS",
    "created_at",
    "NUMERIC",
    "SORTABLE",
    "$.updated_at",
    "AS",
    "updated_at",
    "NUMERIC",
    "SORTABLE",
    "$.metadata.priority",
    "AS",
    "priority",
    "TAG",
    "$.metadata.status",
    "AS",
    "status",
    "TAG",
    "SORTABLE",
    "$.metadata.tags[*]",
    "AS",
    "tags",
    "TAG",
    "SEPARATOR",
    ",",
    "$.metadata.session_id",
    "AS",
    "session_id",
    "TAG",
]

_FULLTEXT_INDEX_ARGS: list = [
    "FT.CREATE",
    FULLTEXT_INDEX_NAME,
    "ON",
    "JSON",
    "PREFIX",
    "1",
    ENTITY_KEY_PREFIX,
    "LANGUAGE",
    "english",
    "SCHEMA",
    "$.name",
    "AS",
    "name",
    "TEXT",
    "PHONETIC",
    "dm:en",
    "$.observations[*]",
    "AS",
    "content",
    "TEXT",
]


# ---------------------------------------------------------------------------
# Index management helpers
# ---------------------------------------------------------------------------


async def _index_exists(redis_client: Any, index_name: str) -> bool:
    """Return True when *index_name* already exists in Redis."""
    try:
        await redis_client.execute_command("FT.INFO", index_name)
        return True
    except Exception:
        return False


async def _create_index(redis_client: Any, args: list) -> None:
    """Issue a single FT.CREATE command; log but do not raise on failure."""
    index_name = args[1]
    try:
        await redis_client.execute_command(*args)
        logger.info("Created Redis search index: %s", index_name)
    except Exception as exc:
        logger.warning("Could not create index %s: %s", index_name, exc)


async def ensure_indexes(redis_client: Any) -> None:
    """Create ``memory_entity_idx`` and ``memory_fulltext_idx`` if absent.

    Idempotent — safe to call on every application startup.

    Args:
        redis_client: An async redis-py client connected to the knowledge DB.
    """
    for index_name, args in (
        (PRIMARY_INDEX_NAME, _PRIMARY_INDEX_ARGS),
        (FULLTEXT_INDEX_NAME, _FULLTEXT_INDEX_ARGS),
    ):
        if not await _index_exists(redis_client, index_name):
            await _create_index(redis_client, args)
        else:
            logger.debug("Index already exists, skipping creation: %s", index_name)
