#!/usr/bin/env python3
"""
Test Knowledge Base Initialization

This script verifies that the knowledge base is properly initializing
its vector store during startup.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_initialization():
    """Test knowledge base initialization"""
    try:
        logger.info("=" * 80)
        logger.info("TESTING KNOWLEDGE BASE INITIALIZATION")
        logger.info("=" * 80)

        # Step 1: Import and create knowledge base
        logger.info("\n[1/5] Importing KnowledgeBaseV2...")
        from src.knowledge_base_v2 import KnowledgeBaseV2

        kb = KnowledgeBaseV2()
        logger.info(f"✅ KnowledgeBaseV2 instance created")
        logger.info(f"    - initialized: {kb.initialized}")
        logger.info(f"    - redis_client: {kb.redis_client}")
        logger.info(f"    - vector_store: {kb.vector_store}")
        logger.info(f"    - vector_index: {kb.vector_index}")

        # Step 2: Call initialize()
        logger.info("\n[2/5] Calling kb.initialize()...")
        result = await kb.initialize()
        logger.info(f"✅ Initialization completed: {result}")
        logger.info(f"    - initialized: {kb.initialized}")
        logger.info(f"    - llama_index_configured: {kb.llama_index_configured}")
        logger.info(f"    - redis_client exists: {kb.redis_client is not None}")
        logger.info(f"    - aioredis_client exists: {kb.aioredis_client is not None}")
        logger.info(f"    - vector_store exists: {kb.vector_store is not None}")
        logger.info(f"    - vector_index exists: {kb.vector_index is not None}")

        # Step 3: Check Redis connection
        logger.info("\n[3/5] Testing Redis connection...")
        if kb.redis_client:
            ping_result = await asyncio.to_thread(kb.redis_client.ping)
            logger.info(f"✅ Redis sync ping: {ping_result}")
        else:
            logger.error("❌ Redis sync client is None")

        if kb.aioredis_client:
            ping_result = await kb.aioredis_client.ping()
            logger.info(f"✅ Redis async ping: {ping_result}")
        else:
            logger.error("❌ Redis async client is None")

        # Step 4: Check vector store
        logger.info("\n[4/5] Checking vector store...")
        if kb.vector_store:
            logger.info(f"✅ Vector store initialized")
            logger.info(f"    - Schema: {kb.vector_store.schema if hasattr(kb.vector_store, 'schema') else 'N/A'}")
        else:
            logger.error("❌ Vector store is None - THIS IS THE PROBLEM!")
            logger.error("    Facts will be stored but NOT indexed for search")

        # Step 5: Get stats
        logger.info("\n[5/5] Getting knowledge base stats...")
        stats = await kb.get_stats()
        logger.info(f"✅ Stats retrieved:")
        logger.info(f"    - total_facts: {stats['total_facts']}")
        logger.info(f"    - total_documents: {stats['total_documents']}")
        logger.info(f"    - total_vectors: {stats['total_vectors']}")
        logger.info(f"    - initialized: {stats['initialized']}")
        logger.info(f"    - llama_index_configured: {stats['llama_index_configured']}")

        # Final verdict
        logger.info("\n" + "=" * 80)
        logger.info("INITIALIZATION TEST RESULTS:")
        logger.info("=" * 80)

        if kb.vector_store is None:
            logger.error("❌ FAILED: Vector store not initialized")
            logger.error("   Root Cause: Vector store initialization failed silently")
            logger.error("   Impact: Facts stored but not searchable via vector search")
            return False
        elif stats['total_facts'] > 0 and stats['total_vectors'] == 0:
            logger.warning("⚠️  PARTIAL: Vector store initialized but no documents indexed")
            logger.warning("   Possible Cause: Existing facts not re-indexed after vector store creation")
            logger.warning("   Solution: Need to re-index existing facts")
            return True
        else:
            logger.info("✅ SUCCESS: Knowledge base fully initialized and operational")
            return True

    except Exception as e:
        logger.error(f"❌ Test failed with exception: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = asyncio.run(test_initialization())
    sys.exit(0 if success else 1)
