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
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

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
from pypdf import PdfReader
from redisvl.schema import IndexSchema

from src.circuit_breaker import circuit_breaker_async
from src.constants.network_constants import NetworkConstants
from src.unified_config import config

logger = logging.getLogger(__name__)


class KnowledgeBaseV2:
    """Async-first knowledge base implementation with proper initialization patterns"""

    def __init__(self):
        """Initialize instance variables only - no async operations"""
        self.initialized = False
        self.initialization_lock = asyncio.Lock()

        # Configuration from unified config
        self.redis_host = config.get_host("redis")
        self.redis_port = config.get_port("redis")
        self.redis_password = config.get("redis.password")
        self.redis_db = config.get("redis.databases.knowledge", 1)
        self.redis_index_name = config.get(
            "redis.indexes.knowledge_base", "llama_index"
        )

        # Connection clients (initialized in async method)
        self.redis_client: Optional[redis.Redis] = None
        self.aioredis_client: Optional[aioredis.Redis] = None

        # Vector store components (initialized in async method)
        self.vector_store: Optional[RedisVectorStore] = None
        self.vector_index: Optional[VectorStoreIndex] = None

        # Configuration flags
        self.llama_index_configured = False
        self.embedding_model_name: Optional[str] = None  # Store actual model being used
        self.embedding_dimensions: Optional[int] = None  # Store vector dimensions

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
            ollama_host = config.get("infrastructure.hosts.ollama", "127.0.0.1")
            ollama_port = config.get(
                "infrastructure.ports.ollama", str(NetworkConstants.OLLAMA_PORT)
            )
            ollama_url = f"http://{ollama_host}:{ollama_port}"
            llm_timeout = config.get_timeout("llm", "default", 30.0)

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
                logger.info(
                    f"Using stored embedding model: {embed_model_name} (dimensions: {detected_dim})"
                )
            elif detected_dim == 768:
                embed_model_name = "nomic-embed-text"
                logger.info("Using nomic-embed-text for 768-dimensional vectors")
            else:
                embed_model_name = "all-MiniLM-L6-v2"
                logger.info("Using all-MiniLM-L6-v2 for 384-dimensional vectors")

            # Store model configuration in instance variables
            self.embedding_model_name = embed_model_name
            self.embedding_dimensions = detected_dim

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
            from src.redis_pool_manager import get_redis_async, get_redis_sync

            # Get sync Redis client for binary operations (needed for vector store)
            # Note: We need a special non-decode client for binary vector operations
            self.redis_client = get_redis_sync("knowledge")

            # Override decode_responses for binary operations if needed
            if hasattr(self.redis_client.connection_pool, "connection_kwargs"):
                # Create a separate pool for binary operations
                import redis

                redis_config = config.get_redis_config()
                self.redis_client = redis.Redis(
                    host=redis_config["host"],
                    port=redis_config["port"],
                    db=self.redis_db,
                    password=redis_config.get("password"),
                    decode_responses=False,  # Needed for binary vector operations
                    socket_timeout=redis_config["socket_timeout"],
                    socket_connect_timeout=redis_config["socket_connect_timeout"],
                    retry_on_timeout=redis_config["retry_on_timeout"],
                )

            # Test sync connection
            await asyncio.to_thread(self.redis_client.ping)
            logger.info(
                f"Knowledge Base Redis sync client connected (database {self.redis_db})"
            )

            # Get async Redis client using pool manager
            self.aioredis_client = await get_redis_async("knowledge")

            # Test async connection
            await self.aioredis_client.ping()
            logger.info("Knowledge Base async Redis client connected successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Redis connections: {e}")
            raise

    async def _init_vector_store(self):
        """Initialize LlamaIndex vector store with Redis backend - FIXED for dimension mismatch"""
        if not self.redis_client:
            logger.warning(
                "Redis client not available, skipping vector store initialization"
            )
            return

        try:
            # Detect embedding dimensions from existing index or use default
            embedding_dim = await self._detect_embedding_dimensions()
            logger.info(f"Using {embedding_dim} dimensions for vector embeddings")

            # CRITICAL FIX: Use IndexSchema.from_dict() with explicit dimension configuration
            # This ensures the Redis vector index is created with the correct dimensions
            custom_schema = IndexSchema.from_dict(
                {
                    "index": {"name": self.redis_index_name, "prefix": "doc"},
                    "fields": [
                        # Required fields for LlamaIndex
                        {"type": "tag", "name": "id"},
                        {"type": "tag", "name": "doc_id"},
                        {"type": "text", "name": "text"},
                        # Vector field with EXPLICIT dimension configuration
                        {
                            "type": "vector",
                            "name": "vector",
                            "attrs": {
                                "dims": embedding_dim,  # CRITICAL: Match embedding model output
                                "algorithm": "hnsw",
                                "distance_metric": "cosine",
                            },
                        },
                    ],
                }
            )

            logger.info(
                f"Created Redis schema with explicit {embedding_dim} vector dimensions"
            )

            # Create vector store with properly configured schema
            redis_url = f"redis://{self.redis_host}:{self.redis_port}"

            self.vector_store = RedisVectorStore(
                schema=custom_schema,
                redis_url=redis_url,
                password=self.redis_password,
                redis_kwargs={"db": self.redis_db},
            )

            logger.info(
                f"LlamaIndex RedisVectorStore initialized with index: {self.redis_index_name}"
            )
            logger.info(
                f"✅ Vector dimension mismatch FIXED - using {embedding_dim} dimensions"
            )

            # CRITICAL FIX: Create vector index immediately during initialization
            # This ensures the index exists even before any facts are stored
            await self._create_initial_vector_index()

        except ImportError as e:
            logger.error(f"Could not import required modules: {e}")
            logger.error("Please ensure redisvl is installed: pip install redisvl")
            self.vector_store = None
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            import traceback

            logger.error(traceback.format_exc())
            self.vector_store = None

    async def _detect_embedding_dimensions(self) -> int:
        """Detect embedding dimensions from existing index or return default"""
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

                    # If there's a mismatch, we need to recreate the index
                    if detected_dim != default_dim:
                        logger.warning(
                            f"Index dimension mismatch: existing={detected_dim}, expected={default_dim}"
                        )
                        logger.info("Will recreate index with correct dimensions...")

                        # Drop the existing index
                        try:
                            await asyncio.to_thread(
                                self.redis_client.execute_command,
                                "FT.DROPINDEX",
                                self.redis_index_name,
                            )
                            logger.info(
                                f"Dropped existing index {self.redis_index_name}"
                            )
                        except Exception as drop_error:
                            logger.warning(f"Could not drop index: {drop_error}")

                    return default_dim  # Always return the expected dimension

        except Exception as e:
            logger.info(
                f"No existing index found or could not detect dimension, using default {default_dim}: {e}"
            )

        return default_dim

    async def _create_initial_vector_index(self):
        """Create the vector index immediately during initialization (CRITICAL FIX)

        This ensures the index exists before any facts are stored, allowing all facts
        to be properly indexed for vector search.
        """
        try:
            if not self.vector_store:
                logger.warning(
                    "Cannot create vector index - vector store not initialized"
                )
                return

            logger.info("Creating initial vector index...")

            # Create empty index with storage context
            storage_context = StorageContext.from_defaults(
                vector_store=self.vector_store
            )

            # Create index with empty document list (index will exist for future inserts)
            self.vector_index = await asyncio.to_thread(
                VectorStoreIndex.from_documents,
                [],  # Empty list - just creates the index structure
                storage_context=storage_context,
            )

            logger.info("✅ Vector index created successfully - ready to index facts")

            # Now re-index any existing facts that don't have vectors
            await self._reindex_existing_facts()

        except Exception as e:
            logger.error(f"Failed to create initial vector index: {e}")
            import traceback

            logger.error(traceback.format_exc())
            # Don't fail initialization - just log the error
            self.vector_index = None

    async def _reindex_existing_facts(self):
        """Re-index any existing facts that don't have corresponding vectors

        This handles the scenario where facts were stored before the vector store
        was properly initialized, ensuring all content is searchable.
        """
        try:
            if not self.aioredis_client or not self.vector_index:
                logger.debug("Skipping re-indexing - prerequisites not met")
                return

            # Get all fact keys
            fact_keys = []
            async for key in self.aioredis_client.scan_iter(match="fact:*"):
                fact_keys.append(key)

            if not fact_keys:
                logger.info("No existing facts to re-index")
                return

            logger.info(
                f"Found {len(fact_keys)} existing facts - checking which need indexing..."
            )

            # Get all existing vector doc keys to see what's already indexed
            # LlamaIndex uses llama_index/vector_* pattern for vector documents
            vector_doc_keys = set()
            async for key in self.aioredis_client.scan_iter(
                match="llama_index/vector_*"
            ):
                vector_doc_keys.add(key)

            logger.info(f"Found {len(vector_doc_keys)} existing vector documents")

            # Re-index facts that don't have vectors
            reindexed_count = 0
            skipped_count = 0

            for fact_key in fact_keys:
                try:
                    # Extract fact_id from key (format: "fact:uuid")
                    fact_id = (
                        fact_key.split(b":")[1].decode()
                        if isinstance(fact_key, bytes)
                        else fact_key.split(":")[1]
                    )

                    # Check if this fact already has a vector document
                    # LlamaIndex creates keys like "llama_index/vector_{doc_id}"
                    # Simple check: if any vector key contains this fact_id, skip it
                    already_indexed = any(
                        (
                            fact_id.encode() in doc_key
                            if isinstance(doc_key, bytes)
                            else fact_id in doc_key
                        )
                        for doc_key in vector_doc_keys
                    )

                    if already_indexed:
                        skipped_count += 1
                        continue

                    # Get fact data
                    fact_data = await self.aioredis_client.hgetall(fact_key)
                    if not fact_data:
                        continue

                    content = fact_data.get(
                        b"content" if isinstance(fact_key, bytes) else "content"
                    )
                    metadata_str = fact_data.get(
                        b"metadata" if isinstance(fact_key, bytes) else "metadata"
                    )

                    if content:
                        if isinstance(content, bytes):
                            content = content.decode()

                        # Parse metadata
                        metadata = {}
                        if metadata_str:
                            try:
                                if isinstance(metadata_str, bytes):
                                    metadata_str = metadata_str.decode()
                                metadata = json.loads(metadata_str)
                            except:
                                pass

                        # Create document and index it
                        document = Document(
                            text=content, metadata=metadata, doc_id=fact_id
                        )

                        # Insert into vector index
                        await asyncio.to_thread(self.vector_index.insert, document)
                        reindexed_count += 1

                        if reindexed_count % 10 == 0:
                            logger.info(
                                f"Re-indexed {reindexed_count}/{len(fact_keys)} facts..."
                            )

                except Exception as fact_error:
                    logger.warning(f"Failed to re-index fact {fact_key}: {fact_error}")
                    continue

            logger.info(
                f"✅ Re-indexing complete: {reindexed_count} facts indexed, {skipped_count} already had vectors"
            )

        except Exception as e:
            logger.error(f"Failed to re-index existing facts: {e}")
            import traceback

            logger.error(traceback.format_exc())
            # Don't fail initialization - just log the error

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

    # REMOVED: Old synchronous get_stats() method - replaced by async version below

    def _scan_redis_keys(self, pattern: str) -> List[str]:
        """Scan Redis keys with pattern using sync client"""
        if not self.redis_client:
            return []

        try:
            keys = []
            for key in self.redis_client.scan_iter(match=pattern):
                if isinstance(key, bytes):
                    keys.append(key.decode("utf-8"))
                else:
                    keys.append(str(key))
            return keys
        except Exception as e:
            logger.error(f"Error scanning Redis keys: {e}")
            return []

    async def _scan_redis_keys_async(self, pattern: str) -> List[str]:
        """Scan Redis keys with pattern using async client"""
        if not self.aioredis_client:
            logger.warning("Async Redis client not available for key scanning")
            return []

        try:
            keys = []
            async for key in self.aioredis_client.scan_iter(match=pattern):
                if isinstance(key, bytes):
                    keys.append(key.decode("utf-8"))
                else:
                    keys.append(str(key))

            logger.debug(f"Scanned {len(keys)} keys matching pattern '{pattern}'")
            return keys

        except redis.RedisError as e:
            logger.error(f"Redis error scanning keys with pattern '{pattern}': {e}")
            return []
        except Exception as e:
            logger.exception(f"Unexpected error scanning Redis keys: {e}")
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
                storage_context = StorageContext.from_defaults(
                    vector_store=self.vector_store
                )
                self.vector_index = VectorStoreIndex.from_vector_store(
                    vector_store=self.vector_store, storage_context=storage_context
                )

            # Get retriever and search
            retriever = self.vector_index.as_retriever(similarity_top_k=top_k)
            nodes = await asyncio.to_thread(retriever.retrieve, query)

            # Format results
            results = []
            for node in nodes:
                result = {
                    "content": node.text,
                    "score": getattr(node, "score", 0.0),
                    "metadata": node.metadata or {},
                    "node_id": node.node_id,
                }
                results.append(result)

            logger.info(
                f"Knowledge base search returned {len(results)} results for query: {query[:50]}..."
            )
            return results

        except Exception as e:
            logger.error(f"Knowledge base search failed: {e}")
            return []

    async def store_fact(
        self, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Store a fact in the knowledge base with vector indexing"""
        self.ensure_initialized()

        try:
            if not content.strip():
                return {
                    "status": "error",
                    "message": "Content cannot be empty",
                    "fact_id": None,
                }

            # Generate unique fact ID
            fact_id = str(uuid.uuid4())

            # Prepare metadata
            fact_metadata = metadata or {}
            fact_metadata.update(
                {
                    "fact_id": fact_id,
                    "stored_at": datetime.now().isoformat(),
                    "content_length": len(content),
                    "content_type": "fact",
                }
            )

            # Store as traditional fact in Redis
            if self.aioredis_client:
                fact_key = f"fact:{fact_id}"
                fact_data = {
                    "content": content,
                    "metadata": json.dumps(fact_metadata),
                    "created_at": datetime.now().isoformat(),
                }
                await self.aioredis_client.hset(fact_key, mapping=fact_data)
                logger.debug(f"Stored fact {fact_id} in Redis")

            # Store in vector index for semantic search - CRITICAL FOR SEARCHABILITY
            vector_indexed = False
            if self.vector_store:
                try:
                    # Create LlamaIndex document
                    document = Document(
                        text=content, metadata=fact_metadata, doc_id=fact_id
                    )

                    # Create or get vector index with proper async handling
                    if not self.vector_index:
                        storage_context = StorageContext.from_defaults(
                            vector_store=self.vector_store
                        )
                        try:
                            # FIXED: Wrap synchronous operations in asyncio.to_thread()
                            self.vector_index = await asyncio.to_thread(
                                VectorStoreIndex.from_documents,
                                [document],
                                storage_context,
                            )
                            vector_indexed = True
                            logger.info(
                                f"Created vector index and stored fact {fact_id}"
                            )
                        except Exception as index_error:
                            if "dimension" in str(index_error).lower():
                                logger.error(
                                    f"Vector index creation failed due to dimension mismatch: {index_error}"
                                )
                                # This should NOT happen with the new schema fix
                                logger.error(
                                    "CRITICAL: Dimension mismatch still occurring after schema fix!"
                                )
                                raise index_error
                            else:
                                raise index_error
                    else:
                        # FIXED: Wrap insert() in asyncio.to_thread() for proper async handling
                        await asyncio.to_thread(self.vector_index.insert, document)
                        vector_indexed = True
                        logger.info(
                            f"Inserted fact {fact_id} into existing vector index"
                        )

                except Exception as vector_error:
                    error_msg = str(vector_error)
                    logger.error(
                        f"CRITICAL: Failed to store fact {fact_id} in vector index: {error_msg}"
                    )
                    # Vector indexing failed - fact is in Redis but NOT searchable
                    return {
                        "status": "partial_success",
                        "message": f"Fact stored in Redis but NOT indexed for search: {error_msg}",
                        "fact_id": fact_id,
                        "vector_indexed": False,
                        "searchable": False,
                    }

            return {
                "status": "success",
                "message": (
                    "Fact stored successfully and indexed for search"
                    if vector_indexed
                    else "Fact stored in Redis only (vector store unavailable)"
                ),
                "fact_id": fact_id,
                "vector_indexed": vector_indexed,
                "searchable": vector_indexed,
            }

        except Exception as e:
            logger.error(f"Error storing fact: {e}")
            return {
                "status": "error",
                "message": f"Failed to store fact: {str(e)}",
                "fact_id": None,
            }

    async def vectorize_existing_fact(
        self, fact_id: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Vectorize an existing fact without creating a duplicate.

        Args:
            fact_id: Existing fact ID to vectorize
            content: Fact content to embed
            metadata: Optional metadata for the fact

        Returns:
            Dict with status, vector_indexed, and message
        """
        self.ensure_initialized()

        try:
            if not self.vector_store or not self.llama_index_configured:
                return {
                    "status": "error",
                    "message": "Vector store not initialized",
                    "fact_id": fact_id,
                    "vector_indexed": False,
                }

            # Prepare metadata
            fact_metadata = metadata or {}
            if "fact_id" not in fact_metadata:
                fact_metadata["fact_id"] = fact_id

            # Create LlamaIndex document with existing fact_id
            document = Document(
                text=content,
                metadata=fact_metadata,
                doc_id=fact_id,  # Use existing ID to prevent duplication
            )

            # Add to vector index
            if not self.vector_index:
                # Create initial index
                storage_context = StorageContext.from_defaults(
                    vector_store=self.vector_store
                )
                self.vector_index = await asyncio.to_thread(
                    VectorStoreIndex.from_documents, [document], storage_context
                )
                logger.info(f"Created vector index and vectorized fact {fact_id}")
            else:
                # Insert into existing index
                await asyncio.to_thread(self.vector_index.insert, document)
                logger.debug(f"Vectorized existing fact {fact_id}")

            return {
                "status": "success",
                "message": "Fact vectorized successfully",
                "fact_id": fact_id,
                "vector_indexed": True,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to vectorize fact {fact_id}: {error_msg}")
            return {
                "status": "error",
                "message": f"Vectorization failed: {error_msg}",
                "fact_id": fact_id,
                "vector_indexed": False,
            }

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive knowledge base statistics (async version)"""
        self.ensure_initialized()

        print("🔍 [DEBUG] ASYNC get_stats() CALLED!", flush=True)
        logger.info("=== ASYNC get_stats() called with caching ===")
        try:
            stats = {
                "total_documents": 0,
                "total_chunks": 0,
                "total_facts": 0,
                "total_vectors": 0,
                "categories": [],
                "db_size": 0,
                "status": "online",
                "last_updated": datetime.now().isoformat(),
                "redis_db": self.redis_db,
                "index_name": self.redis_index_name,
                "initialized": self.initialized,
                "llama_index_configured": self.llama_index_configured,
                "embedding_model": self.embedding_model_name,
                "embedding_dimensions": self.embedding_dimensions,
            }

            if self.aioredis_client:
                # PERFORMANCE FIX: Use cached counts instead of scanning all keys
                # Scanning through 296k+ Redis keys to count 1,358 facts takes minutes
                # Use pre-computed counts stored in Redis for instant lookups

                try:
                    # Try to get cached counts first (instant lookup)
                    cached_fact_count = await self.aioredis_client.get(
                        "kb:stats:fact_count"
                    )
                    cached_vector_count = await self.aioredis_client.get(
                        "kb:stats:vector_count"
                    )

                    if (
                        cached_fact_count is not None
                        and cached_vector_count is not None
                    ):
                        # Use cached values
                        fact_count = int(cached_fact_count)
                        vector_count = int(cached_vector_count)
                        logger.debug(
                            f"Using cached counts: {fact_count} facts, {vector_count} vectors"
                        )
                    else:
                        # Cache miss - use fast count via redis-cli
                        # This is still much faster than scan_iter()
                        import subprocess

                        # Count facts quickly using redis-cli
                        fact_result = subprocess.run(
                            [
                                "redis-cli",
                                "-h",
                                self.redis_host,
                                "-p",
                                str(self.redis_port),
                                "--scan",
                                "--pattern",
                                "fact:*",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        fact_count = (
                            len(fact_result.stdout.strip().split("\n"))
                            if fact_result.stdout.strip()
                            else 0
                        )

                        # Count vectors quickly using redis-cli
                        vector_result = subprocess.run(
                            [
                                "redis-cli",
                                "-h",
                                self.redis_host,
                                "-p",
                                str(self.redis_port),
                                "--scan",
                                "--pattern",
                                "llama_index/vector_*",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=15,
                        )
                        vector_count = (
                            len(vector_result.stdout.strip().split("\n"))
                            if vector_result.stdout.strip()
                            else 0
                        )

                        # Cache the counts for 60 seconds
                        await self.aioredis_client.set(
                            "kb:stats:fact_count", fact_count, ex=60
                        )
                        await self.aioredis_client.set(
                            "kb:stats:vector_count", vector_count, ex=60
                        )
                        logger.info(
                            f"Counted and cached: {fact_count} facts, {vector_count} vectors"
                        )

                except subprocess.TimeoutExpired:
                    logger.warning("Redis count timed out, using fallback")
                    fact_count = 0
                    vector_count = 0
                except Exception as count_error:
                    logger.warning(
                        f"Error counting keys, using fallback: {count_error}"
                    )
                    fact_count = 0
                    vector_count = 0

                stats["total_facts"] = fact_count
                stats["total_documents"] = vector_count
                stats["total_vectors"] = vector_count
                stats["total_chunks"] = vector_count

                # Sample a few facts for category extraction (limit to 10 for speed)
                fact_keys_sample = []
                try:
                    count = 0
                    async for key in self.aioredis_client.scan_iter(
                        match="fact:*", count=10
                    ):
                        fact_keys_sample.append(key)
                        count += 1
                        if count >= 10:  # Only sample 10 facts maximum
                            break
                except Exception as sample_error:
                    logger.warning(f"Error sampling facts: {sample_error}")

                # Get database size
                try:
                    info = await self.aioredis_client.info("memory")
                    stats["db_size"] = info.get("used_memory", 0)
                except Exception:
                    pass

                # Extract categories from sampled facts
                categories = set()
                try:
                    for key in fact_keys_sample:
                        fact_data = await self.aioredis_client.hget(key, "metadata")
                        if fact_data:
                            try:
                                metadata = json.loads(fact_data)
                                if "category" in metadata:
                                    categories.add(metadata["category"])
                            except (json.JSONDecodeError, TypeError):
                                continue

                    stats["categories"] = list(categories)
                except Exception as e:
                    logger.warning(f"Could not extract categories: {e}")
                    stats["categories"] = ["general"]

            # Get index information if available
            if self.redis_client:
                try:
                    index_info = await asyncio.to_thread(
                        self.redis_client.execute_command,
                        "FT.INFO",
                        self.redis_index_name,
                    )
                    if index_info:
                        stats["index_available"] = True
                        # Parse index info for additional stats
                        for i in range(0, len(index_info) - 1, 2):
                            key = (
                                index_info[i].decode()
                                if isinstance(index_info[i], bytes)
                                else str(index_info[i])
                            )
                            if key == "num_docs":
                                stats["indexed_documents"] = int(index_info[i + 1])
                except Exception:
                    stats["index_available"] = False

            return stats

        except Exception as e:
            logger.error(f"Error getting knowledge base stats: {e}")
            return {
                "total_documents": 0,
                "total_chunks": 0,
                "total_facts": 0,
                "total_vectors": 0,
                "categories": [],
                "db_size": 0,
                "status": "error",
                "error": str(e),
                "last_updated": datetime.now().isoformat(),
            }

    async def _detect_stored_embedding_model(self) -> Optional[str]:
        """Detect which embedding model was used for existing data"""
        try:
            if self.aioredis_client:
                # Look for model metadata in existing facts
                async for key in self.aioredis_client.scan_iter(
                    match="fact:*", count=10
                ):
                    metadata_json = await self.aioredis_client.hget(key, "metadata")
                    if metadata_json:
                        try:
                            metadata = json.loads(metadata_json)
                            if "embedding_model" in metadata:
                                return metadata["embedding_model"]
                        except (json.JSONDecodeError, TypeError):
                            continue
        except Exception as e:
            logger.debug(f"Could not detect stored embedding model: {e}")

        return None

    async def get_all_facts(
        self,
        limit: Optional[int] = None,
        offset: int = 0,
        collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve facts from Redis with optional pagination and filtering.

        Args:
            limit: Maximum number of facts to retrieve (None = all)
            offset: Number of facts to skip
            collection: Filter by collection name (None = all collections)

        Returns:
            List of fact dictionaries with content and metadata
        """
        self.ensure_initialized()

        try:
            # Get all fact keys using async scanner
            fact_keys = await self._scan_redis_keys_async("fact:*")

            if not fact_keys:
                logger.debug("No facts found in Redis")
                return []

            # Apply pagination
            total_facts = len(fact_keys)
            if offset > 0:
                fact_keys = fact_keys[offset:]
            if limit:
                fact_keys = fact_keys[:limit]

            logger.debug(
                f"Retrieving {len(fact_keys)} facts (total={total_facts}, offset={offset}, limit={limit})"
            )

            if not fact_keys:
                return []

            # Batch retrieve all facts using pipeline
            facts = []
            async with self.aioredis_client.pipeline() as pipe:
                for fact_key in fact_keys:
                    pipe.hgetall(fact_key)

                # Execute all commands in single network roundtrip
                results = await pipe.execute()

            # Process results
            for fact_key, fact_data in zip(fact_keys, results):
                if not fact_data:
                    logger.debug(f"Empty fact data for key {fact_key}")
                    continue

                try:
                    # Parse metadata
                    metadata_raw = fact_data.get(b"metadata", b"{}")
                    try:
                        metadata = json.loads(
                            metadata_raw.decode("utf-8")
                            if isinstance(metadata_raw, bytes)
                            else metadata_raw
                        )
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        logger.warning(f"Invalid metadata in {fact_key}: {e}")
                        metadata = {}

                    # Apply collection filter
                    if collection and collection != "all":
                        fact_collection = metadata.get("collection", "")
                        if fact_collection != collection:
                            continue  # Skip facts not in requested collection

                    # Parse content
                    content_raw = fact_data.get(b"content", b"")
                    content = (
                        content_raw.decode("utf-8")
                        if isinstance(content_raw, bytes)
                        else str(content_raw)
                    )

                    # Validate required fields
                    if not content:
                        logger.warning(f"Empty content in fact {fact_key}")
                        continue

                    # Build fact object
                    fact = {
                        "content": content,
                        "metadata": metadata,
                        "source": metadata.get("source", ""),
                        "title": metadata.get("title", ""),
                        "fact_id": metadata.get(
                            "fact_id", fact_key.replace("fact:", "")
                        ),
                    }
                    facts.append(fact)

                except json.JSONDecodeError as e:
                    logger.warning(f"JSON decode error in fact {fact_key}: {e}")
                    continue
                except Exception as e:
                    logger.exception(f"Error processing fact {fact_key}: {e}")
                    continue

            logger.info(
                f"Retrieved {len(facts)} facts from Redis (filtered from {len(results)} results)"
            )
            return facts

        except redis.RedisError as e:
            logger.error(f"Redis error in get_all_facts: {e}")
            return []
        except Exception as e:
            logger.exception(f"Unexpected error in get_all_facts: {e}")
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
            logger.warning(
                "KnowledgeBase instance deleted without proper cleanup - use await kb.close()"
            )
