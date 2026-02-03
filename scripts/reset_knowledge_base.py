#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Script to reset and recreate the knowledge base index with correct dimensions.
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.redis_client import get_redis_client
from src.config import global_config_manager


async def reset_knowledge_base_index():
    """Reset the knowledge base Redis index to use correct embedding dimensions."""

    redis_client = get_redis_client(async_client=True)
    if not redis_client:
        print("Redis client not available")
        return

    index_name = global_config_manager.get_nested(
        "memory.redis.index_name", "autobot_knowledge_index"
    )

    print(f"Resetting knowledge base index: {index_name}")

    try:
        # Get all keys for the index
        pattern = f"{index_name}:*"
        keys = await redis_client.keys(pattern)

        if keys:
            print(f"Found {len(keys)} keys to delete")
            # Delete all keys
            for key in keys:
                await redis_client.delete(key)
            print("All keys deleted")
        else:
            print("No existing keys found")

        # Try to drop the index itself using FT.DROPINDEX
        try:
            await redis_client.execute_command("FT.DROPINDEX", index_name)
            print(f"Dropped index: {index_name}")
        except Exception as e:
            print(f"Could not drop index (may not exist): {e}")

        print("\nKnowledge base index has been reset.")
        print(
            "The index will be recreated with correct dimensions when you add documents."
        )

    except Exception as e:
        print(f"Error resetting knowledge base: {e}")


if __name__ == "__main__":
    asyncio.run(reset_knowledge_base_index())
