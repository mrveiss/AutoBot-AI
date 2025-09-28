#!/usr/bin/env python3
"""
Test knowledge base search functionality
"""

import asyncio
import sys
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

async def test_search():
    print("🔍 Testing Knowledge Base Search")

    try:
        from src.knowledge_base_factory import get_knowledge_base

        print("1. Initializing knowledge base...")
        kb = await get_knowledge_base(force_reinit=True)

        if not kb or not kb.initialized:
            print("❌ Knowledge base not initialized")
            return False

        print("2. Checking vector data manually...")
        # Check Redis directly for vector count
        if hasattr(kb, 'redis_client') and kb.redis_client:
            vector_keys = []
            for key in kb.redis_client.scan_iter(match="llama_index/vector_*"):
                vector_keys.append(key)
            print(f"   Found {len(vector_keys)} vector keys in Redis")

        print("3. Testing simple search...")
        try:
            results = await kb.search("AutoBot", top_k=2)
            print(f"   Search returned {len(results)} results")

            if results:
                for i, result in enumerate(results, 1):
                    content = result.get('content', '')[:100] + '...' if len(result.get('content', '')) > 100 else result.get('content', '')
                    score = result.get('score', 0)
                    print(f"   Result {i}: Score {score:.3f} - {content}")
            else:
                print("   No search results found")

        except Exception as search_error:
            print(f"   Search failed: {search_error}")

        await kb.close()
        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_search())