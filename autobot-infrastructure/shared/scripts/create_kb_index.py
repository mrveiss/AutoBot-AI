#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Create the knowledge base index with the dimensions nomic-embed-text emits.

Talks to Redis with raw FT.* commands via the centralized client, the same way
every other helper in this file does — no redisvl. The schema below is the one
source of truth for the index; it used to be declared twice (once as a redisvl
``IndexSchema`` dict, once as the FT.CREATE argv that actually ran), which left
the two free to drift (#12840).
"""

import logging
import os
import sys
from typing import List

logger = logging.getLogger(__name__)

# Index definition — consumed by _build_index_create_command() and the log line
# that reports what is being created, so both always describe the same index.
INDEX_NAME = "llama_index"
INDEX_PREFIX = "llama_index/vector"
LEGACY_INDEX_NAME = "autobot_kb_768"
# nomic-embed-text emits 768-dimensional vectors; the index must match exactly
# or FT.SEARCH rejects every query vector.
VECTOR_DIM = 768

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import centralized Redis client
from autobot_shared.redis_client import get_redis_client
from autobot_shared.redis_utils import decode_redis_list


def _drop_existing_indexes(r) -> None:
    """Drop existing indexes if they exist.

    Helper for create_index_with_correct_dimensions (Issue #825).
    """
    for index_name in (INDEX_NAME, LEGACY_INDEX_NAME):
        try:
            r.execute_command("FT.DROPINDEX", index_name, "DD")
            logger.info("Dropped existing %s", index_name)
        except Exception as e:
            logger.info("No existing %s to drop: %s", index_name, e)


def _build_index_create_command() -> List:
    """Build FT.CREATE command.

    Helper for create_index_with_correct_dimensions (Issue #825).
    """
    return [
        "FT.CREATE",
        INDEX_NAME,
        "ON",
        "HASH",
        "PREFIX",
        "1",
        INDEX_PREFIX,
        "SCHEMA",
        "id",
        "TAG",
        "doc_id",
        "TAG",
        "text",
        "TEXT",
        "vector",
        "VECTOR",
        "FLAT",
        "6",
        "TYPE",
        "FLOAT32",
        "DIM",
        str(VECTOR_DIM),
        "DISTANCE_METRIC",
        "COSINE",
    ]


def _verify_index_creation(r) -> None:
    """Verify index was created correctly.

    Helper for create_index_with_correct_dimensions (Issue #825).

    ``get_redis_client`` returns a ``decode_responses=True`` client
    (``autobot_shared/redis_management/config.py:61,153``), so ``FT.INFO``
    elements arrive as ``str``, not the ``bytes`` this used to index with
    (#13290) — decode defensively so the walk also works if a caller ever
    passes a non-decoding client.
    """
    info = decode_redis_list(r.execute_command("FT.INFO", INDEX_NAME))
    logger.info("\nIndex created with attributes:")
    for attr in info[info.index("attributes") + 1]:
        if "vector" in attr and "dim" in attr:
            dim_index = attr.index("dim")
            logger.info(f"  Vector dimension: {attr[dim_index + 1]}")


def create_index_with_correct_dimensions():
    """Create the Redis index sized for nomic-embed-text (VECTOR_DIM)."""

    r = get_redis_client(database="main")
    if r is None:
        logger.error("Error: Could not connect to Redis")
        return False

    _drop_existing_indexes(r)

    create_cmd = _build_index_create_command()

    logger.info("Creating index with schema:")
    logger.info("  Name: %s", INDEX_NAME)
    logger.info("  Prefix: %s", INDEX_PREFIX)
    logger.info("  Vector dimensions: %d", VECTOR_DIM)

    try:
        result = r.execute_command(*create_cmd)
        logger.info(f"Index created successfully: {result}")

        _verify_index_creation(r)

    except Exception as e:
        logger.error(f"Error creating index: {e}")
        return False

    return True


if __name__ == "__main__":
    success = create_index_with_correct_dimensions()
    if success:
        logger.info("\nIndex created successfully with %d dimensions!", VECTOR_DIM)
        logger.info("You can now run populate_knowledge_base.py")
    else:
        logger.error("\nFailed to create index")
