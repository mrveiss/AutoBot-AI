#!/usr/bin/env python3
"""
Test the specific fix needed for LlamaIndex Redis integration
"""

import asyncio
import logging
import sys

sys.path.insert(0, '/home/kali/Desktop/AutoBot')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_current_knowledge_base():
    """Test the current knowledge base implementation"""
    logger.info("🧪 Testing current AutoBot knowledge base implementation...")
    
    try:
        # Import the actual knowledge base
        from src.knowledge_base import KnowledgeBase
        from src.config import config as global_config
        
        # Initialize knowledge base
        kb = KnowledgeBase(config_manager=global_config)
        
        # Try to initialize
        logger.info("Initializing knowledge base...")
        await kb.ainit()
        logger.info("✅ Knowledge base initialization successful")
        
        # Test search functionality
        logger.info("Testing search functionality...")
        results = await kb.search("deployment configuration", n_results=3)
        
        logger.info(f"✅ Search successful: {len(results)} results found")
        for i, result in enumerate(results):
            logger.info(f"  Result {i+1}: {result['content'][:100]}... (score: {result.get('score', 'N/A')})")
        
        return True, len(results)
        
    except Exception as e:
        logger.error(f"❌ Current knowledge base test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False, 0

async def test_minimal_llamaindex_fix():
    """Test minimal fix for LlamaIndex"""
    logger.info("\n🔧 Testing minimal LlamaIndex fix...")
    
    try:
        from llama_index.vector_stores.redis import RedisVectorStore
        from llama_index.vector_stores.redis.schema import RedisVectorStoreSchema
        from llama_index.embeddings.ollama import OllamaEmbedding
        from llama_index.llms.ollama import Ollama
        from llama_index.core import VectorStoreIndex, Settings
        
        # Use a working model
        llm = Ollama(model="gemma3:270m", base_url="http://localhost:11434")
        embed_model = OllamaEmbedding(
            model_name="nomic-embed-text:latest",
            base_url="http://localhost:11434"
        )
        
        # CRITICAL: Set global settings BEFORE creating any indices
        Settings.llm = llm
        Settings.embed_model = embed_model
        
        # Connect to existing data
        schema = RedisVectorStoreSchema(
            index_name="llama_index",
            prefix="llama_index/vector",
            overwrite=False
        )
        
        vector_store = RedisVectorStore(
            schema=schema,
            redis_url="redis://localhost:6379",
            redis_kwargs={"db": 2}
        )
        
        # Load existing index
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=embed_model
        )
        
        # Create query engine
        query_engine = index.as_query_engine(llm=llm)
        
        # Test query
        response = await asyncio.to_thread(
            query_engine.query, 
            "deployment configuration kubernetes"
        )
        
        result_count = len(response.source_nodes) if hasattr(response, 'source_nodes') else 0
        logger.info(f"✅ Fixed LlamaIndex successful: {result_count} results")
        
        if result_count > 0:
            logger.info(f"Response: {str(response)[:200]}...")
            for i, node in enumerate(response.source_nodes[:2]):
                logger.info(f"  Source {i+1}: {node.text[:100]}...")
        
        return True, result_count
        
    except Exception as e:
        logger.error(f"❌ LlamaIndex fix test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False, 0

async def main():
    logger.info("🔧 Testing AutoBot LlamaIndex Redis Integration Fix\n")
    
    # Test current implementation
    current_success, current_count = await test_current_knowledge_base()
    
    # Test minimal fix
    fix_success, fix_count = await test_minimal_llamaindex_fix()
    
    print("\n" + "="*60)
    print("📊 LLAMAINDEX FIX ANALYSIS")
    print("="*60)
    print(f"Current implementation working: {'✅' if current_success else '❌'} ({current_count} results)")
    print(f"Minimal fix working: {'✅' if fix_success else '❌'} ({fix_count} results)")
    
    if fix_success and fix_count > 0:
        print("\n✅ CONCLUSION: LlamaIndex can be easily fixed!")
        print("🔧 Required fix: Update knowledge_base.py LLM model configuration")
        print("⏱️  Estimated time: 15-30 minutes")
        print("🎯 Preserve existing 13,383 vectors without migration")
    elif current_success:
        print("\n✅ CONCLUSION: Current implementation already works!")
        print("🎯 No fixes needed - knowledge base is functional")
    else:
        print("\n❌ CONCLUSION: LlamaIndex needs deeper investigation")
        print("🔧 May need LLM configuration debugging or library updates")

if __name__ == "__main__":
    asyncio.run(main())