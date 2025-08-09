#!/usr/bin/env python3
"""
Fresh knowledge base setup - let llama_index create everything from scratch.
"""

import asyncio
import os
import sys
import redis

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def fresh_setup():
    """Complete fresh setup of knowledge base."""

    print("=== Fresh Knowledge Base Setup ===")

    # Step 1: Clean Redis completely
    print("\n1. Cleaning Redis...")
    r = redis.Redis(host="localhost", port=6379, db=0)

    # Drop any existing indexes
    try:
        indexes = r.execute_command("FT._LIST")
        for idx in indexes:
            idx_name = idx.decode() if isinstance(idx, bytes) else idx
            r.execute_command("FT.DROPINDEX", idx_name, "DD")
            print(f"   Dropped index: {idx_name}")
    except Exception as e:
        print(f"   No indexes to drop: {e}")

    # Clean all databases
    for db in range(16):
        r_db = redis.Redis(host="localhost", port=6379, db=db)
        r_db.flushdb()
        print(f"   Flushed database {db}")

    print("   Redis cleaned!")

    # Step 2: Initialize knowledge base fresh
    print("\n2. Initializing fresh knowledge base...")

    # Import after cleaning
    from src.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    print(f"   Will use embedding model: {kb.embedding_model_name}")
    print(f"   Will use Redis DB: {kb.redis_db}")
    print(f"   Will use index name: {kb.redis_index_name}")

    # Initialize
    await kb.ainit()
    print("   Knowledge base initialized!")

    # Step 3: Test with a simple document
    print("\n3. Testing with sample document...")

    test_file = "/tmp/test_kb_doc.md"
    with open(test_file, "w") as f:
        f.write(
            """
# AutoBot Documentation Test

AutoBot is an autonomous AI agent platform designed for enterprise use.

## Features
- Multi-agent orchestration
- Redis-based memory
- Knowledge base with vector search
- Vue.js frontend
- FastAPI backend

## Installation
To install AutoBot, follow the setup guide in the README.
"""
        )

    result = await kb.add_file(
        file_path=test_file,
        file_type="txt",
        metadata={"source": "test", "category": "documentation"},
    )

    print(f"   Add result: {result}")

    if result["status"] == "success":
        # Test search
        results = await kb.search("AutoBot features", n_results=2)
        print(f"\n4. Search test results: {len(results)} found")
        if results:
            print(f"   First result score: {results[0].get('score', 0)}")
            print(f"   Content preview: {results[0].get('content', '')[:100]}...")

        # Check the index
        print("\n5. Checking created index...")
        indexes = r.execute_command("FT._LIST")
        print(f"   Indexes: {indexes}")

        if indexes:
            idx_name = (
                indexes[0].decode() if isinstance(indexes[0], bytes) else indexes[0]
            )
            info = r.execute_command("FT.INFO", idx_name)
            attrs_idx = info.index(b"attributes")
            attrs = info[attrs_idx + 1]
            for attr in attrs:
                if b"vector" in attr:
                    for i, item in enumerate(attr):
                        if item == b"dim":
                            print(f"   Vector dimension: {attr[i+1]}")
                            break

        return True
    else:
        print(f"\n   Error: {result.get('message', 'Unknown error')}")
        return False


if __name__ == "__main__":
    success = asyncio.run(fresh_setup())
    if success:
        print("\n✓ Knowledge base setup successful!")
        print("You can now run populate_knowledge_base.py")
    else:
        print("\n✗ Knowledge base setup failed!")
