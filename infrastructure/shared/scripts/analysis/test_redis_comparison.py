#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test script to compare LangChain vs LlamaIndex Redis vector store integrations
for the AutoBot project's existing Redis data.
"""

import asyncio
import logging
import sys
import time

from src.constants import ServiceURLs

# Add the project root to the Python path
sys.path.insert(0, "/home/kali/Desktop/AutoBot")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_redis_connection():
    """Test basic Redis connectivity"""
    logger.info("=== Testing Redis Connection ===")
    try:
        import redis

        client = redis.Redis(host="localhost", port=6379, db=2, decode_responses=True)
        client.ping()
        logger.info("✅ Redis connection successful")

        # Check existing indices
        try:
            indices = client.execute_command("FT._LIST")
            logger.info(f"Available indices: {indices}")
        except Exception as e:
            logger.warning(f"Could not list indices: {e}")

        # Count existing vectors
        try:
            keys = client.scan_iter(match="llama_index*")
            vector_count = sum(1 for _ in keys)
            logger.info(f"Existing vector documents: {vector_count}")
        except Exception as e:
            logger.warning(f"Could not count vectors: {e}")

        return True
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        return False


async def test_llamaindex_redis():
    """Test LlamaIndex Redis integration with existing data"""
    logger.info("\n=== Testing LlamaIndex Redis Integration ===")
    try:
        from llama_index.core import StorageContext, VectorStoreIndex
        from llama_index.embeddings.ollama import OllamaEmbedding
        from llama_index.vector_stores.redis import RedisVectorStore
        from llama_index.vector_stores.redis.schema import RedisVectorStoreSchema

        # Create schema matching existing data
        schema = RedisVectorStoreSchema(
            index_name="llama_index",
            prefix="llama_index/vector",
            overwrite=False,  # Don't overwrite existing index
        )

        # Initialize vector store
        vector_store = RedisVectorStore(
            schema=schema, redis_url="redis://localhost:6379", redis_kwargs={"db": 2}
        )

        # Test embedding model
        embed_model = OllamaEmbedding(
            model_name="nomic-embed-text:latest", base_url=ServiceURLs.OLLAMA_LOCAL
        )

        # Create index from existing vector store
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            storage_context=storage_context,
            embed_model=embed_model,
        )

        # Test query
        query_engine = index.as_query_engine()
        test_query = "deployment configuration"

        # Wrap synchronous call in thread to prevent blocking
        response = await asyncio.to_thread(query_engine.query, test_query)

        logger.info(
            f"✅ LlamaIndex query successful: {len(response.source_nodes)} results"
        )
        for i, node in enumerate(response.source_nodes[:2]):
            logger.info(f"  Result {i+1}: {node.text[:100]}... (score: {node.score})")

        return True, len(response.source_nodes)

    except Exception as e:
        logger.error(f"❌ LlamaIndex Redis test failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False, 0


async def test_langchain_redis():
    """Test LangChain Redis integration with existing data"""
    logger.info("\n=== Testing LangChain Redis Integration ===")
    try:
        # Try new langchain-redis package first
        try:
            from langchain_redis import RedisVectorStore as LangChainRedisStore

            logger.info("Using new langchain-redis package")
            modern_langchain = True
        except ImportError:
            # Fallback to community package
            from langchain_community.vectorstores.redis import (
                Redis as LangChainRedisStore,
            )

            logger.info("Using langchain-community Redis")
            modern_langchain = False

        from langchain_community.embeddings import OllamaEmbeddings

        # Initialize embedding model
        embeddings = OllamaEmbeddings(
            model="nomic-embed-text:latest", base_url=ServiceURLs.OLLAMA_LOCAL
        )

        if modern_langchain:
            # New langchain-redis implementation
            vector_store = LangChainRedisStore(
                index_name="autobot_langchain",  # Use different index to avoid conflicts
                embedding=embeddings,
                redis_url="redis://localhost:6379/2",
            )
        else:
            # Legacy community implementation
            vector_store = LangChainRedisStore(
                redis_url="redis://localhost:6379",
                index_name="autobot_langchain_legacy",
                embedding_function=embeddings.embed_query,
                content_key="text",
                metadata_key="metadata",
                vector_key="vector",
            )

        # Test with a simple document to see if it can connect
        test_docs = ["This is a test document for LangChain Redis integration"]
        test_metadata = [{"source": "test", "type": "integration_test"}]

        # Add test document
        doc_ids = await asyncio.to_thread(
            vector_store.add_texts, test_docs, metadatas=test_metadata
        )
        logger.info(f"✅ Added test document with IDs: {doc_ids}")

        # Test similarity search
        results = await asyncio.to_thread(
            vector_store.similarity_search, "test document", k=3
        )

        logger.info(f"✅ LangChain similarity search successful: {len(results)} results")
        for i, doc in enumerate(results[:2]):
            logger.info(f"  Result {i+1}: {doc.page_content[:100]}...")

        # Try to access existing LlamaIndex data by changing index
        if modern_langchain:
            try:
                # Try to create vector store pointing to existing index
                existing_store = LangChainRedisStore(
                    index_name="llama_index",  # Existing index
                    embedding=embeddings,
                    redis_url="redis://localhost:6379/2",
                )

                existing_results = await asyncio.to_thread(
                    existing_store.similarity_search, "deployment configuration", k=3
                )
                logger.info(
                    f"✅ Accessed existing data: {len(existing_results)} results"
                )
                return True, len(existing_results)

            except Exception as e:
                logger.warning(f"Could not access existing data: {e}")
                return True, len(results)

        return True, len(results)

    except Exception as e:
        logger.error(f"❌ LangChain Redis test failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False, 0


async def compare_performance():
    """Compare performance characteristics"""
    logger.info("\n=== Performance Comparison ===")

    # Test LlamaIndex performance
    llamaindex_time = 0
    llamaindex_results = 0
    try:
        start_time = time.time()
        success, count = await test_llamaindex_redis()
        llamaindex_time = time.time() - start_time
        llamaindex_results = count if success else 0
        logger.info(f"LlamaIndex: {llamaindex_time:.2f}s, {llamaindex_results} results")
    except Exception as e:
        logger.error(f"LlamaIndex performance test failed: {e}")

    # Test LangChain performance
    langchain_time = 0
    langchain_results = 0
    try:
        start_time = time.time()
        success, count = await test_langchain_redis()
        langchain_time = time.time() - start_time
        langchain_results = count if success else 0
        logger.info(f"LangChain: {langchain_time:.2f}s, {langchain_results} results")
    except Exception as e:
        logger.error(f"LangChain performance test failed: {e}")

    return {
        "llamaindex": {"time": llamaindex_time, "results": llamaindex_results},
        "langchain": {"time": langchain_time, "results": langchain_results},
    }


async def analyze_existing_data():
    """Analyze the structure of existing Redis vector data"""
    logger.info("\n=== Analyzing Existing Redis Data ===")
    try:
        import redis

        client = redis.Redis(host="localhost", port=6379, db=2, decode_responses=True)

        # Get sample documents
        sample_keys = list(client.scan_iter(match="llama_index/vector*", count=5))
        logger.info(f"Sample keys: {len(sample_keys)}")

        if sample_keys:
            sample_doc = client.hgetall(sample_keys[0])
            logger.info("Sample document structure:")
            for key, value in sample_doc.items():
                if key == "vector":
                    logger.info(f"  {key}: <binary vector data - {len(value)} bytes>")
                elif key == "_node_content":
                    logger.info(f"  {key}: <node metadata - {len(value)} chars>")
                else:
                    logger.info(f"  {key}: {str(value)[:100]}...")

        # Check index configuration
        try:
            index_info = client.execute_command("FT.INFO", "llama_index")
            vector_config = None
            for i in range(0, len(index_info), 2):
                if index_info[i] == "attributes":
                    attrs = index_info[i + 1]
                    for j in range(0, len(attrs), 6):
                        if j + 1 < len(attrs) and attrs[j + 1] == "vector":
                            vector_config = attrs[j : j + 6]
                            break

            if vector_config:
                logger.info(f"Vector field config: {vector_config}")

        except Exception as e:
            logger.warning(f"Could not get index info: {e}")

        return sample_doc if sample_keys else {}

    except Exception as e:
        logger.error(f"❌ Data analysis failed: {e}")
        return {}


async def main():
    """Main comparison function"""
    logger.info("Starting Redis Vector Store Comparison")

    # Test basic connectivity
    redis_ok = await test_redis_connection()
    if not redis_ok:
        logger.error("Redis connection failed - cannot proceed")
        return

    # Analyze existing data structure
    await analyze_existing_data()

    # Compare implementations
    performance = await compare_performance()

    # Generate recommendation
    logger.info("\n=== RECOMMENDATION ===")

    if (
        performance["llamaindex"]["results"] > 0
        and performance["langchain"]["results"] > 0
    ):
        logger.info("Both implementations can access data successfully")

        if performance["llamaindex"]["time"] < performance["langchain"]["time"]:
            logger.info("✅ RECOMMEND: Stick with LlamaIndex (faster performance)")
        else:
            logger.info("✅ RECOMMEND: Consider LangChain (better performance)")

    elif performance["llamaindex"]["results"] > 0:
        logger.info("✅ RECOMMEND: Fix and keep LlamaIndex (can access existing data)")

    elif performance["langchain"]["results"] > 0:
        logger.info("✅ RECOMMEND: Migrate to LangChain (working implementation)")

    else:
        logger.info("❌ Both implementations have issues - need deeper investigation")

    logger.info(f"\nPerformance summary: {performance}")


if __name__ == "__main__":
    asyncio.run(main())
