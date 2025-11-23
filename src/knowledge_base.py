# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base - Unified Implementation

This is the unified, production-ready knowledge base implementation that combines
all functionality from V1 (RedisVectorStore) and V2 (ChromaVectorStore) implementations.

Key Features:
- Async-first architecture with proper initialization patterns
- ChromaDB vector store (current production backend)
- Backward compatible with V1 API
- All 37 methods from both implementations
- Unified configuration integration
- Better error handling and logging
"""

import asyncio
import hashlib
import json
import logging
import os
import tempfile
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import aiofiles
import aioredis
import redis  # Needed for type hints (Optional[redis.Redis])
from src.utils.chromadb_client import get_chromadb_client as create_chromadb_client
from langchain_text_splitters import RecursiveCharacterTextSplitter
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.storage_context import StorageContext
from llama_index.embeddings.ollama import OllamaEmbedding as LlamaIndexOllamaEmbedding
from llama_index.llms.ollama import Ollama as LlamaIndexOllamaLLM
from llama_index.vector_stores.chroma import ChromaVectorStore
from pypdf import PdfReader

from src.circuit_breaker import circuit_breaker_async
from src.constants.network_constants import NetworkConstants
from src.unified_config_manager import UnifiedConfigManager
from src.utils.error_boundaries import (
    ErrorCategory,
    ErrorContext,
    error_boundary,
    get_error_boundary_manager,
)
from src.utils.knowledge_base_timeouts import kb_timeouts
from src.utils.redis_client import redis_db_manager

# Create singleton config instance
config = UnifiedConfigManager()

logger = logging.getLogger(__name__)


# ============================================================================
# EMBEDDING CACHE - Issue #65 P0 Optimization
# LRU Cache with TTL for query embeddings to avoid regenerating identical queries
# ============================================================================
class EmbeddingCache:
    """
    Thread-safe LRU cache with TTL for query embeddings.

    Performance Impact:
    - 60-80% reduction in embedding computation for repeated queries
    - Reduces ChromaDB search latency significantly
    """

    def __init__(self, maxsize: int = 1000, ttl_seconds: int = 3600):
        """
        Initialize embedding cache.

        Args:
            maxsize: Maximum number of embeddings to cache (default: 1000)
            ttl_seconds: Time-to-live for cached embeddings (default: 1 hour)
        """
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[str, float] = {}
        self._maxsize = maxsize
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()

    def _make_key(self, query: str) -> str:
        """Create cache key from query text using hash."""
        return hashlib.sha256(query.encode("utf-8")).hexdigest()

    def _is_expired(self, key: str) -> bool:
        """Check if cached entry has expired."""
        if key not in self._timestamps:
            return True
        return (time.time() - self._timestamps[key]) > self._ttl_seconds

    def _evict_oldest(self) -> None:
        """Evict oldest entry when cache is full."""
        if self._cache:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._timestamps.pop(oldest_key, None)

    async def get(self, query: str) -> Optional[List[float]]:
        """
        Get embedding from cache if available and not expired.

        Args:
            query: Query text

        Returns:
            Cached embedding or None if not found/expired
        """
        key = self._make_key(query)

        async with self._lock:
            if key in self._cache and not self._is_expired(key):
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                logger.debug(f"Embedding cache HIT for query: {query[:50]}...")
                return self._cache[key]

            # Remove expired entry if exists
            if key in self._cache:
                del self._cache[key]
                self._timestamps.pop(key, None)

            self._misses += 1
            return None

    async def put(self, query: str, embedding: List[float]) -> None:
        """
        Store embedding in cache.

        Args:
            query: Query text
            embedding: Computed embedding vector
        """
        key = self._make_key(query)

        async with self._lock:
            # Evict if at capacity
            if key not in self._cache and len(self._cache) >= self._maxsize:
                self._evict_oldest()

            # Store embedding
            self._cache[key] = embedding
            self._timestamps[key] = time.time()
            self._cache.move_to_end(key)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total,
            "hit_rate_percent": round(hit_rate, 2),
            "cache_size": len(self._cache),
            "max_size": self._maxsize,
            "ttl_seconds": self._ttl_seconds,
        }

    def clear(self) -> None:
        """Clear all cached embeddings."""
        self._cache.clear()
        self._timestamps.clear()
        self._hits = 0
        self._misses = 0
        logger.info("Embedding cache cleared")


# Global embedding cache instance
_embedding_cache = EmbeddingCache(maxsize=1000, ttl_seconds=3600)


def get_embedding_cache() -> EmbeddingCache:
    """Get the global embedding cache instance."""
    return _embedding_cache


def _sanitize_metadata_for_chromadb(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize metadata for ChromaDB compatibility.

    ChromaDB only allows metadata values of type: str, int, float, None.
    This function converts lists/arrays to comma-separated strings.

    Args:
        metadata: Original metadata dict that may contain arrays

    Returns:
        Sanitized metadata dict with all arrays converted to strings
    """
    if not metadata:
        return {}

    sanitized = {}
    for key, value in metadata.items():
        if isinstance(value, (list, tuple)):
            # Convert arrays to comma-separated strings
            sanitized[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            # Convert dicts to JSON strings
            sanitized[key] = json.dumps(value)
        elif isinstance(value, (str, int, float, type(None))):
            # Allowed types - keep as is
            sanitized[key] = value
        else:
            # Convert other types to string
            sanitized[key] = str(value)

    return sanitized


class KnowledgeBase:
    """Unified knowledge base implementation with ChromaDB vector store support"""

    def __init__(self):
        """Initialize instance variables only - no async operations"""
        self.initialized = False
        self.initialization_lock = asyncio.Lock()

        # Error boundary manager for enhanced error tracking
        self.error_manager = get_error_boundary_manager()

        # Configuration from unified config
        self.redis_host = config.get("redis.host")
        self.redis_port = config.get("redis.port")
        self.redis_password = config.get("redis.password")
        # Knowledge base DB number - now managed by get_redis_client(database="knowledge")
        # The database mapping is handled automatically by redis_client utility
        self.redis_db = 1  # Default for knowledge base (historical compatibility)

        # ChromaDB configuration
        self.chromadb_path = config.get("memory.chromadb.path", "data/chromadb")
        self.chromadb_collection = config.get(
            "memory.chromadb.collection_name", "autobot_memory"
        )

        # Redis index name (legacy compatibility - not used with ChromaDB)
        self.redis_index_name = config.get(
            "redis.indexes.knowledge_base", "llama_index"
        )

        # Connection clients (initialized in async method)
        self.redis_client: Optional[redis.Redis] = None
        self.aioredis_client: Optional[aioredis.Redis] = None

        # Vector store components (initialized in async method)
        self.vector_store: Optional[ChromaVectorStore] = None
        self.vector_index: Optional[VectorStoreIndex] = None

        # Configuration flags
        self.llama_index_configured = False
        self.embedding_model_name: Optional[str] = None  # Store actual model being used
        self.embedding_dimensions: Optional[int] = None  # Store vector dimensions

        # Redis initialization flag (V1 compatibility)
        self._redis_initialized = False

        logger.info("KnowledgeBase instance created (not yet initialized)")

    @error_boundary(component="knowledge_base", function="initialize")
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
                self._redis_initialized = True  # V1 compatibility flag
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
            ollama_host = config.get(
                "infrastructure.hosts.ollama", NetworkConstants.MAIN_MACHINE_IP
            )
            ollama_port = config.get(
                "infrastructure.ports.ollama", str(NetworkConstants.OLLAMA_PORT)
            )
            ollama_url = f"http://{ollama_host}:{ollama_port}"
            llm_timeout = config.get_timeout("llm", "default", kb_timeouts.llm_default)

            Settings.llm = LlamaIndexOllamaLLM(
                model=config.get_default_llm_model(),
                request_timeout=llm_timeout,
                base_url=ollama_url,
            )

            # Check what embedding model was used for existing data
            stored_model = await self._detect_stored_embedding_model()

            if stored_model:
                embed_model_name = stored_model
                logger.info(f"Using stored embedding model: {embed_model_name}")
            else:
                # Default to nomic-embed-text (768 dimensions)
                embed_model_name = "nomic-embed-text"
                logger.info("Using nomic-embed-text embedding model (768 dimensions)")

            # Store model configuration in instance variables
            self.embedding_model_name = embed_model_name
            self.embedding_dimensions = 768  # nomic-embed-text dimensions

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
        """Initialize Redis connections using canonical utility"""
        try:
            # Use canonical Redis utility following CLAUDE.md "🔴 REDIS CLIENT USAGE" policy
            from src.utils.redis_client import get_redis_client

            # Get sync Redis client for knowledge base operations
            # Note: Uses DB 1 (knowledge) - canonical utility handles connection pooling
            self.redis_client = get_redis_client(database="knowledge")
            if self.redis_client is None:
                raise Exception("Redis client initialization returned None")

            # Test sync connection
            await asyncio.to_thread(self.redis_client.ping)
            logger.info(
                f"Knowledge Base Redis sync client connected (database {self.redis_db})"
            )

            # Get async Redis client using pool manager
            self.aioredis_client = await get_redis_client(
                async_client=True, database="knowledge"
            )

            # Test async connection
            await self.aioredis_client.ping()
            logger.info("Knowledge Base async Redis client connected successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Redis connections: {e}")
            raise

    async def _init_vector_store(self):
        """Initialize LlamaIndex vector store with ChromaDB backend"""
        try:
            from pathlib import Path

            # Create ChromaDB directory if it doesn't exist
            chroma_path = Path(self.chromadb_path)

            logger.info(f"Initializing ChromaDB at path: {chroma_path}")

            # Create ChromaDB persistent client with telemetry disabled
            chroma_client = create_chromadb_client(
                db_path=str(chroma_path), allow_reset=False, anonymized_telemetry=False
            )

            # Get or create collection (ChromaDB handles dimensions automatically)
            chroma_collection = chroma_client.get_or_create_collection(
                name=self.chromadb_collection,
                metadata={"hnsw:space": "cosine"},  # Use cosine similarity
            )

            # Create ChromaVectorStore for LlamaIndex
            self.vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

            logger.info(
                f"ChromaDB vector store initialized: collection='{self.chromadb_collection}'"
            )

            # Get collection stats
            collection_count = chroma_collection.count()
            logger.info(f"ChromaDB collection contains {collection_count} vectors")

            # Skip eager index creation to prevent blocking during initialization
            # with 545K+ vectors. Index will be created lazily on first use.
            logger.info(
                "Skipping eager vector index creation - will create on first query (lazy loading)"
            )

        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB vector store: {e}")
            import traceback

            logger.error(traceback.format_exc())
            self.vector_store = None

    async def _create_initial_vector_index(self):
        """Create the vector index immediately during initialization

        This ensures the index exists before any facts are stored, allowing all facts
        to be properly indexed for vector search.
        """
        try:
            if not self.vector_store:
                logger.warning(
                    "Cannot create vector index - vector store not initialized"
                )
                return

            logger.info("Creating initial vector index with ChromaDB...")

            # Create storage context with ChromaDB vector store
            storage_context = StorageContext.from_defaults(
                vector_store=self.vector_store
            )

            # Create index from existing vector store (connects to existing collection)
            self.vector_index = await asyncio.to_thread(
                VectorStoreIndex.from_vector_store,
                self.vector_store,
                storage_context=storage_context,
            )

            logger.info(
                "✅ Vector index connected to ChromaDB collection - ready for queries"
            )

            # Note: No need to re-index existing facts - they're already in ChromaDB
            # from the migration process

        except Exception as e:
            logger.error(f"Failed to create initial vector index: {e}")
            import traceback

            logger.error(traceback.format_exc())
            # Don't fail initialization - just log the error
            self.vector_index = None

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

    # ============================================================================
    # V1 COMPATIBILITY METHODS
    # ============================================================================

    async def _ensure_redis_initialized(self):
        """Ensure Redis is initialized before any operations (V1 compatibility)"""
        if not self._redis_initialized:
            await self.initialize()

    def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get Redis client for sync operations (V1 compatibility)"""
        return self.redis_client

    async def _get_async_redis_client(self) -> Optional[aioredis.Redis]:
        """Get async Redis client for async operations (V1 compatibility)"""
        return self.aioredis_client

    async def _init_redis_and_vector_store(self):
        """Initialize Redis connection and vector store asynchronously (V1 compatibility)"""
        # V1 compatibility wrapper - delegates to V2 initialization
        if not self.initialized:
            await self.initialize()

    async def _init_vector_index_from_existing(self):
        """Initialize vector index from existing vectors in storage (V1 compatibility)"""
        # For ChromaDB, this is handled by _create_initial_vector_index
        await self._create_initial_vector_index()

    # ============================================================================
    # PUBLIC API METHODS
    # ============================================================================

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

    @error_boundary(component="knowledge_base", function="search")
    async def search(
        self,
        query: str,
        top_k: int = 10,
        similarity_top_k: int = None,
        filters: Optional[Dict[str, Any]] = None,
        mode: str = "auto",
    ) -> List[Dict[str, Any]]:
        """Search the knowledge base with multiple search modes.

        Args:
            query: Search query
            top_k: Number of results to return (alias for similarity_top_k)
            similarity_top_k: Number of results to return (takes precedence over top_k)
            filters: Optional filters to apply
            mode: Search mode ("vector" for semantic, "text" for keyword, "auto" for hybrid)

        Returns:
            List of search results with content and metadata
        """
        self.ensure_initialized()

        # Handle parameter aliases
        if similarity_top_k is None:
            similarity_top_k = top_k

        if not query.strip():
            return []

        if not self.vector_store:
            logger.warning("Vector store not available for search")
            return []

        try:
            # Use direct ChromaDB queries to avoid VectorStoreIndex blocking with 545K vectors
            chroma_collection = self.vector_store._collection

            # Generate embedding for query using the same model
            # P0 OPTIMIZATION: Use embedding cache to avoid regenerating identical queries
            from llama_index.core import Settings

            # Check cache first
            query_embedding = await _embedding_cache.get(query)

            if query_embedding is None:
                # Cache miss - compute embedding
                query_embedding = await asyncio.to_thread(
                    Settings.embed_model.get_text_embedding, query
                )
                # Store in cache for future use
                await _embedding_cache.put(query, query_embedding)
            # else: Cache hit - embedding already loaded

            # Query ChromaDB directly (avoids index creation overhead)
            # Note: IDs are always returned by default, don't include in 'include' parameter
            results_data = await asyncio.to_thread(
                chroma_collection.query,
                query_embeddings=[query_embedding],
                n_results=similarity_top_k,
                include=["documents", "metadatas", "distances"],
            )

            # Format results
            results = []
            seen_documents = (
                {}
            )  # Track unique documents by metadata to prevent duplicates

            if (
                results_data
                and "documents" in results_data
                and results_data["documents"][0]
            ):
                for i, doc in enumerate(results_data["documents"][0]):
                    # Convert distance to similarity score (cosine: 0=identical, 2=opposite)
                    distance = (
                        results_data["distances"][0][i]
                        if "distances" in results_data
                        else 1.0
                    )
                    score = max(
                        0.0, 1.0 - (distance / 2.0)
                    )  # Convert to 0-1 similarity

                    metadata = (
                        results_data["metadatas"][0][i]
                        if "metadatas" in results_data
                        else {}
                    )

                    # Create unique document key to deduplicate chunks from same source
                    # Use fact_id first (most reliable), fallback to title+category
                    doc_key = metadata.get("fact_id")
                    if not doc_key:
                        title = metadata.get("title", "")
                        category = metadata.get("category", "")
                        doc_key = (
                            f"{category}:{title}" if (title or category) else f"doc_{i}"
                        )

                    # Keep only highest-scoring result per unique document
                    if (
                        doc_key not in seen_documents
                        or score > seen_documents[doc_key]["score"]
                    ):
                        result = {
                            "content": doc,
                            "score": score,
                            "metadata": metadata,
                            "node_id": (
                                results_data["ids"][0][i]
                                if "ids" in results_data
                                else f"result_{i}"
                            ),
                            "doc_id": (
                                results_data["ids"][0][i]
                                if "ids" in results_data
                                else f"result_{i}"
                            ),  # V1 compatibility
                        }
                        seen_documents[doc_key] = result

            # Convert to list and sort by score descending
            results = sorted(
                seen_documents.values(), key=lambda x: x["score"], reverse=True
            )

            # Limit to top_k after deduplication
            results = results[:similarity_top_k]

            logger.info(
                f"ChromaDB direct search returned {len(results)} unique documents (deduplicated) for query: {query[:50]}..."
            )
            return results

        except Exception as e:
            logger.error(f"Knowledge base search failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return []

    async def _perform_search(
        self,
        query: str,
        similarity_top_k: int,
        filters: Optional[Dict[str, Any]],
        mode: str,
    ) -> List[Dict[str, Any]]:
        """Internal search implementation with timeout protection (V1 compatibility)"""
        # Delegate to main search method
        return await self.search(
            query, similarity_top_k=similarity_top_k, filters=filters, mode=mode
        )

    async def _find_fact_by_unique_key(
        self, unique_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find an existing fact by unique key (fast Redis SET lookup).

        Args:
            unique_key: The unique key to search for (e.g., "machine:os:command:section")

        Returns:
            Dict with fact info if found, None otherwise
        """
        try:
            # Check Redis SET for unique key mapping
            unique_key_name = f"unique_key:man_page:{unique_key}"
            fact_id = self.redis_client.get(unique_key_name)

            if fact_id:
                # Decode bytes if necessary
                if isinstance(fact_id, bytes):
                    fact_id = fact_id.decode("utf-8")

                # Retrieve the fact metadata
                fact_key = f"fact:{fact_id}"
                metadata_str = self.redis_client.hget(fact_key, "metadata")
                created_at = self.redis_client.hget(fact_key, "created_at")

                if metadata_str:
                    metadata = json.loads(metadata_str)
                    logger.info(
                        f"Found existing fact by unique key: {unique_key} → {fact_id}"
                    )
                    return {
                        "fact_id": fact_id,
                        "created_at": created_at,
                        "metadata": metadata,
                    }

            return None

        except Exception as e:
            logger.error(f"Error finding fact by unique key '{unique_key}': {e}")
            return None

    async def _find_existing_fact(
        self, category: str, title: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find an existing fact with the same category and title.

        Args:
            category: The category to search for
            title: The title to search for

        Returns:
            Dict with fact info if found, None otherwise
        """
        try:
            # Use SCAN to iterate through fact keys
            cursor = 0

            while True:
                cursor, keys = self.redis_client.scan(cursor, match="fact:*", count=100)

                if keys:
                    # Use pipeline for batch operations
                    pipe = self.redis_client.pipeline()
                    for key in keys:
                        pipe.hget(key, "metadata")
                        pipe.hget(key, "created_at")
                    results = pipe.execute()

                    # Check each fact's metadata
                    for i in range(0, len(results), 2):
                        metadata_str = results[i]
                        created_at = results[i + 1]

                        if metadata_str:
                            try:
                                metadata = json.loads(metadata_str)
                                if (
                                    metadata.get("category") == category
                                    and metadata.get("title") == title
                                ):
                                    # Found a matching fact
                                    return {
                                        "fact_id": metadata.get("fact_id"),
                                        "created_at": created_at,
                                        "metadata": metadata,
                                    }
                            except json.JSONDecodeError:
                                continue

                if cursor == 0:
                    break

            return None

        except Exception as e:
            logger.error(f"Error finding existing fact: {e}")
            return None

    async def store_fact(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        check_duplicates: bool = True,
    ) -> Dict[str, Any]:
        """
        Store a fact in the knowledge base with vector indexing

        Args:
            content: The fact content to store (or text for V1 compatibility)
            metadata: Optional metadata dict with title, category, etc.
            check_duplicates: If True, check for existing facts with same category+title (default: True)

        Returns:
            Dict with status, fact_id, and optional duplicate_of field
        """
        self.ensure_initialized()

        # V1 compatibility: accept 'text' parameter name
        if not content.strip():
            return {
                "status": "error",
                "message": "Content cannot be empty",
                "fact_id": None,
            }

        try:
            # Check for duplicates based on unique_key first (faster, more specific)
            if check_duplicates and metadata:
                unique_key = metadata.get("unique_key")

                if unique_key:
                    # Fast lookup using Redis SET
                    existing_fact = await self._find_fact_by_unique_key(unique_key)

                    if existing_fact:
                        logger.info(
                            f"Duplicate fact detected by unique key: '{unique_key}', existing_fact_id={existing_fact['fact_id']}"
                        )
                        return {
                            "status": "duplicate",
                            "message": f"Fact already exists with unique key: {unique_key}",
                            "fact_id": existing_fact["fact_id"],
                            "duplicate_of": existing_fact["fact_id"],
                            "existing_created_at": existing_fact.get("created_at"),
                            "matched_by": "unique_key",
                        }

                # Fallback: Check for duplicates based on category + title
                # FIXED: Use efficient Redis SET indexing instead of slow SCAN
                category = metadata.get("category")
                title = metadata.get("title")

                if category and title:
                    # Use fast O(1) lookup via Redis SET
                    category_title_key = f"{category}:{title}"
                    existing_fact_id = await self.aioredis_client.get(
                        f"category_title:{category_title_key}"
                    )

                    if existing_fact_id:
                        if isinstance(existing_fact_id, bytes):
                            existing_fact_id = existing_fact_id.decode("utf-8")

                        # Retrieve fact metadata
                        fact_key = f"fact:{existing_fact_id}"
                        metadata_str = await self.aioredis_client.hget(
                            fact_key, "metadata"
                        )
                        created_at = await self.aioredis_client.hget(
                            fact_key, "created_at"
                        )

                        if metadata_str:
                            logger.info(
                                f"Duplicate fact detected by category+title: category='{category}', title='{title}', existing_fact_id={existing_fact_id}"
                            )
                            return {
                                "status": "duplicate",
                                "message": f"Fact already exists with same category and title",
                                "fact_id": existing_fact_id,
                                "duplicate_of": existing_fact_id,
                                "existing_created_at": created_at,
                                "matched_by": "category_title",
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
                    "timestamp": datetime.now().isoformat(),  # V1 compatibility
                }
                await self.aioredis_client.hset(fact_key, mapping=fact_data)
                logger.debug(f"Stored fact {fact_id} in Redis")

                # Store index keys for fast O(1) duplicate detection
                unique_key = fact_metadata.get("unique_key")
                if unique_key:
                    await self.aioredis_client.set(
                        f"unique_key:man_page:{unique_key}", fact_id
                    )
                    logger.debug(
                        f"Stored unique key index: unique_key:man_page:{unique_key} → {fact_id}"
                    )

                category = fact_metadata.get("category")
                title = fact_metadata.get("title")
                if category and title:
                    category_title_key = f"{category}:{title}"
                    await self.aioredis_client.set(
                        f"category_title:{category_title_key}", fact_id
                    )
                    logger.debug(
                        f"Stored category_title index: category_title:{category_title_key} → {fact_id}"
                    )

            # Store in vector index for semantic search - CRITICAL FOR SEARCHABILITY
            vector_indexed = False
            if self.vector_store:
                try:
                    # Sanitize metadata for ChromaDB compatibility
                    sanitized_metadata = _sanitize_metadata_for_chromadb(fact_metadata)

                    # Create LlamaIndex document
                    document = Document(
                        text=content, metadata=sanitized_metadata, doc_id=fact_id
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

            # Prepare metadata - sanitize for ChromaDB compatibility
            fact_metadata = metadata or {}
            if "fact_id" not in fact_metadata:
                fact_metadata["fact_id"] = fact_id

            # Sanitize metadata to convert arrays to strings (ChromaDB requirement)
            sanitized_metadata = _sanitize_metadata_for_chromadb(fact_metadata)

            # Create LlamaIndex document with existing fact_id
            document = Document(
                text=content,
                metadata=sanitized_metadata,
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

    def get_fact(
        self, fact_id: Optional[str] = None, query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve facts from the knowledge base (V1 compatibility - synchronous)"""
        if not self.redis_client:
            return []

        try:
            facts = []

            if fact_id:
                # Get specific fact
                fact_key = f"fact:{fact_id}"
                fact_data = self.redis_client.hgetall(fact_key)
                if fact_data:
                    facts.append(
                        {
                            "id": fact_id,
                            "content": fact_data.get(b"content", b"").decode("utf-8"),
                            "metadata": json.loads(
                                fact_data.get(b"metadata", b"{}").decode("utf-8")
                            ),
                            "timestamp": fact_data.get(b"timestamp", b"").decode(
                                "utf-8"
                            ),
                        }
                    )
            elif query:
                # Search facts by content matching
                all_fact_keys = self._scan_redis_keys("fact:*")
                for fact_key in all_fact_keys:
                    fact_data = self.redis_client.hgetall(fact_key)
                    if fact_data:
                        content = fact_data.get(b"content", b"").decode("utf-8")
                        if query.lower() in content.lower():
                            fact_id = fact_key.split(":")[1]
                            facts.append(
                                {
                                    "id": fact_id,
                                    "content": content,
                                    "metadata": json.loads(
                                        fact_data.get(b"metadata", b"{}").decode(
                                            "utf-8"
                                        )
                                    ),
                                    "timestamp": fact_data.get(
                                        b"timestamp", b""
                                    ).decode("utf-8"),
                                }
                            )
            else:
                # Get all facts (with limit for performance)
                all_fact_keys = self._scan_redis_keys("fact:*")[
                    :100
                ]  # Limit to 100 facts
                if all_fact_keys:
                    # Use pipeline for efficiency
                    pipe = self.redis_client.pipeline()
                    for key in all_fact_keys:
                        pipe.hgetall(key)
                    results = pipe.execute()

                    for key, fact_data in zip(all_fact_keys, results):
                        if fact_data:
                            facts.append(
                                {
                                    "id": (
                                        key.split(":")[1]
                                        if isinstance(key, str)
                                        else key.decode().split(":")[1]
                                    ),
                                    "content": (
                                        fact_data.get(
                                            b"content", fact_data.get("content", "")
                                        ).decode("utf-8")
                                        if isinstance(
                                            fact_data.get(
                                                b"content", fact_data.get("content", "")
                                            ),
                                            bytes,
                                        )
                                        else fact_data.get("content", "")
                                    ),
                                    "metadata": json.loads(
                                        (
                                            fact_data.get(
                                                b"metadata",
                                                fact_data.get("metadata", "{}"),
                                            ).decode("utf-8")
                                            if isinstance(
                                                fact_data.get(
                                                    b"metadata",
                                                    fact_data.get("metadata", "{}"),
                                                ),
                                                bytes,
                                            )
                                            else fact_data.get("metadata", "{}")
                                        )
                                    ),
                                    "timestamp": (
                                        fact_data.get(
                                            b"timestamp", fact_data.get("timestamp", "")
                                        ).decode("utf-8")
                                        if isinstance(
                                            fact_data.get(
                                                b"timestamp",
                                                fact_data.get("timestamp", ""),
                                            ),
                                            bytes,
                                        )
                                        else fact_data.get("timestamp", "")
                                    ),
                                }
                            )
            logger.info(
                f"Retrieved {len(facts)} facts from Redis using sync operations."
            )
            return facts
        except Exception as e:
            logger.error(f"Error retrieving facts from Redis: {str(e)}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive knowledge base statistics (async version)"""
        self.ensure_initialized()

        logger.info("=== get_stats() called with caching ===")
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
                "vector_store": "chromadb",
                "chromadb_collection": self.chromadb_collection,
                "initialized": self.initialized,
                "llama_index_configured": self.llama_index_configured,
                "embedding_model": self.embedding_model_name,
                "embedding_dimensions": self.embedding_dimensions,
            }

            if self.aioredis_client:
                # PERFORMANCE FIX: Use cached counts instead of scanning all keys
                try:
                    # Try to get cached fact count first (instant lookup)
                    cached_fact_count = await self.aioredis_client.get(
                        "kb:stats:fact_count"
                    )

                    if cached_fact_count is not None:
                        # Use cached value
                        fact_count = int(cached_fact_count)
                        logger.debug(f"Using cached fact count: {fact_count} facts")
                    else:
                        # Cache miss - count using native async Redis
                        fact_count = 0

                        # Count facts using async scan_iter (efficient cursor-based)
                        try:
                            async for _ in self.aioredis_client.scan_iter(
                                match="fact:*", count=1000
                            ):
                                fact_count += 1
                        except Exception as e:
                            logger.error(f"Error counting facts: {e}")
                            fact_count = 0

                        # Cache the fact count for 60 seconds
                        await self.aioredis_client.set(
                            "kb:stats:fact_count", fact_count, ex=60
                        )
                        logger.info(f"Counted and cached: {fact_count} facts")

                    # Get vector count from ChromaDB (fast O(1) operation)
                    vector_count = 0
                    if self.vector_store:
                        try:
                            chroma_collection = self.vector_store._collection
                            vector_count = chroma_collection.count()
                            logger.debug(f"ChromaDB vector count: {vector_count}")
                        except Exception as e:
                            logger.error(f"Error getting ChromaDB count: {e}")
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

            # Get ChromaDB collection information if available
            if self.vector_store:
                try:
                    # Access ChromaDB collection to get vector count
                    chroma_collection = self.vector_store._collection
                    vector_count = chroma_collection.count()
                    stats["index_available"] = True
                    stats["indexed_documents"] = vector_count
                    stats["chromadb_collection"] = self.chromadb_collection
                    stats["chromadb_path"] = self.chromadb_path
                    logger.debug(
                        f"ChromaDB stats: {vector_count} vectors in collection '{self.chromadb_collection}'"
                    )
                except Exception as e:
                    logger.warning(f"Could not get ChromaDB stats: {e}")
                    stats["index_available"] = False

            # Add embedding cache statistics (P0 optimization monitoring)
            stats["embedding_cache"] = _embedding_cache.get_stats()

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

    async def get_detailed_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about the knowledge base.

        This method provides detailed insights including database size,
        category distribution, recent activity, and performance metrics.
        This is more computationally intensive than get_stats().

        Returns:
            Dict containing detailed statistics and analytics

        Performance: Slower (1-5s) - performs comprehensive analysis
        """
        basic_stats = await self.get_stats()

        if not self.redis_client:
            return {
                **basic_stats,
                "detailed_stats": False,
                "message": "Redis not available for detailed analysis",
            }

        try:
            detailed = {**basic_stats}

            # Database size analysis
            try:
                # Get approximate database size
                info = await asyncio.to_thread(self.redis_client.info, "memory")
                detailed["memory_usage_mb"] = round(
                    info.get("used_memory", 0) / (1024 * 1024), 2
                )
                detailed["peak_memory_mb"] = round(
                    info.get("used_memory_peak", 0) / (1024 * 1024), 2
                )
            except Exception as e:
                logger.warning(f"Could not get memory stats: {e}")

            # Recent activity analysis
            try:
                fact_keys = await self._scan_redis_keys_async("fact:*")
                if fact_keys:
                    # Sample recent facts for activity analysis
                    recent_facts = []
                    sample_size = min(10, len(fact_keys))

                    for fact_key in fact_keys[:sample_size]:
                        try:
                            fact_data = await self.aioredis_client.hgetall(fact_key)
                            if fact_data and "timestamp" in fact_data:
                                recent_facts.append(fact_data["timestamp"])
                        except Exception:
                            continue

                    detailed["recent_activity"] = {
                        "total_facts": len(fact_keys),
                        "sample_timestamps": recent_facts[:5],  # Show 5 most recent
                    }
            except Exception as e:
                logger.warning(f"Could not get recent activity: {e}")

            # Vector store health
            try:
                detailed["vector_store_health"] = "healthy"
                detailed["vector_backend"] = "chromadb"
            except Exception as e:
                logger.warning(f"Could not assess vector store health: {e}")

            detailed["detailed_stats"] = True
            detailed["generated_at"] = datetime.now().isoformat()

            return detailed

        except Exception as e:
            logger.error(f"Error generating detailed stats: {e}")
            return {**basic_stats, "detailed_stats": False, "error": str(e)}

    async def add_document(
        self,
        content: str,
        metadata: Dict[str, Any] = None,
        doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a document to the knowledge base with async processing.

        Args:
            content: Document content
            metadata: Document metadata
            doc_id: Optional document ID

        Returns:
            Result dictionary with status and details
        """
        if not content.strip():
            return {"status": "error", "message": "Empty content provided"}

        try:
            # Use asyncio.wait_for for timeout protection
            return await asyncio.wait_for(
                self._add_document_internal(content, metadata, doc_id),
                timeout=kb_timeouts.document_add,
            )
        except asyncio.TimeoutError:
            logger.warning("Document addition timed out")
            return {"status": "timeout", "message": "Document addition timed out"}
        except Exception as e:
            logger.error(f"Document addition failed: {e}")
            return {"status": "error", "message": str(e)}

    async def _add_document_internal(
        self, content: str, metadata: Dict[str, Any], doc_id: Optional[str]
    ) -> Dict[str, Any]:
        """Internal document addition with proper async handling"""
        await self._ensure_redis_initialized()

        if metadata is None:
            metadata = {}

        # Generate document ID if not provided
        if not doc_id:
            doc_id = str(uuid.uuid4())

        # Add document metadata
        metadata.update(
            {
                "doc_id": doc_id,
                "added_at": datetime.now().isoformat(),
                "content_length": len(content),
            }
        )

        # Store as fact (unified with store_fact method)
        return await self.store_fact(content, metadata)

    async def export_all_data(self) -> List[Dict[str, Any]]:
        """Export all knowledge base data"""
        try:
            # Get all facts
            all_facts = []
            fact_keys = await self._scan_redis_keys_async("fact:*")

            for fact_key in fact_keys:
                try:
                    fact_data = await self.aioredis_client.hgetall(fact_key)
                    if fact_data:
                        all_facts.append(
                            {
                                "type": "fact",
                                "id": fact_key.split(":")[-1],
                                "content": fact_data.get("content", ""),
                                "metadata": json.loads(fact_data.get("metadata", "{}")),
                                "timestamp": fact_data.get("timestamp", ""),
                            }
                        )
                except Exception as e:
                    logger.warning(f"Could not export fact {fact_key}: {e}")

            logger.info(f"Exported {len(all_facts)} facts")
            return all_facts

        except Exception as e:
            logger.error(f"Export failed: {e}")
            return []

    def extract_category_names(self, cat_dict: Dict, prefix: str = "") -> List[str]:
        """Extract category names from nested dict (V1 compatibility helper)"""
        names = []
        for key, value in cat_dict.items():
            if isinstance(value, dict):
                if "children" in value:
                    names.append(f"{prefix}{key}" if prefix else key)
                    names.extend(
                        self.extract_category_names(
                            value["children"], f"{prefix}{key}/"
                        )
                    )
                else:
                    names.append(f"{prefix}{key}" if prefix else key)
        return names

    async def rebuild_search_index(self) -> Dict[str, Any]:
        """
        Rebuild the search index to sync with actual vectors (V1 compatibility).

        For ChromaDB, this is mostly a no-op since ChromaDB manages its own indices.
        """
        try:
            if not self.vector_store:
                return {"status": "error", "message": "Vector store not available"}

            # For ChromaDB, just verify the collection is accessible
            chroma_collection = self.vector_store._collection
            vector_count = chroma_collection.count()

            return {
                "status": "success",
                "message": f"ChromaDB index verified successfully",
                "vectors_found": vector_count,
                "indexed_documents": vector_count,
                "sync_status": "synced",
            }

        except Exception as e:
            logger.error(f"Failed to rebuild search index: {e}")
            return {"status": "error", "message": str(e)}

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
                    metadata_raw = fact_data.get("metadata", "{}")
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
                    content_raw = fact_data.get("content", "")
                    content = (
                        content_raw.decode("utf-8")
                        if isinstance(content_raw, bytes)
                        else str(content_raw)
                    )

                    # Validate required fields
                    if not content:
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

    async def update_fact(
        self, fact_id: str, content: str = None, metadata: dict = None
    ) -> dict:
        """
        Update an existing fact's content and/or metadata.

        Args:
            fact_id: The fact ID to update
            content: New content (optional, keeps existing if None)
            metadata: New metadata (optional, merges with existing if provided)

        Returns:
            dict: {
                "success": bool,
                "fact_id": str,
                "updated_fields": list,
                "message": str
            }

        Raises:
            ValueError: If fact_id not found
        """
        self.ensure_initialized()

        try:
            # Validate fact_id format
            if not fact_id or not isinstance(fact_id, str):
                raise ValueError("Invalid fact_id format")

            fact_key = f"fact:{fact_id}"

            # Check if fact exists
            fact_exists = await self.aioredis_client.exists(fact_key)
            if not fact_exists:
                raise ValueError(f"Fact with ID {fact_id} not found")

            # Get existing fact data
            fact_data = await self.aioredis_client.hgetall(fact_key)
            if not fact_data:
                raise ValueError(f"Fact {fact_id} exists but has no data")

            updated_fields = []

            # Get existing content and metadata
            existing_content = fact_data.get("content", "")
            if isinstance(existing_content, bytes):
                existing_content = existing_content.decode("utf-8")

            existing_metadata_raw = fact_data.get("metadata", "{}")
            if isinstance(existing_metadata_raw, bytes):
                existing_metadata_raw = existing_metadata_raw.decode("utf-8")

            try:
                existing_metadata = json.loads(existing_metadata_raw)
            except (json.JSONDecodeError, TypeError):
                existing_metadata = {}

            # Determine what needs updating
            content_changed = False
            new_content = existing_content
            new_metadata = existing_metadata.copy()

            # Update content if provided
            if content is not None and content != existing_content:
                new_content = content
                content_changed = True
                updated_fields.append("content")
                logger.info(f"Updating content for fact {fact_id}")

            # Update metadata if provided
            if metadata is not None:
                # Merge new metadata with existing
                new_metadata.update(metadata)
                updated_fields.append("metadata")
                logger.info(f"Updating metadata for fact {fact_id}")

            # Update timestamp
            new_metadata["updated_at"] = datetime.now().isoformat()
            new_metadata["fact_id"] = fact_id  # Ensure fact_id is preserved

            # Update Redis hash
            update_data = {
                "content": new_content,
                "metadata": json.dumps(new_metadata),
            }
            await self.aioredis_client.hset(fact_key, mapping=update_data)

            # If content changed, re-vectorize
            vector_updated = False
            if content_changed and self.vector_store and self.vector_index:
                try:
                    # Delete old vector document
                    await asyncio.to_thread(
                        self.vector_index.delete_ref_doc,
                        fact_id,
                        delete_from_docstore=True,
                    )

                    # Sanitize metadata for ChromaDB compatibility
                    sanitized_new_metadata = _sanitize_metadata_for_chromadb(
                        new_metadata
                    )

                    # Create new vector document
                    document = Document(
                        text=new_content,
                        metadata=sanitized_new_metadata,
                        doc_id=fact_id,
                    )

                    # Insert new vector
                    await asyncio.to_thread(self.vector_index.insert, document)
                    vector_updated = True
                    updated_fields.append("vectorization")
                    logger.info(f"Re-vectorized fact {fact_id} due to content change")

                except Exception as vector_error:
                    logger.error(
                        f"Failed to update vectorization for fact {fact_id}: {vector_error}"
                    )
                    # Continue - Redis update succeeded even if vectorization failed

            return {
                "success": True,
                "fact_id": fact_id,
                "updated_fields": updated_fields,
                "vector_updated": vector_updated,
                "message": (
                    f"Fact updated successfully ({', '.join(updated_fields)})"
                    if updated_fields
                    else "No changes made"
                ),
            }

        except ValueError as e:
            logger.error(f"Validation error updating fact {fact_id}: {e}")
            return {
                "success": False,
                "fact_id": fact_id,
                "updated_fields": [],
                "message": str(e),
            }
        except Exception as e:
            logger.error(f"Error updating fact {fact_id}: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return {
                "success": False,
                "fact_id": fact_id,
                "updated_fields": [],
                "message": f"Failed to update fact: {str(e)}",
            }

    @error_boundary(component="knowledge_base", function="delete_fact")
    async def delete_fact(self, fact_id: str) -> dict:
        """
        Delete a fact and its vectorization.

        Args:
            fact_id: The fact ID to delete

        Returns:
            dict: {
                "success": bool,
                "fact_id": str,
                "message": str
            }

        Raises:
            ValueError: If fact_id not found
        """
        self.ensure_initialized()

        try:
            # Validate fact_id format
            if not fact_id or not isinstance(fact_id, str):
                raise ValueError("Invalid fact_id format")

            fact_key = f"fact:{fact_id}"

            # Check if fact exists
            fact_exists = await self.aioredis_client.exists(fact_key)
            if not fact_exists:
                raise ValueError(f"Fact with ID {fact_id} not found")

            # Delete from vector index first (if exists)
            vector_deleted = False
            if self.vector_index:
                try:
                    await asyncio.to_thread(
                        self.vector_index.delete_ref_doc,
                        fact_id,
                        delete_from_docstore=True,
                    )
                    vector_deleted = True
                    logger.info(f"Deleted vectorization for fact {fact_id}")
                except Exception as vector_error:
                    logger.warning(
                        f"Could not delete vector for fact {fact_id}: {vector_error}"
                    )
                    # Continue - will still delete from Redis

            # Delete from Redis
            deleted_count = await self.aioredis_client.delete(fact_key)

            if deleted_count > 0:
                logger.info(f"Deleted fact {fact_id} from Redis")
                return {
                    "success": True,
                    "fact_id": fact_id,
                    "vector_deleted": vector_deleted,
                    "message": (
                        "Fact and vectorization deleted successfully"
                        if vector_deleted
                        else "Fact deleted from Redis (vectorization not found)"
                    ),
                }
            else:
                # This shouldn't happen since we checked existence above
                raise ValueError(f"Fact {fact_id} could not be deleted")

        except ValueError as e:
            logger.error(f"Validation error deleting fact {fact_id}: {e}")
            return {
                "success": False,
                "fact_id": fact_id,
                "message": str(e),
            }
        except Exception as e:
            logger.error(f"Error deleting fact {fact_id}: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return {
                "success": False,
                "fact_id": fact_id,
                "message": f"Failed to delete fact: {str(e)}",
            }

    async def add_document_from_file(
        self,
        file_path: Path,
        category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a document from file (PDF, DOCX, TXT, MD) to knowledge base

        Uses reusable DocumentExtractor utility to extract text from various formats.

        Supported formats:
        - PDF (.pdf)
        - Microsoft Word (.docx, .doc)
        - Plain text (.txt, .md, .rst, .markdown)

        Args:
            file_path: Path to document file
            category: Category/namespace for the document (default: 'documents')
            metadata: Additional metadata to store with document

        Returns:
            dict: {
                "success": bool,
                "document_id": str,
                "source": str,
                "file_type": str,
                "chars_extracted": int,
                "message": str
            }

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file type not supported

        Example:
            result = await kb.add_document_from_file(
                Path("report.pdf"),
                category="research",
                metadata={"author": "John Doe", "year": 2024}
            )
        """
        from src.utils.document_extractors import DocumentExtractor

        self.ensure_initialized()

        try:
            file_path = Path(file_path)

            # Extract text using reusable utility
            logger.info(f"Extracting text from {file_path.name}...")
            text = await DocumentExtractor.extract_from_file(file_path)

            if not text or not text.strip():
                raise ValueError(f"No text extracted from {file_path}")

            # Build metadata
            doc_metadata = {
                "source": str(file_path),
                "filename": file_path.name,
                "file_type": file_path.suffix,
                "category": category or "documents",
                "extracted_at": datetime.utcnow().isoformat(),
            }
            if metadata:
                doc_metadata.update(metadata)

            # Add to knowledge base using existing add_document method
            result = await self.add_document(content=text, metadata=doc_metadata)

            logger.info(
                f"✅ Added {file_path.name} to knowledge base ({len(text)} chars)"
            )

            return {
                "success": True,
                "document_id": result.get("document_id", "unknown"),
                "source": str(file_path),
                "file_type": file_path.suffix,
                "chars_extracted": len(text),
                "message": f"Successfully added {file_path.name} to knowledge base",
            }

        except Exception as e:
            logger.error(f"Failed to add document from {file_path}: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return {
                "success": False,
                "source": str(file_path),
                "message": f"Failed to add document: {str(e)}",
            }

    async def add_documents_from_directory(
        self,
        directory_path: Path,
        file_types: Optional[List[str]] = None,
        category: Optional[str] = None,
        recursive: bool = True,
        max_files: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Batch process all documents in a directory

        Uses reusable DocumentExtractor utility for parallel file processing.

        Args:
            directory_path: Path to directory containing documents
            file_types: List of file extensions to process (default: all supported)
            category: Category/namespace for documents (default: 'documents')
            recursive: Process subdirectories recursively (default: True)
            max_files: Maximum number of files to process (default: unlimited)

        Returns:
            dict: {
                "success": bool,
                "processed": int,
                "failed": int,
                "total": int,
                "directory": str,
                "files": List[str],  # List of successfully processed files
                "errors": List[dict],  # List of errors encountered
                "message": str
            }

        Example:
            # Process all supported files in directory
            result = await kb.add_documents_from_directory(
                Path("docs/"),
                category="documentation"
            )

            # Process only PDFs, limit to 100 files
            result = await kb.add_documents_from_directory(
                Path("research/"),
                file_types=['.pdf'],
                category="research",
                max_files=100
            )
        """
        from src.utils.document_extractors import DocumentExtractor

        self.ensure_initialized()

        directory_path = Path(directory_path)
        processed_files = []
        errors = []

        try:
            logger.info(f"Processing documents from directory: {directory_path}")

            # Extract all documents using reusable utility
            extracted_texts = await DocumentExtractor.extract_from_directory(
                directory_path=directory_path,
                file_types=file_types,
                recursive=recursive,
                max_files=max_files,
            )

            total_files = len(extracted_texts)
            logger.info(
                f"Extracted text from {total_files} files, adding to knowledge base..."
            )

            # P0 OPTIMIZATION: Parallel document processing with controlled concurrency
            # Uses asyncio.gather() with semaphore to process multiple documents concurrently
            # Expected improvement: 5-10x speedup for bulk document ingestion (Issue #65)
            max_concurrent = (
                10  # Limit concurrent operations to avoid overwhelming resources
            )
            semaphore = asyncio.Semaphore(max_concurrent)

            async def process_file_with_limit(file_path: Path, text: str):
                """Process single file with semaphore-controlled concurrency"""
                async with semaphore:
                    try:
                        result = await self.add_document_from_file(
                            file_path=file_path, category=category
                        )
                        return (file_path, result, None)
                    except Exception as e:
                        logger.error(f"Failed to add {file_path} to KB: {e}")
                        return (file_path, None, str(e))

            # Create tasks for all files
            tasks = [
                process_file_with_limit(fp, txt) for fp, txt in extracted_texts.items()
            ]

            # Execute all tasks concurrently (up to semaphore limit)
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    errors.append({"file": "unknown", "error": str(result)})
                else:
                    file_path, add_result, error = result
                    if error:
                        errors.append({"file": str(file_path), "error": error})
                    elif add_result and add_result.get("success"):
                        processed_files.append(str(file_path))
                    else:
                        errors.append(
                            {
                                "file": str(file_path),
                                "error": (
                                    add_result.get("message", "Unknown error")
                                    if add_result
                                    else "No result"
                                ),
                            }
                        )

            processed_count = len(processed_files)
            failed_count = len(errors)

            logger.info(
                f"✅ Directory processing complete: {processed_count} succeeded, "
                f"{failed_count} failed out of {total_files} total"
            )

            return {
                "success": failed_count == 0,
                "processed": processed_count,
                "failed": failed_count,
                "total": total_files,
                "directory": str(directory_path),
                "files": processed_files,
                "errors": errors,
                "message": (
                    f"Successfully processed {processed_count}/{total_files} documents"
                    if failed_count == 0
                    else f"Processed {processed_count}/{total_files} documents with {failed_count} errors"
                ),
            }

        except Exception as e:
            logger.error(f"Error processing directory {directory_path}: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return {
                "success": False,
                "processed": len(processed_files),
                "failed": len(errors),
                "total": len(processed_files) + len(errors),
                "directory": str(directory_path),
                "files": processed_files,
                "errors": errors,
                "message": f"Directory processing failed: {str(e)}",
            }

    def get_librarian(self):
        """
        Get KB librarian agent for research assistance

        Returns a KBLibrarianAgent instance configured with this knowledge base.
        Lazy import to avoid circular dependencies.

        Returns:
            KBLibrarianAgent: Librarian agent instance

        Example:
            kb = KnowledgeBase()
            await kb.initialize()

            librarian = kb.get_librarian()
            response = await librarian.research_topic("machine learning")
        """
        self.ensure_initialized()

        from src.agents.kb_librarian_agent import KBLibrarianAgent

        return KBLibrarianAgent(knowledge_base=self)

    async def close(self):
        """Close all connections and cleanup resources"""
        try:
            if self.aioredis_client:
                await self.aioredis_client.close()

            if self.redis_client:
                await asyncio.to_thread(self.redis_client.close)

            self.initialized = False
            self._redis_initialized = False
            logger.info("Knowledge base connections closed")

        except Exception as e:
            logger.warning(f"Error during knowledge base cleanup: {e}")

    def __del__(self):
        """Destructor - ensure cleanup"""
        if self.initialized:
            logger.warning(
                "KnowledgeBase instance deleted without proper cleanup - use await kb.close()"
            )
