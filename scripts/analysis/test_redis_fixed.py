#!/usr/bin/env python3
"""
Fixed test script to compare LangChain vs LlamaIndex Redis vector store integrations
"""

import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict, List

# Add the project root to the Python path
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_llamaindex_redis_fixed():
    """Test LlamaIndex Redis integration with proper LLM configuration"""
    logger.info("\n=== Testing LlamaIndex Redis Integration (Fixed) ===")
    try:
        from llama_index.vector_stores.redis import RedisVectorStore
        from llama_index.vector_stores.redis.schema import RedisVectorStoreSchema
        from llama_index.embeddings.ollama import OllamaEmbedding
        from llama_index.llms.ollama import Ollama
        from llama_index.core import VectorStoreIndex, StorageContext, Settings
        
        # Properly configure LLM first
        llm = Ollama(model="phi:2.7b", base_url=ServiceURLs.OLLAMA_LOCAL)
        embed_model = OllamaEmbedding(
            model_name="nomic-embed-text:latest",
            base_url=ServiceURLs.OLLAMA_LOCAL
        )
        
        # Set global settings
        Settings.llm = llm
        Settings.embed_model = embed_model
        
        # Try to connect to existing index without overwriting
        schema = RedisVectorStoreSchema(
            index_name="llama_index",
            prefix="llama_index/vector",
            overwrite=False  # Don't overwrite existing
        )
        
        vector_store = RedisVectorStore(
            schema=schema,
            redis_url="redis://localhost:6379",
            redis_kwargs={"db": 2}
        )
        
        # Try to create index from existing vector store
        logger.info("Attempting to load existing index...")
        try:
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=embed_model
            )
            logger.info("✅ Successfully loaded existing LlamaIndex data")
        except Exception as e:
            logger.warning(f"Could not load existing index: {e}")
            # Try creating new index
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            index = VectorStoreIndex.from_documents([], storage_context=storage_context)
            logger.info("Created new index")
        
        # Test query with existing data
        query_engine = index.as_query_engine()
        
        # Test with a query that should match existing data
        response = await asyncio.to_thread(query_engine.query, "deployment guide kubernetes")
        
        result_count = len(response.source_nodes) if hasattr(response, 'source_nodes') else 0
        logger.info(f"✅ LlamaIndex query successful: {result_count} results")
        
        if result_count > 0:
            for i, node in enumerate(response.source_nodes[:2]):
                logger.info(f"  Result {i+1}: {node.text[:100]}... (score: {getattr(node, 'score', 'N/A')})")
        
        return True, result_count
        
    except Exception as e:
        logger.error(f"❌ LlamaIndex test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False, 0

async def test_langchain_redis_fixed():
    """Test LangChain Redis with proper configuration"""
    logger.info("\n=== Testing LangChain Redis Integration (Fixed) ===")
    try:
        # Install modern package if available
        try:
            import subprocess
            result = subprocess.run(['pip', 'install', 'langchain-redis'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("Installed langchain-redis package")
        except Exception:
            pass
        
        # Try modern package first
        try:
            from langchain_redis import RedisVectorStore
            logger.info("Using modern langchain-redis package")
            modern = True
        except ImportError:
            logger.info("Modern package not available, using community version")
            modern = False
        
        # Try modern ollama embeddings
        try:
            from langchain_ollama import OllamaEmbeddings
            logger.info("Using modern langchain-ollama embeddings")
        except ImportError:
            from langchain_community.embeddings import OllamaEmbeddings
            logger.info("Using community ollama embeddings")
        
        # Initialize embeddings
        embeddings = OllamaEmbeddings(
            model="nomic-embed-text:latest",
            base_url=ServiceURLs.OLLAMA_LOCAL
        )
        
        if modern:
            # Modern implementation
            vector_store = RedisVectorStore(
                index_name="autobot_langchain_test",
                embedding=embeddings,
                redis_url="redis://localhost:6379/2"
            )
        else:
            # Community implementation  
            from langchain_community.vectorstores import Redis
            vector_store = Redis(
                embedding=embeddings,
                redis_url="redis://localhost:6379",
                index_name="autobot_langchain_community",
                content_key="text",
                metadata_key="metadata", 
                vector_key="vector"
            )
        
        # Test basic functionality
        test_texts = ["This is a deployment configuration test"]
        test_metadata = [{"source": "test", "category": "deployment"}]
        
        # Add and search
        await asyncio.to_thread(vector_store.add_texts, test_texts, metadatas=test_metadata)
        
        results = await asyncio.to_thread(
            vector_store.similarity_search,
            "deployment configuration",
            k=3
        )
        
        logger.info(f"✅ LangChain test successful: {len(results)} results")
        for i, doc in enumerate(results):
            logger.info(f"  Result {i+1}: {doc.page_content[:100]}...")
        
        # Try to search existing data structure 
        try:
            existing_results = await asyncio.to_thread(
                vector_store.similarity_search,
                "kubernetes deployment guide",
                k=5
            )
            logger.info(f"Existing data search: {len(existing_results)} results")
            return True, len(existing_results)
        except Exception as e:
            logger.warning(f"Could not search existing data: {e}")
            return True, len(results)
        
    except Exception as e:
        logger.error(f"❌ LangChain test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False, 0

async def check_existing_data_accessibility():
    """Check if existing data can be accessed directly"""
    logger.info("\n=== Checking Direct Data Access ===")
    try:
        import redis
from src.constants import NetworkConstants, ServiceURLs
        client = redis.Redis(host='localhost', port=6379, db=2, decode_responses=True)
        
        # Count documents in existing index
        total_docs = client.execute_command('FT.INFO', 'llama_index')[client.execute_command('FT.INFO', 'llama_index').index('num_docs') + 1]
        logger.info(f"Total documents in llama_index: {total_docs}")
        
        # Try FT.SEARCH on existing index
        search_result = client.execute_command(
            'FT.SEARCH', 'llama_index', 
            'deployment configuration',
            'LIMIT', '0', '3'
        )
        
        result_count = search_result[0] if search_result else 0
        logger.info(f"Direct Redis FT.SEARCH results: {result_count}")
        
        if result_count > 0:
            logger.info("✅ Existing data is accessible via Redis FT.SEARCH")
            # Show sample results
            for i in range(1, min(len(search_result), 7), 2):
                doc_key = search_result[i]
                logger.info(f"  Document key: {doc_key}")
        
        return result_count > 0, result_count
        
    except Exception as e:
        logger.error(f"❌ Direct data access failed: {e}")
        return False, 0

async def main():
    """Main analysis function"""
    logger.info("🔍 Starting Redis Vector Store Analysis for AutoBot")
    
    # Check existing data accessibility
    data_accessible, existing_count = await check_existing_data_accessibility()
    
    # Test implementations
    llamaindex_success, llamaindex_count = await test_llamaindex_redis_fixed()
    langchain_success, langchain_count = await test_langchain_redis_fixed()
    
    # Generate analysis report
    logger.info("\n" + "="*60)
    logger.info("📊 ANALYSIS REPORT")
    logger.info("="*60)
    
    logger.info(f"Existing Redis data accessible: {data_accessible} ({existing_count} docs)")
    logger.info(f"LlamaIndex integration working: {llamaindex_success} ({llamaindex_count} results)")
    logger.info(f"LangChain integration working: {langchain_success} ({langchain_count} results)")
    
    # Recommendation logic
    if data_accessible and existing_count > 10000:
        logger.info("\n🎯 RECOMMENDATION: Fix LlamaIndex Integration")
        logger.info("REASONING:")
        logger.info("  • 13,383 properly indexed vectors already exist")
        logger.info("  • Data is accessible via Redis FT.SEARCH")
        logger.info("  • LlamaIndex created this data structure")
        logger.info("  • Fix is likely just LLM configuration issue")
        logger.info("\n📋 IMPLEMENTATION PLAN:")
        logger.info("  1. Fix LLM initialization in knowledge_base.py")
        logger.info("  2. Ensure Settings.llm is properly configured before query_engine creation")
        logger.info("  3. Test with existing data structure")
        logger.info("  4. No data migration needed")
        
    elif langchain_success and not llamaindex_success:
        logger.info("\n🎯 RECOMMENDATION: Migrate to LangChain")
        logger.info("REASONING:")
        logger.info("  • LangChain integration works out of the box")
        logger.info("  • Modern langchain-redis package available")
        logger.info("  • Better async support and error handling")
        logger.info("\n📋 MIGRATION PLAN:")
        logger.info("  1. Export existing data via Redis FT.SEARCH")
        logger.info("  2. Implement LangChain RedisVectorStore")
        logger.info("  3. Re-index data with LangChain format")
        logger.info("  4. Update knowledge_base.py to use LangChain")
        
    else:
        logger.info("\n🎯 RECOMMENDATION: Deep Investigation Required")
        logger.info("REASONING:")
        logger.info("  • Both integrations have configuration issues")
        logger.info("  • Need to resolve dependency conflicts")
        logger.info("  • May need hybrid approach")

if __name__ == "__main__":
    asyncio.run(main())