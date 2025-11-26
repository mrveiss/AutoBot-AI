#!/usr/bin/env python3
"""
Simple test to verify knowledge base initialization without search
"""

import asyncio
import sys
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

async def test_simple_init():
    print("🧠 Testing Simple Knowledge Base Initialization")

    try:
        from src.knowledge_base_factory import get_knowledge_base

        print("1. Creating knowledge base instance...")
        kb = await get_knowledge_base(force_reinit=True)

        if kb and kb.initialized:
            print("✅ Knowledge base initialized successfully!")

            print("2. Testing Redis connection...")
            redis_status = await kb.ping_redis()
            print(f"   Redis status: {redis_status}")

            print("3. Getting basic stats...")
            stats = kb.get_stats()
            print(f"   Documents: {stats.get('total_documents', 0)}")
            print(f"   Initialized: {stats.get('initialized', False)}")

            print("4. Checking vector store...")
            has_vector_store = hasattr(kb, 'vector_store') and kb.vector_store is not None
            print(f"   Vector store available: {has_vector_store}")

            await kb.close()
            print("✅ Test completed successfully!")
            return True
        else:
            print("❌ Knowledge base initialization failed")
            return False

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_simple_init())
    sys.exit(0 if success else 1)
