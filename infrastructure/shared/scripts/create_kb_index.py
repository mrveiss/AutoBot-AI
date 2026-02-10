#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Create knowledge base index with correct dimensions using redisvl directly.
"""

import os
import sys

import logging

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import centralized Redis client
from utils.redis_client import get_redis_client


def _drop_existing_indexes(r) -> None:
    """Drop existing indexes if they exist.

    Helper for create_index_with_correct_dimensions (Issue #825).
    """
    try:
        r.execute_command("FT.DROPINDEX", "llama_index", "DD")
        logger.info("Dropped existing llama_index")
    except Exception as e:
        logger.info(f"No existing llama_index to drop: {e}")

    try:
        r.execute_command("FT.DROPINDEX", "autobot_kb_768", "DD")
        logger.info("Dropped existing autobot_kb_768")
    except Exception as e:
        logger.info(f"No existing autobot_kb_768 to drop: {e}")


def _build_index_create_command() -> List:
    """Build FT.CREATE command.

    Helper for create_index_with_correct_dimensions (Issue #825).
    """
    return [
        "FT.CREATE",
        "llama_index",
        "ON",
        "HASH",
        "PREFIX",
        "1",
        "llama_index/vector",
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
        "768",
        "DISTANCE_METRIC",
        "COSINE",
    ]


def _verify_index_creation(r) -> None:
    """Verify index was created correctly.

    Helper for create_index_with_correct_dimensions (Issue #825).
    """
    info = r.execute_command("FT.INFO", "llama_index")
    logger.info("\nIndex created with attributes:")
    for attr in info[info.index(b"attributes") + 1]:
        if b"vector" in attr and b"dim" in attr:
            dim_index = attr.index(b"dim")
            logger.info(f"  Vector dimension: {attr[dim_index + 1]}")


def create_index_with_correct_dimensions():
    """Create Redis index with 768 dimensions for nomic-embed-text."""

    r = get_redis_client(database="main")
    if r is None:
        logger.error("Error: Could not connect to Redis")
        return False

    _drop_existing_indexes(r)

    schema_dict = {
        "index": {
            "name": "llama_index",
            "prefix": "llama_index/vector",
            "storage_type": "hash",
        },
        "fields": [
            {"name": "id", "type": "tag"},
            {"name": "doc_id", "type": "tag"},
            {"name": "text", "type": "text"},
            {
                "name": "vector",
                "type": "vector",
                "attrs": {
                    "dims": 768,
                    "algorithm": "flat",
                    "distance_metric": "cosine",
                },
            },
        ],
    }

    schema = IndexSchema.from_dict(schema_dict)

    logger.info("Creating index with schema:")
    logger.info(f"  Name: {schema.index.name}")
    logger.info("  Vector dimensions: 768")

    try:
        create_cmd = _build_index_create_command()

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
        logger.info("\nIndex created successfully with 768 dimensions!")
        logger.info("You can now run populate_knowledge_base.py")
    else:
        logger.error("\nFailed to create index")
