#!/usr/bin/env python3
"""
Test script to verify knowledge base can access existing vectors
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.knowledge_base import KnowledgeBase
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    try:
        print("🧪 Testing Knowledge Base vector access...")
        kb = KnowledgeBase()

        # Wait for initialization
        max_wait = 10
        for i in range(max_wait):
            if kb.redis_client is not None:
                print(f"✅ KB initialized after {i} seconds")
                break
            await asyncio.sleep(1)
        else:
            print("❌ KB failed to initialize after 10 seconds")
            return

        # Test Redis connection
        if kb.redis_client:
            ping_result = await asyncio.to_thread(kb.redis_client.ping)
            print(f"✅ Redis ping: {ping_result}")
        else:
            print("❌ No Redis client available")
            return

        # Check vector store initialization
        if kb.vector_store:
            print("✅ Vector store initialized successfully")
        else:
            print("❌ Vector store not initialized")

        # Get stats to see if vectors are now accessible
        print("\n📊 Getting knowledge base stats...")
        stats = await kb.get_stats()
        print(f"📊 Stats: {stats}")

        # Test search functionality
        print("\n🔍 Testing search functionality...")
        try:
            search_results = await kb.search("AutoBot", similarity_top_k=3)
            print(f"✅ Search successful! Found {len(search_results)} results")

            if search_results:
                print(f"📄 Sample result text: {search_results[0].get('text', '')[:100]}...")

        except Exception as e:
            print(f"❌ Search failed: {e}")

        print("\n✅ Knowledge Base testing completed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())