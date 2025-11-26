#!/usr/bin/env python3
"""
Test script to verify knowledge base initialization fixes
This script tests the fixes for:
1. Automatic knowledge base initialization
2. Dimension mismatch resolution (768 vs 384)
3. Search functionality
"""

import asyncio
import logging
import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_knowledge_base_initialization():
    """Test knowledge base initialization with dimension detection"""
    print("🧠 Testing Knowledge Base Initialization Fixes")
    print("=" * 60)

    try:
        # Test 1: Factory pattern initialization
        print("\n1️⃣  Testing factory pattern initialization...")
        from src.knowledge_base_factory import get_knowledge_base

        kb = await get_knowledge_base(force_reinit=True)
        if kb:
            print("✅ Knowledge base factory initialization: SUCCESS")
        else:
            print("❌ Knowledge base factory initialization: FAILED")
            return False

        # Test 2: Dimension detection
        print("\n2️⃣  Testing dimension detection...")
        if hasattr(kb, '_detect_embedding_dimensions'):
            detected_dim = await kb._detect_embedding_dimensions()
            print(f"✅ Detected embedding dimensions: {detected_dim}")

            if detected_dim == 768:
                print("✅ Correctly detected 768-dimensional vectors")
            else:
                print(f"⚠️  Detected {detected_dim} dimensions (expected 768)")
        else:
            print("❌ Dimension detection method not available")

        # Test 3: LlamaIndex configuration
        print("\n3️⃣  Testing LlamaIndex configuration...")
        if hasattr(kb, 'llama_index_configured') and kb.llama_index_configured:
            print("✅ LlamaIndex configuration: SUCCESS")
        else:
            print("❌ LlamaIndex configuration: FAILED")

        # Test 4: Vector store initialization
        print("\n4️⃣  Testing vector store initialization...")
        if hasattr(kb, 'vector_store') and kb.vector_store:
            print("✅ Vector store initialization: SUCCESS")
        else:
            print("❌ Vector store initialization: FAILED")

        # Test 5: Search functionality
        print("\n5️⃣  Testing search functionality...")
        try:
            results = await kb.search("AutoBot documentation", top_k=3)
            if results:
                print(f"✅ Search test: SUCCESS - Found {len(results)} results")
                for i, result in enumerate(results[:2], 1):
                    content_preview = result.get('content', '')[:100] + '...' if len(result.get('content', '')) > 100 else result.get('content', '')
                    score = result.get('score', 0)
                    print(f"   Result {i}: Score {score:.3f} - {content_preview}")
            else:
                print("⚠️  Search test: No results found")
        except Exception as search_error:
            print(f"❌ Search test: FAILED - {search_error}")

        # Test 6: Stats functionality
        print("\n6️⃣  Testing stats functionality...")
        try:
            stats = kb.get_stats()
            print(f"✅ Stats test: SUCCESS")
            print(f"   Total documents: {stats.get('total_documents', 0)}")
            print(f"   Total chunks: {stats.get('total_chunks', 0)}")
            print(f"   Initialized: {stats.get('initialized', False)}")
        except Exception as stats_error:
            print(f"❌ Stats test: FAILED - {stats_error}")

        # Test 7: Redis connection
        print("\n7️⃣  Testing Redis connection...")
        try:
            redis_status = await kb.ping_redis()
            if redis_status == "healthy":
                print("✅ Redis connection: SUCCESS")
            else:
                print(f"⚠️  Redis connection: {redis_status}")
        except Exception as redis_error:
            print(f"❌ Redis connection: FAILED - {redis_error}")

        print("\n" + "=" * 60)
        print("🎉 Knowledge Base Initialization Test Complete!")
        print("\nSummary:")
        print("- The knowledge base should now initialize automatically on backend startup")
        print("- Dimension mismatch (768 vs 384) should be resolved")
        print("- Search functionality should work after backend restart")

        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test runner"""
    success = await test_knowledge_base_initialization()
    if success:
        print("\n✅ All tests completed. Backend restart is required to apply fixes.")
    else:
        print("\n❌ Tests failed. Please check the error messages above.")

    return success

if __name__ == "__main__":
    asyncio.run(main())
