#!/usr/bin/env python3
"""
Fix knowledge base dimension mismatch by recreating with correct settings.
"""

import asyncio
import os
import sys

import redis

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def fix_dimensions():
    """Drop all llama_index traces and let it recreate properly."""

    # Connect to Redis
    r = redis.Redis(host="localhost", port=6379, db=0)

    print("Cleaning up Redis...")

    # Drop the index if it exists
    try:
        r.execute_command("FT.DROPINDEX", "llama_index", "DD")
        print("Dropped llama_index")
    except Exception as e:
        print(f"Index drop: {e}")

    # Clean all databases
    for db in range(16):
        r_db = redis.Redis(host="localhost", port=6379, db=db)
        try:
            # Delete any llama_index related keys
            keys = r_db.keys("llama_index:*")
            if keys:
                for key in keys:
                    r_db.delete(key)
                print(f"Cleaned {len(keys)} keys from DB {db}")

            # Also look for doc: prefixed keys
            doc_keys = r_db.keys("doc:*")
            if doc_keys:
                for key in doc_keys:
                    r_db.delete(key)
                print(f"Cleaned {len(doc_keys)} doc keys from DB {db}")
        except Exception as e:
            print(f"DB {db}: {e}")

    print("\nRedis cleanup complete!")
    print("\nNow testing with correct embedding model...")

    from src.knowledge_base import KnowledgeBase

    # Create a fresh knowledge base
    kb = KnowledgeBase()
    print(f"Knowledge base will use Redis DB: {kb.redis_db}")

    # Initialize it
    await kb.ainit()
    print("Knowledge base initialized")

    # Test adding a simple document
    test_content = "AutoBot is an autonomous AI agent platform."
    from llama_index.core import Document

    try:
        doc = Document(text=test_content, metadata={"source": "test"})
        kb.index.insert(doc)
        print("Successfully added test document!")

        # Test search
        results = await kb.search("AutoBot", n_results=1)
        print(f"Search test: Found {len(results)} results")

        return True
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(fix_dimensions())
    if success:
        print("\nKnowledge base is now ready! You can run populate_knowledge_base.py")
    else:
        print("\nFailed to fix dimensions issue")
