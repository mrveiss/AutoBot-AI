#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Script to reset and recreate the knowledge base index with correct dimensions.
"""

import asyncio
import logging
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import global_config_manager
from utils.redis_client import get_redis_client

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def reset_knowledge_base_index():
    """Reset the knowledge base Redis index to use correct embedding dimensions."""

    redis_client = get_redis_client(async_client=True)
    if not redis_client:
        logger.error("Redis client not available")
        return

    index_name = global_config_manager.get_nested(
        "memory.redis.index_name", "autobot_knowledge_index"
    )

    logger.info("Resetting knowledge base index: %s", index_name)

    try:
        # Get all keys for the index
        pattern = f"{index_name}:*"
        keys = await redis_client.keys(pattern)

        if keys:
            logger.info("Found %s keys to delete", len(keys))
            # Delete all keys
            for key in keys:
                await redis_client.delete(key)
            logger.info("All keys deleted")
        else:
            logger.info("No existing keys found")

        # Try to drop the index itself using FT.DROPINDEX
        try:
            await redis_client.execute_command("FT.DROPINDEX", index_name)
            logger.info("Dropped index: %s", index_name)
        except Exception as e:
            logger.info("Could not drop index (may not exist): %s", e)

        logger.info("")
        logger.info("Knowledge base index has been reset.")
        logger.info(
            "The index will be recreated with correct dimensions when you add documents."
        )

    except Exception as e:
        logger.error("Error resetting knowledge base: %s", e)


if __name__ == "__main__":
    asyncio.run(reset_knowledge_base_index())
