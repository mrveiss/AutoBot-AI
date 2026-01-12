#!/usr/bin/env python3
"""
Fix Redis index dimensions to match existing vector data
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging

logging.basicConfig(level=logging.INFO)

# Import canonical Redis client utility
from src.utils.redis_client import get_redis_client


async def main():
    try:
        print("🔧 Fixing Redis index dimensions to match existing vectors...")

        # Connect to Redis using canonical pattern
        redis_client = get_redis_client(database="knowledge", async_client=False)

        # Test connection
        print(f"✅ Connected to Redis: {redis_client.ping()}")

        # Check current index info
        try:
            current_info = redis_client.execute_command('FT.INFO', 'llama_index')
            print("📊 Current index info:")
            for i in range(0, len(current_info), 2):
                if current_info[i] in ['num_docs', 'dim']:
                    print(f"  {current_info[i]}: {current_info[i+1]}")
        except Exception as e:
            print(f"ℹ️ Could not get current index info: {e}")

        # Drop the existing index (keeps the data, just removes the index)
        print("🗑️ Dropping existing index...")
        try:
            redis_client.execute_command('FT.DROPINDEX', 'llama_index')
            print("✅ Index dropped successfully")
        except Exception as e:
            print(f"ℹ️ Could not drop index (might not exist): {e}")

        # Create new index with correct dimensions (384 for all-MiniLM-L6-v2)
        print("🔨 Creating new index with 384 dimensions...")
        create_command = [
            'FT.CREATE', 'llama_index',
            'ON', 'HASH',
            'PREFIX', '1', 'llama_index/vector_',
            'SCHEMA',
            'id', 'TEXT',
            'doc_id', 'TEXT',
            'text', 'TEXT',
            'vector', 'VECTOR', 'HNSW', '6',
            'TYPE', 'FLOAT32',
            'DIM', '384',  # Match existing vector dimensions
            'DISTANCE_METRIC', 'COSINE'
        ]

        try:
            result = redis_client.execute_command(*create_command)
            print(f"✅ Index created successfully: {result}")
        except Exception as e:
            print(f"❌ Failed to create index: {e}")
            return

        # Wait a moment for indexing to start
        await asyncio.sleep(2)

        # Check the new index status
        try:
            new_info = redis_client.execute_command('FT.INFO', 'llama_index')
            print("📊 New index info:")
            for i in range(0, len(new_info), 2):
                if new_info[i] in ['num_docs', 'dim', 'percent_indexed']:
                    print(f"  {new_info[i]}: {new_info[i+1]}")
        except Exception as e:
            print(f"❌ Could not get new index info: {e}")

        # Count vectors
        vector_count = len(redis_client.keys("llama_index/vector_*"))
        print(f"📦 Total vectors in Redis: {vector_count}")

        print("✅ Index dimension fix completed!")
        print("⏳ Note: It may take a few minutes for all vectors to be indexed.")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
