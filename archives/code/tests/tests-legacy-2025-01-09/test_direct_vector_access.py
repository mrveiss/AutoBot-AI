#!/usr/bin/env python3
"""
Test direct vector access without Redis search index
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import redis
from llama_index.vector_stores.redis import RedisVectorStore
from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.ollama import OllamaEmbedding as LlamaIndexOllamaEmbedding
from llama_index.llms.ollama import Ollama as LlamaIndexOllamaLLM
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    try:
        print("🧪 Testing direct vector store access...")

        # Configure LlamaIndex with the correct embedding model
        try:
            Settings.llm = LlamaIndexOllamaLLM(
                model="llama3.2:3b",
                request_timeout=30.0,
                base_url="http://127.0.0.1:11434",
            )
            # For now, keep using nomic-embed-text for new queries
            # We'll address dimension mismatch separately
            Settings.embed_model = LlamaIndexOllamaEmbedding(
                model_name="nomic-embed-text",
                base_url="http://127.0.0.1:11434",
                ollama_additional_kwargs={"num_ctx": 2048},
            )
            print("✅ LlamaIndex configured")
        except Exception as e:
            print(f"⚠️ LlamaIndex configuration warning: {e}")

        # Connect directly to the existing Redis vector store
        print("🔗 Connecting to Redis vector store...")

        # Create RedisVectorStore pointing to database 1 where vectors exist
        vector_store = RedisVectorStore(
            redis_url="redis://172.16.168.23:6379",
            password=None,
            redis_kwargs={"db": 1},  # Database 1 where vectors actually exist
            overwrite=False,  # Don't overwrite existing data
        )

        print("✅ Connected to Redis vector store")

        # Try to get all vectors directly
        print("📦 Checking vector store contents...")

        # Get Redis client to check data (no decode for binary data)
        redis_client = redis.Redis(host="172.16.168.23", port=6379, db=1, decode_responses=False)
        vector_keys = redis_client.keys(b"llama_index/vector_*")
        print(f"📊 Found {len(vector_keys)} vectors in database 1")

        # Check one vector to understand structure
        if vector_keys:
            sample_key = vector_keys[0]
            sample_data = redis_client.hgetall(sample_key)

            # Decode field names (but keep values as binary for vectors)
            fields = [k.decode('utf-8') if isinstance(k, bytes) else k for k in sample_data.keys()]
            print(f"📄 Sample vector fields: {fields}")

            if b'text' in sample_data:
                text_content = sample_data[b'text'].decode('utf-8', errors='ignore')
                text_preview = text_content[:100] + "..." if len(text_content) > 100 else text_content
                print(f"📝 Sample text: {text_preview}")

        # Try to create VectorStoreIndex from existing store
        print("🔄 Creating VectorStoreIndex from existing store...")
        try:
            # This should load the existing index without needing Redis search
            index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
            print("✅ VectorStoreIndex created successfully")

            # Try a simple query
            print("🔍 Testing query on existing vectors...")
            query_engine = index.as_query_engine(similarity_top_k=3)

            # Test query for AutoBot documentation
            response = await asyncio.to_thread(
                query_engine.query,
                "What is AutoBot? Tell me about AutoBot documentation and features."
            )

            print(f"✅ Query successful!")
            print(f"📄 Response: {str(response)[:200]}...")

            # Check source documents
            if hasattr(response, 'source_nodes') and response.source_nodes:
                print(f"📚 Found {len(response.source_nodes)} source documents")
                for i, node in enumerate(response.source_nodes[:2]):
                    source = node.metadata.get('source', 'Unknown')
                    print(f"  📖 Source {i+1}: {source}")

        except Exception as e:
            print(f"❌ VectorStoreIndex creation failed: {e}")
            import traceback
            traceback.print_exc()

        print("✅ Direct vector access test completed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())