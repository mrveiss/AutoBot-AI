#!/usr/bin/env python3
"""
Test script to directly test the new Knowledge Base stats functionality
This bypasses the API layer and tests the updated knowledge_base.py directly
"""

import asyncio
import sys
import os

# Add the src directory to path
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

from src.knowledge_base import KnowledgeBase


async def test_kb_stats():
    """Test the updated knowledge base stats functionality"""
    print("=== Testing Updated Knowledge Base Stats ===")

    try:
        # Create knowledge base instance
        print("Initializing Knowledge Base...")
        kb = KnowledgeBase()

        # Wait a bit for async initialization
        await asyncio.sleep(2)

        print("Getting stats...")
        stats = await kb.get_stats()

        print("\n📊 Knowledge Base Stats:")
        print(f"   Total Documents: {stats.get('total_documents', 'N/A')}")
        print(f"   Total Chunks: {stats.get('total_chunks', 'N/A')}")
        print(f"   Total Facts: {stats.get('total_facts', 'N/A')}")
        print(f"   Categories: {stats.get('categories', [])}")
        print(f"   Status: {stats.get('status', 'N/A')}")

        # Show debugging info if available
        if 'indexed_documents' in stats:
            print(f"   Indexed Documents: {stats['indexed_documents']}")
            print(f"   Vector Index Sync: {stats.get('vector_index_sync', 'N/A')}")

        # Test detailed stats
        print("\nGetting detailed stats...")
        detailed = await kb.get_detailed_stats()

        print("\n📈 Detailed Stats:")
        if detailed.get('memory_usage_mb'):
            print(f"   Memory Usage: {detailed['memory_usage_mb']} MB")
        if detailed.get('vector_store_health'):
            print(f"   Vector Store Health: {detailed['vector_store_health']}")
        if detailed.get('health_recommendation'):
            print(f"   Recommendation: {detailed['health_recommendation']}")

        # Test search functionality
        print("\nTesting search functionality...")
        search_results = await kb.search("linux", similarity_top_k=3)
        print(f"   Search results for 'linux': {len(search_results)} results")

        if search_results:
            for i, result in enumerate(search_results[:2]):  # Show first 2 results
                print(f"   Result {i+1}: {result.get('content', '')[:100]}...")

        return stats

    except Exception as e:
        print(f"❌ Error testing knowledge base: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    result = asyncio.run(test_kb_stats())

    if result and result.get('total_documents', 0) > 10:
        print("\n✅ SUCCESS: Knowledge Base is working and showing realistic stats!")
    else:
        print("\n❌ ISSUE: Knowledge Base stats are still showing low numbers")