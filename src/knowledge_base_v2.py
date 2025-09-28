"""
Knowledge Base V2 - Async-First Implementation

This is an improved version of the knowledge base that supports proper async initialization
and resolves race conditions through a clean async factory pattern.

Key Improvements:
- Async initialization with proper await patterns
- No async tasks created in __init__
- Clear separation of sync and async operations
- Unified configuration integration
- Better error handling and logging
- Initialization state tracking
"""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator

import aiofiles
import aioredis
import redis
from langchain_text_splitters import RecursiveCharacterTextSplitter
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.storage_context import StorageContext
from llama_index.embeddings.ollama import OllamaEmbedding as LlamaIndexOllamaEmbedding
from llama_index.llms.ollama import Ollama as LlamaIndexOllamaLLM
from llama_index.vector_stores.redis import RedisVectorStore
from llama_index.vector_stores.redis.schema import RedisVectorStoreSchema
from pypdf import PdfReader

from src.circuit_breaker import circuit_breaker_async
from src.unified_config import config

logger = logging.getLogger(__name__)


class KnowledgeBaseV2:
    """Async-first knowledge base implementation with proper initialization patterns"""

    def __init__(self):
        """Initialize instance variables only - no async operations"""
        self.initialized = False
        self.initialization_lock = asyncio.Lock()

        # Configuration from unified config
        self.redis_host = config.get_host('redis')
        self.redis_port = config.get_port('redis')
        self.redis_password = config.get('redis.password')
        self.redis_db = config.get('redis.databases.knowledge', 1)
        self.redis_index_name = config.get('redis.indexes.knowledge_base', 'llama_index')

        # Connection clients (initialized in async method)
        self.redis_client: Optional[redis.Redis] = None
        self.aioredis_client: Optional[aioredis.Redis] = None

        # Vector store components (initialized in async method)
        self.vector_store: Optional[RedisVectorStore] = None
        self.vector_index: Optional[VectorStoreIndex] = None

        # Configuration flags
        self.llama_index_configured = False

        logger.info("KnowledgeBaseV2 instance created (not yet initialized)")

    async def initialize(self) -> bool:
        """Async initialization method - must be called after construction"""
        if self.initialized:
            return True

        async with self.initialization_lock:
            if self.initialized:  # Double-check after acquiring lock
                return True

            try:
                logger.info("Starting async knowledge base initialization...")

                # Step 1: Initialize Redis connections first
                await self._init_redis_connections()

                # Step 2: Configure LlamaIndex (needs Redis for dimension detection)
                await self._configure_llama_index()

                # Step 3: Initialize vector store
                await self._init_vector_store()

                self.initialized = True
                logger.info("Knowledge base initialization completed successfully")
                return True

            except Exception as e:
                logger.error(f"Knowledge base initialization failed: {e}")
                await self._cleanup_on_failure()
                return False

    async def _configure_llama_index(self):
        """Configure LlamaIndex with Ollama models"""
        try:
            # Manually construct Ollama URL due to config interpolation issue
            ollama_host = config.get('infrastructure.hosts.ollama', '127.0.0.1')
            ollama_port = config.get('infrastructure.ports.ollama', '11434')
            ollama_url = f"http://{ollama_host}:{ollama_port}"
            llm_timeout = config.get_timeout('llm', 'default', 30.0)

            Settings.llm = LlamaIndexOllamaLLM(
                model="llama3.2:3b",
                request_timeout=llm_timeout,
                base_url=ollama_url,
            )

            # Check what embedding model was used for existing data
            detected_dim = await self._detect_embedding_dimensions()
            stored_model = await self._detect_stored_embedding_model()

            if stored_model:
                embed_model_name = stored_model
                logger.info(f"Using stored embedding model: {embed_model_name} (dimensions: {detected_dim})")
            elif detected_dim == 768:
                embed_model_name = "nomic-embed-text"
                logger.info("Using nomic-embed-text for 768-dimensional vectors")
            else:
                embed_model_name = "all-MiniLM-L6-v2"
                logger.info("Using all-MiniLM-L6-v2 for 384-dimensional vectors")

            Settings.embed_model = LlamaIndexOllamaEmbedding(
                model_name=embed_model_name,
                base_url=ollama_url,
                ollama_additional_kwargs={"num_ctx": 2048},
            )

            self.llama_index_configured = True
            logger.info(f"LlamaIndex configured with Ollama at {ollama_url}")

        except Exception as e:
            logger.warning(f"Could not configure LlamaIndex with Ollama: {e}")
            self.llama_index_configured = False

    async def _init_redis_connections(self):
        """Initialize Redis connections using standardized pool manager"""
        try:
            from src.redis_pool_manager import get_redis_sync, get_redis_async

            # Get sync Redis client for binary operations (needed for vector store)
            # Note: We need a special non-decode client for binary vector operations
            self.redis_client = get_redis_sync('knowledge')

            # Override decode_responses for binary operations if needed
            if hasattr(self.redis_client.connection_pool, 'connection_kwargs'):
                # Create a separate pool for binary operations
                import redis
                redis_config = config.get_redis_config()
                self.redis_client = redis.Redis(
                    host=redis_config['host'],
                    port=redis_config['port'],
                    db=self.redis_db,
                    password=redis_config.get('password'),
                    decode_responses=False,  # Needed for binary vector operations
                    socket_timeout=redis_config['socket_timeout'],
                    socket_connect_timeout=redis_config['socket_connect_timeout'],
                    retry_on_timeout=redis_config['retry_on_timeout']
                )

            # Test sync connection
            await asyncio.to_thread(self.redis_client.ping)
            logger.info(f"Knowledge Base Redis sync client connected (database {self.redis_db})")

            # Get async Redis client using pool manager
            self.aioredis_client = await get_redis_async('knowledge')

            # Test async connection
            await self.aioredis_client.ping()
            logger.info("Knowledge Base async Redis client connected successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Redis connections: {e}")
            raise

    async def _init_vector_store(self):
        """Initialize LlamaIndex vector store with Redis backend"""
        if not self.redis_client:
            logger.warning("Redis client not available, skipping vector store initialization")
            return

        try:
            # Detect embedding dimensions from existing index
            embedding_dim = await self._detect_embedding_dimensions()

            # Create schema
            schema = RedisVectorStoreSchema(
                index_name=self.redis_index_name,
                prefix="doc",
                overwrite=True,  # Allow overwriting to fix dimension mismatch
            )

            logger.info(f"Created Redis schema with {embedding_dim} vector dimensions")

            # Create vector store
            redis_url = f"redis://{self.redis_host}:{self.redis_port}"
            self.vector_store = RedisVectorStore(
                schema=schema,
                redis_url=redis_url,
                password=self.redis_password,
                redis_kwargs={"db": self.redis_db},
            )

            logger.info(f"LlamaIndex RedisVectorStore initialized with index: {self.redis_index_name}")

        except ImportError as e:
            logger.warning(f"Could not import RedisVectorStoreSchema: {e}. Using fallback configuration.")
            self.vector_store = None
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            self.vector_store = None

    async def _detect_embedding_dimensions(self) -> int:
        """Detect embedding dimensions from existing index"""
        default_dim = 768  # Default for nomic-embed-text (match existing data)

        try:
            # Check if index exists and get its dimensions
            index_info = await asyncio.to_thread(
                self.redis_client.execute_command, "FT.INFO", self.redis_index_name
            )

            # Parse dimension from index info
            for i, item in enumerate(index_info):
                if isinstance(item, bytes):
                    item = item.decode()
                if item == "dim" and i + 1 < len(index_info):
                    detected_dim = int(index_info[i + 1])
                    logger.info(f"Detected existing index dimension: {detected_dim}")
                    return detected_dim

        except Exception as e:
            logger.info(f"Could not detect embedding dimension, using default {default_dim}: {e}")

        return default_dim

    async def _cleanup_on_failure(self):
        """Cleanup resources on initialization failure"""
        try:
            if self.aioredis_client:
                await self.aioredis_client.close()
                self.aioredis_client = None

            if self.redis_client:
                await asyncio.to_thread(self.redis_client.close)
                self.redis_client = None

            self.vector_store = None
            self.vector_index = None

            logger.info("Cleanup completed after initialization failure")

        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

    # Public API methods

    def ensure_initialized(self):
        """Ensure the knowledge base is initialized (raises exception if not)"""
        if not self.initialized:
            raise RuntimeError(
                "Knowledge base not initialized. Use 'await knowledge_base.initialize()' first, "
                "or get instance via get_knowledge_base() factory function."
            )

    async def ping_redis(self) -> str:
        """Test Redis connection"""
        self.ensure_initialized()
        try:
            if self.aioredis_client:
                pong = await self.aioredis_client.ping()
                return "healthy" if pong else "unhealthy"
            else:
                return "no_client"
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return "error"

    def get_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics"""
        self.ensure_initialized()

        try:
            if not self.redis_client:
                return {"error": "Redis client not available"}

            # Get vector count
            vector_keys = self._scan_redis_keys("doc:*")
            vector_count = len(vector_keys)

            # Get index info if available
            index_info = {}
            try:
                info = self.redis_client.execute_command("FT.INFO", self.redis_index_name)
                # Parse basic info
                if info:
                    for i in range(0, len(info) - 1, 2):
                        key = info[i].decode() if isinstance(info[i], bytes) else str(info[i])
                        value = info[i + 1]
                        if isinstance(value, bytes):
                            value = value.decode()
                        index_info[key] = value
            except:
                pass

            return {
                "total_documents": vector_count,
                "total_chunks": vector_count,  # In Redis, each document is typically one chunk
                "total_facts": self._count_facts(),
                "redis_db": self.redis_db,
                "index_name": self.redis_index_name,
                "index_info": index_info,
                "initialized": self.initialized,
                "llama_index_configured": self.llama_index_configured
            }

        except Exception as e:
            logger.error(f"Error getting knowledge base stats: {e}")
            return {"error": str(e)}

    def _scan_redis_keys(self, pattern: str) -> List[str]:
        """Scan Redis keys with pattern using sync client"""
        if not self.redis_client:
            return []

        try:
            keys = []
            for key in self.redis_client.scan_iter(match=pattern):
                if isinstance(key, bytes):
                    keys.append(key.decode('utf-8'))
                else:
                    keys.append(str(key))
            return keys
        except Exception as e:
            logger.error(f"Error scanning Redis keys: {e}")
            return []

    def _count_facts(self) -> int:
        """Count stored facts in Redis"""
        try:
            fact_keys = self._scan_redis_keys("fact:*")
            return len(fact_keys)
        except Exception as e:
            logger.error(f"Error counting facts: {e}")
            return 0

    async def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search the knowledge base"""
        self.ensure_initialized()

        if not self.vector_store:
            logger.warning("Vector store not available for search")
            return []

        try:
            # Use retriever for search to avoid LLM timeout issues
            if not self.vector_index:
                # Create index from vector store
                storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
                self.vector_index = VectorStoreIndex.from_vector_store(
                    vector_store=self.vector_store,
                    storage_context=storage_context
                )

            # Get retriever and search
            retriever = self.vector_index.as_retriever(similarity_top_k=top_k)
            nodes = await asyncio.to_thread(retriever.retrieve, query)

            # Format results
            results = []
            for node in nodes:
                result = {
                    "content": node.text,
                    "score": getattr(node, 'score', 0.0),
                    "metadata": node.metadata or {},
                    "node_id": node.node_id
                }
                results.append(result)

            logger.info(f"Knowledge base search returned {len(results)} results for query: {query[:50]}...")
            return results

        except Exception as e:
            logger.error(f"Knowledge base search failed: {e}")
            return []

    async def close(self):
        """Close all connections and cleanup resources"""
        try:
            if self.aioredis_client:
                await self.aioredis_client.close()

            if self.redis_client:
                await asyncio.to_thread(self.redis_client.close)

            self.initialized = False
            logger.info("Knowledge base connections closed")

        except Exception as e:
            logger.warning(f"Error during knowledge base cleanup: {e}")

    def __del__(self):
        """Destructor - ensure cleanup"""
        if self.initialized:
            logger.warning("KnowledgeBase instance deleted without proper cleanup - use await kb.close()")