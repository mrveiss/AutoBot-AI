#!/usr/bin/env python3
"""Direct test of Knowledge Base V2 to identify vector indexing issues"""
import asyncio
import sys
import logging

# Setup logging to see ALL details
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(name)s - %(message)s')

async def main():
    try:
        print("=" * 80)
        print("KNOWLEDGE BASE V2 DIRECT TEST")
        print("=" * 80)

        # Import and create KB
        print("\n1. Importing KnowledgeBaseV2...")
        from src.knowledge_base_v2 import KnowledgeBaseV2
        kb = KnowledgeBaseV2()
        print("✓ KB instance created")

        # Initialize
        print("\n2. Initializing KB (this should show all initialization logs)...")
        success = await kb.initialize()
        print(f"✓ KB initialization result: {success}")

        if not success:
            print("✗ Initialization failed!")
            return

        # Check state
        print("\n3. Checking KB state...")
        print(f"  - initialized: {kb.initialized}")
        print(f"  - vector_store: {kb.vector_store is not None}")
        print(f"  - vector_index: {kb.vector_index is not None}")
        print(f"  - llama_index_configured: {kb.llama_index_configured}")

        # Get stats
        print("\n4. Getting stats...")
        stats = await kb.get_stats()
        print(f"  - total_facts: {stats.get('total_facts')}")
        print(f"  - total_documents: {stats.get('total_documents')}")
        print(f"  - total_vectors: {stats.get('total_vectors')}")

        # Store a test fact
        print("\n5. Storing a test fact...")
        result = await kb.store_fact("Test fact for vector indexing validation", {"category": "test"})
        print(f"  - status: {result.get('status')}")
        print(f"  - message: {result.get('message')}")
        print(f"  - vector_indexed: {result.get('vector_indexed')}")
        print(f"  - searchable: {result.get('searchable')}")

        # Check stats again
        print("\n6. Checking stats after store...")
        stats = await kb.get_stats()
        print(f"  - total_facts: {stats.get('total_facts')}")
        print(f"  - total_documents: {stats.get('total_documents')}")
        print(f"  - total_vectors: {stats.get('total_vectors')}")

        print("\n" + "=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
