#!/usr/bin/env python3
"""
Test the fixed knowledge base stats method
"""

import asyncio
import logging
import sys

sys.path.insert(0, '/home/kali/Desktop/AutoBot')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_knowledge_base_stats():
    """Test the knowledge base stats functionality"""
    logger.info("🧪 Testing knowledge base stats...")
    
    try:
        # Import the knowledge base
        from src.knowledge_base import KnowledgeBase
        from src.config import config as global_config
        
        # Initialize knowledge base
        kb = KnowledgeBase(config_manager=global_config)
        
        # Initialize
        logger.info("Initializing knowledge base...")
        await kb.ainit()
        logger.info("✅ Knowledge base initialized")
        
        # Test stats
        logger.info("Getting knowledge base stats...")
        stats = await kb.get_stats()
        
        logger.info("✅ Stats retrieved successfully")
        logger.info(f"📊 Knowledge Base Statistics:")
        logger.info(f"  • Total Documents: {stats['total_documents']:,}")
        logger.info(f"  • Total Chunks: {stats['total_chunks']:,}")
        logger.info(f"  • Total Facts: {stats['total_facts']:,}")
        logger.info(f"  • Categories: {stats['categories']}")
        
        # Test a few searches to verify everything works
        logger.info("\nTesting search functionality...")
        results = await kb.search("deployment configuration", top_k=2)
        logger.info(f"✅ Search test: {len(results)} results found")
        
        return True, stats
        
    except Exception as e:
        logger.error(f"❌ Knowledge base stats test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False, {}

async def main():
    logger.info("🔧 Testing AutoBot Knowledge Base Stats Fix\n")
    
    success, stats = await test_knowledge_base_stats()
    
    print("\n" + "="*60)
    print("📊 KNOWLEDGE BASE STATS TEST RESULTS")
    print("="*60)
    print(f"Stats retrieval working: {'✅' if success else '❌'}")
    
    if success:
        total_docs = stats.get('total_documents', 0)
        if total_docs > 13000:
            print(f"✅ CONCLUSION: Stats fix successful!")
            print(f"🎯 Correctly reporting {total_docs:,} documents from Redis vector store")
            print(f"📈 Knowledge base is properly connected to existing data")
        else:
            print(f"⚠️ CONCLUSION: Stats working but document count seems low ({total_docs})")
    else:
        print("❌ CONCLUSION: Stats fix needs more work")

if __name__ == "__main__":
    asyncio.run(main())