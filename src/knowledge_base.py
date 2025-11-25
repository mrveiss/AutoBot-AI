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
import re
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aioredis
import redis  # Needed for type hints (Optional[redis.Redis])
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.storage.storage_context import StorageContext
from llama_index.embeddings.ollama import OllamaEmbedding as LlamaIndexOllamaEmbedding
from llama_index.llms.ollama import Ollama as LlamaIndexOllamaLLM
from llama_index.vector_stores.chroma import ChromaVectorStore

from src.constants.network_constants import NetworkConstants
from src.unified_config_manager import UnifiedConfigManager
from src.utils.chromadb_client import get_chromadb_client as create_chromadb_client
from src.utils.error_boundaries import (
    error_boundary,
    get_error_boundary_manager,
)
from src.utils.knowledge_base_timeouts import kb_timeouts

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
            ),
            ollama_port = config.get(
                "infrastructure.ports.ollama", str(NetworkConstants.OLLAMA_PORT)
            ),
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
                    ),
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
                f"ChromaDB direct search returned {len(results)} unique documents "
                f"(deduplicated) for query: {query[:50]}..."
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

    @error_boundary(component="knowledge_base", function="enhanced_search")
    async def enhanced_search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        tags_match_any: bool = False,
        mode: str = "hybrid",
        enable_reranking: bool = False,
        min_score: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Enhanced search with tag filtering, hybrid mode, and query preprocessing.

        Issue #78: Search Quality Improvements

        Args:
            query: Search query (will be preprocessed)
            limit: Maximum results to return
            offset: Pagination offset
            category: Optional category filter
            tags: Optional list of tags to filter by
            tags_match_any: If True, match ANY tag. If False, match ALL tags.
            mode: Search mode ("semantic", "keyword", "hybrid")
            enable_reranking: Enable cross-encoder reranking for better relevance
            min_score: Minimum similarity score threshold (0.0-1.0)

        Returns:
            Dict with results, total_count, and search metadata
        """
        self.ensure_initialized()

        if not query.strip():
            return {
                "success": False,
                "results": [],
                "total_count": 0,
                "message": "Empty query",
            }

        try:
            # Step 1: Query preprocessing
            processed_query = self._preprocess_query(query)

            # Step 2: Get candidate fact IDs from tags if specified
            tag_filtered_ids: Optional[Set[str]] = None
            if tags:
                tag_result = await self._get_fact_ids_by_tags(
                    tags, match_all=not tags_match_any
                )
                if tag_result["success"]:
                    tag_filtered_ids = tag_result["fact_ids"]
                    if not tag_filtered_ids:
                        # No facts match the tag filter
                        return {
                            "success": True,
                            "results": [],
                            "total_count": 0,
                            "query_processed": processed_query,
                            "message": "No facts match the specified tags",
                        }

            # Step 3: Perform search based on mode
            # Request more results than needed to allow for filtering
            fetch_multiplier = 3 if tags or min_score > 0 else 1.5
            fetch_limit = min(int((limit + offset) * fetch_multiplier), 500)

            if mode == "keyword":
                # Keyword-only search (uses Redis text search if available)
                results = await self._keyword_search(
                    processed_query, fetch_limit, category
                )
            elif mode == "semantic":
                # Semantic-only search (existing ChromaDB search)
                results = await self.search(
                    processed_query,
                    top_k=fetch_limit,
                    filters={"category": category} if category else None,
                    mode="vector",
                )
            else:
                # Hybrid mode: combine semantic and keyword results
                results = await self._hybrid_search(
                    processed_query, fetch_limit, category
                )

            # Step 4: Filter by tags if specified
            if tag_filtered_ids is not None:
                results = [
                    r for r in results
                    if r.get("metadata", {}).get("fact_id") in tag_filtered_ids
                ]

            # Step 5: Apply minimum score threshold
            if min_score > 0:
                results = [r for r in results if r.get("score", 0) >= min_score]

            # Step 6: Optional reranking with cross-encoder
            if enable_reranking and results:
                results = await self._rerank_results(processed_query, results)

            # Step 7: Get total before pagination
            total_count = len(results)

            # Step 8: Apply pagination
            paginated_results = results[offset:offset + limit]

            return {
                "success": True,
                "results": paginated_results,
                "total_count": total_count,
                "query_processed": processed_query,
                "mode": mode,
                "tags_applied": tags if tags else [],
                "min_score_applied": min_score,
                "reranking_applied": enable_reranking,
            }

        except Exception as e:
            logger.error(f"Enhanced search failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "results": [],
                "total_count": 0,
                "error": str(e),
            }

    def _preprocess_query(self, query: str) -> str:
        """
        Preprocess search query for better results.

        Issue #78: Query preprocessing for search quality.

        Preprocessing steps:
        1. Normalize whitespace
        2. Remove redundant punctuation
        3. Expand common abbreviations
        4. Preserve quoted phrases

        Args:
            query: Raw user query

        Returns:
            Preprocessed query string
        """
        import re

        # Normalize whitespace
        processed = " ".join(query.split())

        # Common abbreviations expansion (security/sysadmin context)
        abbreviations = {
            r"\bdir\b": "directory",
            r"\bcmd\b": "command",
            r"\bpwd\b": "password",
            r"\bauth\b": "authentication",
            r"\bperm\b": "permission",
            r"\bperms\b": "permissions",
            r"\bconfig\b": "configuration",
            r"\benv\b": "environment",
            r"\bvar\b": "variable",
            r"\bvars\b": "variables",
            r"\bproc\b": "process",
            r"\bsvc\b": "service",
            r"\bpkg\b": "package",
            r"\brepo\b": "repository",
            r"\binfo\b": "information",
            r"\bdoc\b": "documentation",
            r"\bdocs\b": "documentation",
        }

        # Only expand if not in quotes
        if '"' not in processed and "'" not in processed:
            for abbr, expansion in abbreviations.items():
                processed = re.sub(abbr, expansion, processed, flags=re.IGNORECASE)

        return processed.strip()

    async def _get_fact_ids_by_tags(
        self, tags: List[str], match_all: bool = True
    ) -> Dict[str, Any]:
        """
        Get fact IDs matching specified tags.

        Args:
            tags: List of tags to match
            match_all: If True, facts must have ALL tags

        Returns:
            Dict with success status and set of fact_ids
        """
        try:
            if not self.aioredis_client:
                return {"success": False, "fact_ids": set(), "message": "Redis not initialized"}

            # Normalize tags
            normalized_tags = [t.lower().strip() for t in tags if t.strip()]
            if not normalized_tags:
                return {"success": False, "fact_ids": set(), "message": "No valid tags"}

            # Get fact IDs for each tag using pipeline
            pipeline = self.aioredis_client.pipeline()
            for tag in normalized_tags:
                pipeline.smembers(f"tag:{tag}")
            tag_results = await pipeline.execute()

            # Convert to sets
            tag_fact_sets = []
            for fact_ids in tag_results:
                if fact_ids:
                    decoded_ids = {
                        fid.decode("utf-8") if isinstance(fid, bytes) else fid
                        for fid in fact_ids
                    }
                    tag_fact_sets.append(decoded_ids)
                else:
                    tag_fact_sets.append(set())

            # Calculate matching IDs
            if not tag_fact_sets:
                return {"success": True, "fact_ids": set()}

            if match_all:
                # Intersection - must have ALL tags
                result_ids = tag_fact_sets[0]
                for fact_set in tag_fact_sets[1:]:
                    result_ids = result_ids.intersection(fact_set)
            else:
                # Union - ANY tag matches
                result_ids = set()
                for fact_set in tag_fact_sets:
                    result_ids = result_ids.union(fact_set)

            return {"success": True, "fact_ids": result_ids}

        except Exception as e:
            logger.error(f"Failed to get fact IDs by tags: {e}")
            return {"success": False, "fact_ids": set(), "error": str(e)}

    async def _keyword_search(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform keyword-based search using Redis.

        Args:
            query: Search query
            limit: Maximum results
            category: Optional category filter

        Returns:
            List of search results
        """
        try:
            if not self.aioredis_client:
                return []

            # Tokenize query
            query_terms = set(query.lower().split())
            if not query_terms:
                return []

            # SCAN through facts and score by term matches
            # This is a simple implementation; could be optimized with Redis Search module
            results = []
            cursor = b"0"
            scanned = 0
            max_scan = 10000  # Safety limit

            while scanned < max_scan:
                cursor, keys = await self.aioredis_client.scan(
                    cursor=cursor, match="fact:*", count=100
                )
                scanned += len(keys)

                if keys:
                    # Batch fetch
                    pipeline = self.aioredis_client.pipeline()
                    for key in keys:
                        pipeline.hgetall(key)
                    facts_data = await pipeline.execute()

                    for key, fact_data in zip(keys, facts_data):
                        if not fact_data:
                            continue

                        # Decode
                        decoded = {}
                        for k, v in fact_data.items():
                            dk = k.decode("utf-8") if isinstance(k, bytes) else k
                            dv = v.decode("utf-8") if isinstance(v, bytes) else v
                            decoded[dk] = dv

                        # Category filter
                        if category:
                            try:
                                metadata = json.loads(decoded.get("metadata", "{}"))
                                if metadata.get("category") != category:
                                    continue
                            except json.JSONDecodeError:
                                continue

                        # Score by term matches in content
                        content = decoded.get("content", "").lower()
                        matches = sum(1 for term in query_terms if term in content)

                        if matches > 0:
                            # Calculate score based on match ratio
                            score = matches / len(query_terms)
                            fact_id = key.decode(
                                "utf-8").replace("fact:", "") if isinstance(key, bytes) else key.replace("fact:", "")

                            try:
                                metadata = json.loads(decoded.get("metadata", "{}"))
                            except json.JSONDecodeError:
                                metadata = {}

                            results.append({
                                "content": decoded.get("content", ""),
                                "score": score,
                                "metadata": {**metadata, "fact_id": fact_id},
                                "node_id": fact_id,
                                "doc_id": fact_id,
                            })

                if cursor == b"0":
                    break

            # Sort by score and limit
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []

    async def _hybrid_search(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining semantic and keyword results.

        Uses reciprocal rank fusion (RRF) to combine rankings.

        Args:
            query: Search query
            limit: Maximum results
            category: Optional category filter

        Returns:
            List of merged and re-ranked results
        """
        try:
            # Run both searches in parallel
            semantic_task = asyncio.create_task(
                self.search(
                    query,
                    top_k=limit,
                    filters={"category": category} if category else None,
                    mode="vector",
                )
            )
            keyword_task = asyncio.create_task(
                self._keyword_search(query, limit, category)
            )

            semantic_results, keyword_results = await asyncio.gather(
                semantic_task, keyword_task
            )

            # Reciprocal Rank Fusion (RRF)
            # Score = sum(1 / (k + rank)) across all rankings
            # Using k=60 as standard RRF constant
            k = 60
            rrf_scores: Dict[str, float] = {}
            result_map: Dict[str, Dict[str, Any]] = {}

            # Process semantic results
            for rank, result in enumerate(semantic_results):
                fact_id = result.get("metadata", {}).get(
                    "fact_id") or result.get("node_id", f"sem_{rank}")
                rrf_scores[fact_id] = rrf_scores.get(fact_id, 0) + (1 / (k + rank + 1))
                if fact_id not in result_map:
                    result_map[fact_id] = result

            # Process keyword results
            for rank, result in enumerate(keyword_results):
                fact_id = result.get("metadata", {}).get(
                    "fact_id") or result.get("node_id", f"kw_{rank}")
                rrf_scores[fact_id] = rrf_scores.get(fact_id, 0) + (1 / (k + rank + 1))
                if fact_id not in result_map:
                    result_map[fact_id] = result

            # Sort by RRF score
            sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

            # Build final results with normalized scores
            max_rrf = max(rrf_scores.values()) if rrf_scores else 1
            results = []
            for fact_id in sorted_ids[:limit]:
                result = result_map[fact_id].copy()
                # Normalize RRF score to 0-1 range
                result["score"] = rrf_scores[fact_id] / max_rrf
                result["rrf_score"] = rrf_scores[fact_id]
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            # Fallback to semantic search
            return await self.search(query, top_k=limit, mode="vector")

    async def _rerank_results(
        self, query: str, results: List[Dict[str, Any]], top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank results using cross-encoder for improved relevance.

        Args:
            query: Original search query
            results: Initial search results
            top_k: Maximum results to return after reranking

        Returns:
            Reranked results
        """
        try:
            # Check if cross-encoder is available
            try:
                from sentence_transformers import CrossEncoder
            except ImportError:
                logger.warning("CrossEncoder not available, skipping reranking")
                return results

            if not results:
                return results

            # Use cached cross-encoder or create new one
            if not hasattr(self, "_cross_encoder") or self._cross_encoder is None:
                # Use a lightweight cross-encoder model
                self._cross_encoder = await asyncio.to_thread(
                    CrossEncoder, "cross-encoder/ms-marco-MiniLM-L-6-v2"
                )

            # Prepare pairs for scoring
            pairs = [(query, r.get("content", "")) for r in results]

            # Score all pairs
            scores = await asyncio.to_thread(self._cross_encoder.predict, pairs)

            # Attach scores and sort
            for i, result in enumerate(results):
                result["rerank_score"] = float(scores[i])

            results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

            # Update primary score to rerank score
            for result in results:
                result["original_score"] = result.get("score", 0)
                result["score"] = result.get("rerank_score", 0)

            if top_k:
                results = results[:top_k]

            return results

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return results

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
            check_duplicates: If True, check for existing facts with same
                category+title (default: True)

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
                            f"Duplicate fact detected by unique key: "
                            f"'{unique_key}', existing_fact_id={existing_fact['fact_id']}"
                        )
                        return {
                            "status": "duplicate",
                            "message": (
                                f"Fact already exists with unique key: {unique_key}"
                            ),
                            "fact_id": existing_fact["fact_id"],
                            "duplicate_o": existing_fact["fact_id"],
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
                        ),
                        created_at = await self.aioredis_client.hget(
                            fact_key, "created_at"
                        )

                        if metadata_str:
                            logger.info(
                                f"Duplicate fact detected by category+title: "
                                f"category='{category}', title='{title}', "
                                f"existing_fact_id={existing_fact_id}"
                            )
                            return {
                                "status": "duplicate",
                                "message": (
                                    "Fact already exists with same category and title"
                                ),
                                "fact_id": existing_fact_id,
                                "duplicate_o": existing_fact_id,
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
                        f"Stored category_title index: "
                        f"category_title:{category_title_key} → {fact_id}"
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
                            ),
                            vector_indexed = True
                            logger.info(
                                f"Created vector index and stored fact {fact_id}"
                            )
                        except Exception as index_error:
                            if "dimension" in str(index_error).lower():
                                logger.error(
                                    f"Vector index creation failed due to "
                                    f"dimension mismatch: {index_error}"
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
                        "message": (
                            f"Fact stored in Redis but NOT indexed for search: {error_msg}"
                        ),
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
                            "timestamp": (
                                fact_data.get(b"timestamp", b"").decode("utf-8")
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
                                    "timestamp": (
                                        fact_data.get(b"timestamp", b"").decode("utf-8")
                                    ),
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
                    ),
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
                        f"ChromaDB stats: {vector_count} vectors "
                        f"in collection '{self.chromadb_collection}'"
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
                "message": "ChromaDB index verified successfully",
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
                f"Retrieving {len(fact_keys)} facts "
                f"(total={total_facts}, offset={offset}, limit={limit})"
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
                    ),
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
                Path("report.pd"),
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
            ),
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
                    else (
                        f"Processed {processed_count}/{total_files} documents "
                        f"with {failed_count} errors"
                    )
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

    # =========================================================================
    # TAG MANAGEMENT METHODS (Issue #77)
    # =========================================================================
    #
    # Redis Schema for Tags:
    #   - fact:{fact_id} hash now includes "tags" field (JSON array)
    #   - tag:{tag_name} → SET of fact_ids that have this tag
    #   - tag:index:all → SET of all unique tag names
    #
    # This allows:
    #   - O(1) tag lookup per fact
    #   - O(1) reverse lookup: all facts with a given tag
    #   - O(1) list all tags
    # =========================================================================

    async def add_tags_to_fact(
        self, fact_id: str, tags: List[str]
    ) -> Dict[str, Any]:
        """
        Add tags to a knowledge base fact.

        Args:
            fact_id: The fact ID to add tags to
            tags: List of tags to add (will be normalized to lowercase)

        Returns:
            Dict with success status, updated tags list, and added_count
        """
        self.ensure_initialized()

        try:
            if not self.aioredis_client:
                return {
                    "success": False,
                    "message": "Redis client not initialized",
                }

            fact_key = f"fact:{fact_id}"

            # Check if fact exists
            exists = await self.aioredis_client.exists(fact_key)
            if not exists:
                return {
                    "success": False,
                    "message": f"Fact {fact_id} not found",
                }

            # Normalize tags to lowercase
            normalized_tags = [t.lower().strip() for t in tags]

            # Get existing tags with JSON size limit (Critical fix #3)
            existing_tags_json = await self.aioredis_client.hget(fact_key, "tags")
            existing_tags = []
            if existing_tags_json:
                # Decode bytes if needed
                if isinstance(existing_tags_json, bytes):
                    existing_tags_json = existing_tags_json.decode("utf-8")
                # Size limit to prevent JSON bombs
                if len(existing_tags_json) > 10000:
                    logger.warning(f"Tags JSON too large for fact {fact_id}")
                    existing_tags_json = "[]"
                try:
                    existing_tags = json.loads(existing_tags_json)
                    if not isinstance(existing_tags, list):
                        existing_tags = []
                except json.JSONDecodeError:
                    existing_tags = []

            # Calculate new tags (avoiding duplicates)
            existing_set = set(existing_tags)
            new_tags = [t for t in normalized_tags if t not in existing_set]
            updated_tags = list(existing_set.union(set(normalized_tags)))

            # ATOMIC UPDATE (Critical fix #2): Use single pipeline for all operations
            pipeline = self.aioredis_client.pipeline()
            pipeline.hset(fact_key, "tags", json.dumps(updated_tags))
            for tag in new_tags:
                # Add fact to tag's set
                pipeline.sadd(f"tag:{tag}", fact_id)
                # Add tag to global index
                pipeline.sadd("tag:index:all", tag)
            await pipeline.execute()

            logger.info(f"Added {len(new_tags)} tags to fact {fact_id}")
            logger.debug(f"Tags added: {new_tags}")

            return {
                "success": True,
                "tags": sorted(updated_tags),
                "added_count": len(new_tags),
                "message": f"Added {len(new_tags)} new tags",
            }

        except Exception as e:
            logger.error(f"Error adding tags to fact {fact_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to add tags: {str(e)}",
            }

    async def remove_tags_from_fact(
        self, fact_id: str, tags: List[str]
    ) -> Dict[str, Any]:
        """
        Remove tags from a knowledge base fact.

        Args:
            fact_id: The fact ID to remove tags from
            tags: List of tags to remove

        Returns:
            Dict with success status, remaining tags list, and removed_count
        """
        self.ensure_initialized()

        try:
            if not self.aioredis_client:
                return {
                    "success": False,
                    "message": "Redis client not initialized",
                }

            fact_key = f"fact:{fact_id}"

            # Check if fact exists
            exists = await self.aioredis_client.exists(fact_key)
            if not exists:
                return {
                    "success": False,
                    "message": f"Fact {fact_id} not found",
                }

            # Normalize tags to lowercase
            normalized_tags = set(t.lower().strip() for t in tags)

            # Get existing tags with JSON size limit (Critical fix #3)
            existing_tags_json = await self.aioredis_client.hget(fact_key, "tags")
            existing_tags = []
            if existing_tags_json:
                # Decode bytes if needed
                if isinstance(existing_tags_json, bytes):
                    existing_tags_json = existing_tags_json.decode("utf-8")
                # Size limit to prevent JSON bombs
                if len(existing_tags_json) > 10000:
                    logger.warning(f"Tags JSON too large for fact {fact_id}")
                    existing_tags_json = "[]"
                try:
                    existing_tags = json.loads(existing_tags_json)
                    if not isinstance(existing_tags, list):
                        existing_tags = []
                except json.JSONDecodeError:
                    existing_tags = []

            # Calculate which tags to remove (only those that exist)
            existing_set = set(existing_tags)
            tags_to_remove = normalized_tags.intersection(existing_set)
            remaining_tags = list(existing_set - normalized_tags)

            # ATOMIC UPDATE: Use single pipeline for fact update and index removal
            pipeline = self.aioredis_client.pipeline()
            pipeline.hset(fact_key, "tags", json.dumps(remaining_tags))
            for tag in tags_to_remove:
                # Remove fact from tag's set
                pipeline.srem(f"tag:{tag}", fact_id)
            await pipeline.execute()

            # ATOMIC CLEANUP (Critical fix #1): Use Lua script for safe tag cleanup
            # This prevents race condition where another request adds the tag
            # between SCARD check and DELETE
            cleanup_script = """
local tag_key = KEYS[1]
local index_key = KEYS[2]
local tag = ARGV[1]

if redis.call('SCARD', tag_key) == 0 then
    redis.call('DEL', tag_key)
    redis.call('SREM', index_key, tag)
    return 1
end
return 0
"""
            for tag in tags_to_remove:
                await self.aioredis_client.eval(
                    cleanup_script,
                    2,  # number of keys
                    f"tag:{tag}",
                    "tag:index:all",
                    tag
                )

            logger.info(f"Removed {len(tags_to_remove)} tags from fact {fact_id}")

            return {
                "success": True,
                "tags": sorted(remaining_tags),
                "removed_count": len(tags_to_remove),
                "message": f"Removed {len(tags_to_remove)} tags",
            }

        except Exception as e:
            logger.error(f"Error removing tags from fact {fact_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to remove tags: {str(e)}",
            }

    async def get_fact_tags(self, fact_id: str) -> Dict[str, Any]:
        """
        Get all tags for a specific fact.

        Args:
            fact_id: The fact ID to get tags for

        Returns:
            Dict with success status and tags list
        """
        self.ensure_initialized()

        try:
            if not self.aioredis_client:
                return {
                    "success": False,
                    "message": "Redis client not initialized",
                }

            fact_key = f"fact:{fact_id}"

            # Check if fact exists
            exists = await self.aioredis_client.exists(fact_key)
            if not exists:
                return {
                    "success": False,
                    "message": f"Fact {fact_id} not found",
                }

            # Get tags
            tags_json = await self.aioredis_client.hget(fact_key, "tags")
            tags = []
            if tags_json:
                try:
                    tags = json.loads(tags_json)
                except json.JSONDecodeError:
                    tags = []

            return {
                "success": True,
                "tags": sorted(tags),
            }

        except Exception as e:
            logger.error(f"Error getting tags for fact {fact_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to get tags: {str(e)}",
            }

    async def search_facts_by_tags(
        self,
        tags: List[str],
        match_all: bool = False,
        limit: int = 50,
        offset: int = 0,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for facts by tags.

        Args:
            tags: List of tags to search for
            match_all: If True, facts must have ALL tags. If False, ANY tag matches.
            limit: Maximum number of results
            offset: Pagination offset
            category: Optional category filter

        Returns:
            Dict with facts list and total_count
        """
        self.ensure_initialized()

        try:
            if not self.aioredis_client:
                return {
                    "success": False,
                    "facts": [],
                    "total_count": 0,
                    "message": "Redis client not initialized",
                }

            # Normalize tags
            normalized_tags = [t.lower().strip() for t in tags]

            # Get fact IDs for each tag using pipeline (Critical fix #4)
            pipeline = self.aioredis_client.pipeline()
            for tag in normalized_tags:
                pipeline.smembers(f"tag:{tag}")
            tag_results = await pipeline.execute()

            tag_fact_sets = []
            for fact_ids in tag_results:
                if fact_ids:
                    # Decode bytes to strings
                    decoded_ids = {
                        fid.decode("utf-8") if isinstance(fid, bytes) else fid
                        for fid in fact_ids
                    }
                    tag_fact_sets.append(decoded_ids)
                else:
                    tag_fact_sets.append(set())

            # Calculate matching fact IDs
            if not tag_fact_sets:
                matching_ids = set()
            elif match_all:
                # Intersection - facts must have ALL tags
                matching_ids = tag_fact_sets[0]
                for fact_set in tag_fact_sets[1:]:
                    matching_ids = matching_ids.intersection(fact_set)
            else:
                # Union - facts with ANY tag
                matching_ids = set()
                for fact_set in tag_fact_sets:
                    matching_ids = matching_ids.union(fact_set)

            # Convert to list and get total count BEFORE pagination (Critical fix #9)
            matching_ids_list = list(matching_ids)
            total_count = len(matching_ids_list)

            # Paginate at ID level BEFORE fetching data (performance optimization)
            paginated_ids = matching_ids_list[offset:offset + limit]

            if not paginated_ids:
                return {
                    "success": True,
                    "facts": [],
                    "total_count": total_count,
                }

            # BATCH FETCH using pipeline (Critical fix #4: ~1000x faster)
            pipeline = self.aioredis_client.pipeline()
            for fact_id in paginated_ids:
                pipeline.hgetall(f"fact:{fact_id}")
            fact_data_list = await pipeline.execute()

            # Process results
            facts = []
            for fact_id, fact_data in zip(paginated_ids, fact_data_list):
                if not fact_data:
                    continue

                # Decode fact data
                decoded_data = {}
                for k, v in fact_data.items():
                    key = k.decode("utf-8") if isinstance(k, bytes) else k
                    value = v.decode("utf-8") if isinstance(v, bytes) else v
                    decoded_data[key] = value

                # Parse metadata with size limit (Critical fix #3)
                metadata = {}
                if "metadata" in decoded_data:
                    metadata_json = decoded_data["metadata"]
                    if len(metadata_json) <= 50000:  # 50KB limit
                        try:
                            metadata = json.loads(metadata_json)
                        except json.JSONDecodeError:
                            pass

                # Apply category filter if specified
                if category and metadata.get("category") != category:
                    total_count -= 1  # Adjust count for filtered items
                    continue

                # Parse tags with size limit
                fact_tags = []
                if "tags" in decoded_data:
                    tags_json = decoded_data["tags"]
                    if len(tags_json) <= 10000:
                        try:
                            fact_tags = json.loads(tags_json)
                        except json.JSONDecodeError:
                            pass

                facts.append({
                    "fact_id": fact_id,
                    "content": decoded_data.get("content", ""),
                    "metadata": metadata,
                    "tags": fact_tags,
                    "created_at": decoded_data.get("created_at"),
                })

            return {
                "success": True,
                "facts": facts,
                "total_count": total_count,
            }

        except Exception as e:
            logger.error(f"Error searching facts by tags: {e}")
            return {
                "success": False,
                "facts": [],
                "total_count": 0,
                "message": f"Search failed: {str(e)}",
            }

    async def list_all_tags(
        self, limit: int = 100, prefix: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List all unique tags in the knowledge base with usage counts.

        Args:
            limit: Maximum number of tags to return
            prefix: Optional prefix filter

        Returns:
            Dict with tags list (name + count) and total_count
        """
        self.ensure_initialized()

        try:
            if not self.aioredis_client:
                return {
                    "success": False,
                    "tags": [],
                    "total_count": 0,
                    "message": "Redis client not initialized",
                }

            # Get all tags from global index
            all_tags = await self.aioredis_client.smembers("tag:index:all")

            if not all_tags:
                return {
                    "success": True,
                    "tags": [],
                    "total_count": 0,
                }

            # Decode and filter by prefix
            tag_names = []
            for tag in all_tags:
                name = tag.decode("utf-8") if isinstance(tag, bytes) else tag
                if prefix is None or name.startswith(prefix):
                    tag_names.append(name)

            # BATCH FETCH counts using pipeline (Critical fix #6)
            # Process in chunks to prevent memory exhaustion
            BATCH_SIZE = 100
            tags_with_counts = []

            for i in range(0, len(tag_names), BATCH_SIZE):
                batch = tag_names[i:i + BATCH_SIZE]
                pipeline = self.aioredis_client.pipeline()
                for tag_name in batch:
                    pipeline.scard(f"tag:{tag_name}")
                counts = await pipeline.execute()

                for tag_name, count in zip(batch, counts):
                    tags_with_counts.append({
                        "name": tag_name,
                        "count": count,
                    })

            # Sort by count (descending), then name (ascending)
            tags_with_counts.sort(key=lambda x: (-x["count"], x["name"]))

            total_count = len(tags_with_counts)

            # Apply limit
            limited_tags = tags_with_counts[:limit]

            return {
                "success": True,
                "tags": limited_tags,
                "total_count": total_count,
            }

        except Exception as e:
            logger.error(f"Error listing tags: {e}")
            return {
                "success": False,
                "tags": [],
                "total_count": 0,
                "message": f"Failed to list tags: {str(e)}",
            }

    async def bulk_tag_facts(
        self,
        fact_ids: List[str],
        tags: List[str],
        operation: str = "add",
    ) -> Dict[str, Any]:
        """
        Apply or remove tags from multiple facts at once.

        Args:
            fact_ids: List of fact IDs to tag
            tags: List of tags to apply/remove
            operation: 'add' or 'remove'

        Returns:
            Dict with status, processed/failed counts, and per-fact results
        """
        self.ensure_initialized()

        # Deduplicate fact_ids (Recommendation #10)
        unique_fact_ids = list(dict.fromkeys(fact_ids))  # Preserves order
        if len(unique_fact_ids) < len(fact_ids):
            logger.warning(
                f"Removed {len(fact_ids) - len(unique_fact_ids)} duplicate fact_ids"
            )

        results = []
        processed_count = 0
        failed_count = 0

        for fact_id in unique_fact_ids:
            try:
                if operation == "add":
                    result = await self.add_tags_to_fact(fact_id, tags)
                else:
                    result = await self.remove_tags_from_fact(fact_id, tags)

                if result.get("success"):
                    processed_count += 1
                    results.append({
                        "fact_id": fact_id,
                        "success": True,
                        "tags": result.get("tags", []),
                    })
                else:
                    failed_count += 1
                    results.append({
                        "fact_id": fact_id,
                        "success": False,
                        "error": result.get("message", "Unknown error"),
                    })

            except Exception as e:
                failed_count += 1
                results.append({
                    "fact_id": fact_id,
                    "success": False,
                    "error": str(e),
                })

        status = "success" if failed_count == 0 else "partial_success"
        if processed_count == 0:
            status = "failed"

        logger.info(
            f"Bulk {operation} tags: {processed_count} processed, "
            f"{failed_count} failed"
        )

        return {
            "status": status,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "results": results,
        }

    # ===== BULK OPERATIONS (Issue #79) =====

    @error_boundary(component="knowledge_base", function="export_facts")
    async def export_facts(
        self,
        format: str = "json",
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        fact_ids: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        include_metadata: bool = True,
        include_tags: bool = True,
    ) -> Dict[str, Any]:
        """
        Export facts from the knowledge base.

        Issue #79: Bulk Operations - Export functionality

        Args:
            format: Export format ("json", "csv", "markdown")
            categories: Filter by categories
            tags: Filter by tags
            fact_ids: Specific fact IDs to export
            date_from: ISO date string for date range start
            date_to: ISO date string for date range end
            include_metadata: Include metadata in export
            include_tags: Include tags in export

        Returns:
            Dict with export data and metadata
        """
        self.ensure_initialized()

        try:
            # Collect facts to export
            facts_to_export = []

            if fact_ids:
                # Export specific facts
                for fact_id in fact_ids:
                    fact_data = await self._get_fact_data(fact_id)
                    if fact_data:
                        facts_to_export.append(fact_data)
            else:
                # Scan and filter facts
                cursor = b"0"
                scanned = 0
                max_scan = 50000

                while scanned < max_scan:
                    cursor, keys = await self.aioredis_client.scan(
                        cursor=cursor, match="fact:*", count=100
                    )
                    scanned += len(keys)

                    if keys:
                        pipeline = self.aioredis_client.pipeline()
                        for key in keys:
                            pipeline.hgetall(key)
                        facts_data = await pipeline.execute()

                        for key, data in zip(keys, facts_data):
                            if not data:
                                continue

                            fact = self._decode_fact_data(key, data)
                            if fact and self._matches_filters(
                                fact, categories, tags, date_from, date_to
                            ):
                                facts_to_export.append(fact)

                    if cursor == b"0":
                        break

            # Add tags if requested
            if include_tags:
                for fact in facts_to_export:
                    fact_id = fact.get("fact_id")
                    if fact_id:
                        tags_result = await self.get_fact_tags(fact_id)
                        fact["tags"] = tags_result.get("tags", [])

            # Format output
            if format == "json":
                export_data = self._format_export_json(facts_to_export, include_metadata)
            elif format == "csv":
                export_data = self._format_export_csv(facts_to_export, include_metadata)
            elif format == "markdown":
                export_data = self._format_export_markdown(facts_to_export, include_metadata)
            else:
                return {"success": False, "error": f"Unsupported format: {format}"}

            return {
                "success": True,
                "format": format,
                "total_facts": len(facts_to_export),
                "data": export_data,
                "exported_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Export failed: {e}")
            return {"success": False, "error": str(e)}

    async def _get_fact_data(self, fact_id: str) -> Optional[Dict[str, Any]]:
        """Get fact data by ID."""
        try:
            data = await self.aioredis_client.hgetall(f"fact:{fact_id}")
            if data:
                return self._decode_fact_data(f"fact:{fact_id}".encode(), data)
            return None
        except Exception as e:
            logger.error(f"Failed to get fact {fact_id}: {e}")
            return None

    def _decode_fact_data(self, key: bytes, data: Dict) -> Dict[str, Any]:
        """Decode fact data from Redis."""
        decoded = {}
        for k, v in data.items():
            dk = k.decode("utf-8") if isinstance(k, bytes) else k
            dv = v.decode("utf-8") if isinstance(v, bytes) else v
            decoded[dk] = dv

        # Extract fact_id from key
        key_str = key.decode("utf-8") if isinstance(key, bytes) else key
        fact_id = key_str.replace("fact:", "")

        # Parse metadata
        try:
            metadata = json.loads(decoded.get("metadata", "{}"))
        except json.JSONDecodeError:
            metadata = {}

        return {
            "fact_id": fact_id,
            "content": decoded.get("content", ""),
            "created_at": decoded.get("created_at", ""),
            "updated_at": decoded.get("updated_at", ""),
            "metadata": metadata,
        }

    def _matches_filters(
        self,
        fact: Dict[str, Any],
        categories: Optional[List[str]],
        tags: Optional[List[str]],
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> bool:
        """Check if fact matches all specified filters."""
        metadata = fact.get("metadata", {})

        # Category filter
        if categories:
            fact_category = metadata.get("category", "")
            if fact_category not in categories:
                return False

        # Date filters
        created_at = fact.get("created_at", "")
        if date_from and created_at:
            if created_at < date_from:
                return False
        if date_to and created_at:
            if created_at > date_to:
                return False

        # Tag filter (requires tags to be loaded separately)
        # This is handled in the main export function after loading tags

        return True

    def _format_export_json(
        self, facts: List[Dict[str, Any]], include_metadata: bool
    ) -> str:
        """Format facts as JSON."""
        if not include_metadata:
            facts = [
                {"fact_id": f["fact_id"], "content": f["content"], "tags": f.get("tags", [])}
                for f in facts
            ]
        return json.dumps(facts, indent=2, ensure_ascii=False)

    def _format_export_csv(
        self, facts: List[Dict[str, Any]], include_metadata: bool
    ) -> str:
        """Format facts as CSV."""
        import csv
        import io

        output = io.StringIO()
        if include_metadata:
            fieldnames = ["fact_id", "content", "category", "title", "tags", "created_at"]
        else:
            fieldnames = ["fact_id", "content", "tags"]

        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for fact in facts:
            row = {
                "fact_id": fact.get("fact_id", ""),
                "content": fact.get("content", ""),
                "tags": ",".join(fact.get("tags", [])),
            }
            if include_metadata:
                metadata = fact.get("metadata", {})
                row["category"] = metadata.get("category", "")
                row["title"] = metadata.get("title", "")
                row["created_at"] = fact.get("created_at", "")
            writer.writerow(row)

        return output.getvalue()

    def _format_export_markdown(
        self, facts: List[Dict[str, Any]], include_metadata: bool
    ) -> str:
        """Format facts as Markdown."""
        lines = ["# Knowledge Base Export", ""]
        lines.append(f"Exported: {datetime.utcnow().isoformat()}")
        lines.append(f"Total facts: {len(facts)}")
        lines.append("")

        for i, fact in enumerate(facts, 1):
            metadata = fact.get("metadata", {})
            title = metadata.get("title", f"Fact {i}")
            lines.append(f"## {title}")
            lines.append("")

            if include_metadata:
                lines.append(f"**ID**: `{fact.get('fact_id', '')}`")
                lines.append(f"**Category**: {metadata.get('category', 'N/A')}")
                if fact.get("tags"):
                    lines.append(f"**Tags**: {', '.join(fact['tags'])}")
                lines.append(f"**Created**: {fact.get('created_at', 'N/A')}")
                lines.append("")

            lines.append(fact.get("content", ""))
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    @error_boundary(component="knowledge_base", function="import_facts")
    async def import_facts(
        self,
        data: str,
        format: str = "json",
        validate_only: bool = False,
        skip_duplicates: bool = True,
        overwrite_existing: bool = False,
        default_category: str = "imported",
    ) -> Dict[str, Any]:
        """
        Import facts into the knowledge base.

        Issue #79: Bulk Operations - Import functionality

        Args:
            data: Import data string
            format: Data format ("json", "csv", "markdown")
            validate_only: Only validate without importing
            skip_duplicates: Skip facts that already exist
            overwrite_existing: Overwrite existing facts with same ID
            default_category: Default category for imported facts

        Returns:
            Dict with import results
        """
        self.ensure_initialized()

        try:
            # Parse input data
            if format == "json":
                facts = self._parse_import_json(data)
            elif format == "csv":
                facts = self._parse_import_csv(data, default_category)
            else:
                return {"success": False, "error": f"Unsupported format: {format}"}

            # Validate facts
            validation_errors = []
            valid_facts = []

            for i, fact in enumerate(facts):
                errors = self._validate_import_fact(fact)
                if errors:
                    validation_errors.append({"index": i, "errors": errors})
                else:
                    valid_facts.append(fact)

            if validate_only:
                return {
                    "success": True,
                    "validation_only": True,
                    "total_facts": len(facts),
                    "valid_facts": len(valid_facts),
                    "invalid_facts": len(validation_errors),
                    "errors": validation_errors,
                }

            # Import valid facts
            imported = 0
            skipped = 0
            overwritten = 0
            import_errors = []

            for fact in valid_facts:
                try:
                    fact_id = fact.get("fact_id") or str(uuid.uuid4())

                    # Check if exists
                    exists = await self.aioredis_client.exists(f"fact:{fact_id}")

                    if exists:
                        if skip_duplicates and not overwrite_existing:
                            skipped += 1
                            continue
                        elif overwrite_existing:
                            overwritten += 1
                        else:
                            skipped += 1
                            continue

                    # Import the fact
                    metadata = fact.get("metadata", {})
                    if "category" not in metadata:
                        metadata["category"] = default_category

                    await self._store_fact(
                        fact_id=fact_id,
                        content=fact.get("content", ""),
                        metadata=metadata,
                    )

                    # Import tags if present
                    if fact.get("tags"):
                        await self.add_tags_to_fact(fact_id, fact["tags"])

                    imported += 1

                except Exception as e:
                    import_errors.append({
                        "fact_id": fact.get("fact_id", "unknown"),
                        "error": str(e)
                    })

            return {
                "success": True,
                "total_facts": len(facts),
                "imported": imported,
                "skipped": skipped,
                "overwritten": overwritten,
                "errors": import_errors,
                "validation_errors": validation_errors,
            }

        except Exception as e:
            logger.error(f"Import failed: {e}")
            return {"success": False, "error": str(e)}

    def _parse_import_json(self, data: str) -> List[Dict[str, Any]]:
        """Parse JSON import data."""
        parsed = json.loads(data)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict) and "facts" in parsed:
            return parsed["facts"]
        else:
            return [parsed]

    def _parse_import_csv(self, data: str, default_category: str) -> List[Dict[str, Any]]:
        """Parse CSV import data."""
        import csv
        import io

        reader = csv.DictReader(io.StringIO(data))
        facts = []

        for row in reader:
            fact = {
                "fact_id": row.get("fact_id", str(uuid.uuid4())),
                "content": row.get("content", ""),
                "metadata": {
                    "category": row.get("category", default_category),
                    "title": row.get("title", ""),
                },
            }
            if row.get("tags"):
                fact["tags"] = [t.strip() for t in row["tags"].split(",") if t.strip()]
            facts.append(fact)

        return facts

    def _validate_import_fact(self, fact: Dict[str, Any]) -> List[str]:
        """Validate a fact for import."""
        errors = []

        if not fact.get("content"):
            errors.append("Missing content")

        content = fact.get("content", "")
        if len(content) > 1000000:
            errors.append("Content too large (max 1MB)")

        if fact.get("fact_id"):
            if not re.match(r"^[a-zA-Z0-9_-]+$", fact["fact_id"]):
                errors.append("Invalid fact_id format")

        return errors

    async def _store_fact(
        self, fact_id: str, content: str, metadata: Dict[str, Any]
    ) -> None:
        """Store a fact in Redis."""
        now = datetime.utcnow().isoformat()
        await self.aioredis_client.hset(
            f"fact:{fact_id}",
            mapping={
                "content": content,
                "metadata": json.dumps(metadata),
                "created_at": now,
                "updated_at": now,
            },
        )

    @error_boundary(component="knowledge_base", function="find_duplicates")
    async def find_duplicates(
        self,
        similarity_threshold: float = 0.95,
        category: Optional[str] = None,
        max_comparisons: int = 10000,
    ) -> Dict[str, Any]:
        """
        Find duplicate or near-duplicate facts.

        Issue #79: Bulk Operations - Deduplication

        Args:
            similarity_threshold: Similarity threshold (0.5-1.0)
            category: Limit to specific category
            max_comparisons: Maximum comparisons to prevent timeout

        Returns:
            Dict with duplicate pairs and statistics
        """
        self.ensure_initialized()

        try:
            # Collect facts for comparison
            facts = []
            cursor = b"0"
            scanned = 0

            while scanned < 10000:
                cursor, keys = await self.aioredis_client.scan(
                    cursor=cursor, match="fact:*", count=100
                )
                scanned += len(keys)

                if keys:
                    pipeline = self.aioredis_client.pipeline()
                    for key in keys:
                        pipeline.hgetall(key)
                    facts_data = await pipeline.execute()

                    for key, data in zip(keys, facts_data):
                        if not data:
                            continue

                        fact = self._decode_fact_data(key, data)

                        # Category filter
                        if category:
                            metadata = fact.get("metadata", {})
                            if metadata.get("category") != category:
                                continue

                        facts.append(fact)

                if cursor == b"0":
                    break

            # Find duplicates using content hashing first (exact matches)
            exact_duplicates = []
            content_hashes: Dict[str, List[str]] = {}

            for fact in facts:
                content = fact.get("content", "").strip().lower()
                content_hash = hashlib.md5(content.encode()).hexdigest()

                if content_hash in content_hashes:
                    for existing_id in content_hashes[content_hash]:
                        exact_duplicates.append({
                            "fact_id_1": existing_id,
                            "fact_id_2": fact["fact_id"],
                            "similarity": 1.0,
                            "type": "exact",
                        })
                    content_hashes[content_hash].append(fact["fact_id"])
                else:
                    content_hashes[content_hash] = [fact["fact_id"]]

            # Find near-duplicates using embedding similarity (if threshold < 1.0)
            near_duplicates = []

            if similarity_threshold < 1.0 and len(facts) > 1:
                # Use vector similarity for near-duplicate detection
                comparisons = 0
                fact_embeddings = {}

                for i, fact1 in enumerate(facts):
                    if comparisons >= max_comparisons:
                        break

                    # Get or compute embedding for fact1
                    if fact1["fact_id"] not in fact_embeddings:
                        emb = await self._get_fact_embedding(fact1["fact_id"])
                        if emb:
                            fact_embeddings[fact1["fact_id"]] = emb

                    if fact1["fact_id"] not in fact_embeddings:
                        continue

                    for fact2 in facts[i + 1:]:
                        if comparisons >= max_comparisons:
                            break

                        # Skip if already found as exact duplicate
                        is_exact = any(
                            (d["fact_id_1"] == fact1["fact_id"] and d["fact_id_2"] == fact2["fact_id"]) or
                            (d["fact_id_1"] == fact2["fact_id"] and d["fact_id_2"] == fact1["fact_id"])
                            for d in exact_duplicates
                        )
                        if is_exact:
                            continue

                        # Get or compute embedding for fact2
                        if fact2["fact_id"] not in fact_embeddings:
                            emb = await self._get_fact_embedding(fact2["fact_id"])
                            if emb:
                                fact_embeddings[fact2["fact_id"]] = emb

                        if fact2["fact_id"] not in fact_embeddings:
                            continue

                        # Calculate cosine similarity
                        similarity = self._cosine_similarity(
                            fact_embeddings[fact1["fact_id"]],
                            fact_embeddings[fact2["fact_id"]]
                        )

                        if similarity >= similarity_threshold:
                            near_duplicates.append({
                                "fact_id_1": fact1["fact_id"],
                                "fact_id_2": fact2["fact_id"],
                                "similarity": round(similarity, 4),
                                "type": "near",
                            })

                        comparisons += 1

            all_duplicates = exact_duplicates + near_duplicates

            return {
                "success": True,
                "total_facts_scanned": len(facts),
                "exact_duplicates": len(exact_duplicates),
                "near_duplicates": len(near_duplicates),
                "total_duplicates": len(all_duplicates),
                "duplicates": all_duplicates,
                "similarity_threshold": similarity_threshold,
            }

        except Exception as e:
            logger.error(f"Find duplicates failed: {e}")
            return {"success": False, "error": str(e)}

    async def _get_fact_embedding(self, fact_id: str) -> Optional[List[float]]:
        """Get embedding vector for a fact."""
        try:
            # Try to get from Redis first
            vector_key = f"llama_index/vector_{fact_id}"
            vector_data = await self.aioredis_client.get(vector_key)

            if vector_data:
                return json.loads(vector_data)

            # If not cached, get content and compute embedding
            fact_data = await self._get_fact_data(fact_id)
            if not fact_data:
                return None

            content = fact_data.get("content", "")
            if not content:
                return None

            # Use embedding model
            from llama_index.core import Settings
            embedding = await asyncio.to_thread(
                Settings.embed_model.get_text_embedding, content[:2000]
            )
            return embedding

        except Exception as e:
            logger.error(f"Failed to get embedding for {fact_id}: {e}")
            return None

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    @error_boundary(component="knowledge_base", function="bulk_delete")
    async def bulk_delete(
        self, fact_ids: List[str], confirm: bool = False
    ) -> Dict[str, Any]:
        """
        Delete multiple facts at once.

        Issue #79: Bulk Operations - Bulk delete

        Args:
            fact_ids: List of fact IDs to delete
            confirm: Must be True to actually delete

        Returns:
            Dict with deletion results
        """
        self.ensure_initialized()

        if not confirm:
            return {
                "success": False,
                "error": "Confirmation required. Set confirm=True to delete.",
                "facts_to_delete": len(fact_ids),
            }

        try:
            deleted = 0
            not_found = 0
            errors = []

            for fact_id in fact_ids:
                try:
                    # Check if exists
                    exists = await self.aioredis_client.exists(f"fact:{fact_id}")
                    if not exists:
                        not_found += 1
                        continue

                    # Get tags before deletion
                    tags_result = await self.get_fact_tags(fact_id)
                    tags = tags_result.get("tags", [])

                    # Remove from tag indexes
                    if tags:
                        pipeline = self.aioredis_client.pipeline()
                        for tag in tags:
                            pipeline.srem(f"tag:{tag}", fact_id)
                        await pipeline.execute()

                    # Delete the fact
                    await self.aioredis_client.delete(f"fact:{fact_id}")
                    deleted += 1

                except Exception as e:
                    errors.append({"fact_id": fact_id, "error": str(e)})

            return {
                "success": True,
                "deleted": deleted,
                "not_found": not_found,
                "errors": errors,
            }

        except Exception as e:
            logger.error(f"Bulk delete failed: {e}")
            return {"success": False, "error": str(e)}

    @error_boundary(component="knowledge_base", function="bulk_update_category")
    async def bulk_update_category(
        self, fact_ids: List[str], new_category: str
    ) -> Dict[str, Any]:
        """
        Update category for multiple facts.

        Issue #79: Bulk Operations - Bulk category update

        Args:
            fact_ids: List of fact IDs to update
            new_category: New category to assign

        Returns:
            Dict with update results
        """
        self.ensure_initialized()

        try:
            updated = 0
            not_found = 0
            errors = []

            for fact_id in fact_ids:
                try:
                    # Get current fact data
                    fact_data = await self._get_fact_data(fact_id)
                    if not fact_data:
                        not_found += 1
                        continue

                    # Update metadata
                    metadata = fact_data.get("metadata", {})
                    metadata["category"] = new_category

                    # Store updated metadata
                    await self.aioredis_client.hset(
                        f"fact:{fact_id}",
                        "metadata",
                        json.dumps(metadata),
                    )
                    await self.aioredis_client.hset(
                        f"fact:{fact_id}",
                        "updated_at",
                        datetime.utcnow().isoformat(),
                    )

                    updated += 1

                except Exception as e:
                    errors.append({"fact_id": fact_id, "error": str(e)})

            return {
                "success": True,
                "updated": updated,
                "not_found": not_found,
                "errors": errors,
            }

        except Exception as e:
            logger.error(f"Bulk category update failed: {e}")
            return {"success": False, "error": str(e)}

    @error_boundary(component="knowledge_base", function="cleanup")
    async def cleanup(
        self,
        remove_empty: bool = True,
        remove_orphaned_tags: bool = True,
        fix_metadata: bool = True,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Clean up the knowledge base.

        Issue #79: Bulk Operations - Cleanup

        Args:
            remove_empty: Remove facts with empty content
            remove_orphaned_tags: Remove tags with no associated facts
            fix_metadata: Fix malformed metadata JSON
            dry_run: Only report issues without fixing

        Returns:
            Dict with cleanup results
        """
        self.ensure_initialized()

        try:
            issues_found = {
                "empty_facts": [],
                "orphaned_tags": [],
                "malformed_metadata": [],
            }
            fixes_applied = {
                "empty_facts_removed": 0,
                "orphaned_tags_removed": 0,
                "metadata_fixed": 0,
            }

            # Find empty facts
            if remove_empty:
                cursor = b"0"
                while True:
                    cursor, keys = await self.aioredis_client.scan(
                        cursor=cursor, match="fact:*", count=100
                    )

                    if keys:
                        pipeline = self.aioredis_client.pipeline()
                        for key in keys:
                            pipeline.hget(key, "content")
                        contents = await pipeline.execute()

                        for key, content in zip(keys, contents):
                            if not content or (
                                isinstance(content, bytes) and not content.strip()
                            ):
                                fact_id = key.decode().replace("fact:", "")
                                issues_found["empty_facts"].append(fact_id)

                                if not dry_run:
                                    await self.aioredis_client.delete(key)
                                    fixes_applied["empty_facts_removed"] += 1

                    if cursor == b"0":
                        break

            # Find orphaned tags
            if remove_orphaned_tags:
                all_tags = await self.aioredis_client.smembers("tag:index:all")
                if all_tags:
                    for tag_bytes in all_tags:
                        tag = tag_bytes.decode() if isinstance(tag_bytes, bytes) else tag_bytes
                        member_count = await self.aioredis_client.scard(f"tag:{tag}")

                        if member_count == 0:
                            issues_found["orphaned_tags"].append(tag)

                            if not dry_run:
                                await self.aioredis_client.delete(f"tag:{tag}")
                                await self.aioredis_client.srem("tag:index:all", tag)
                                fixes_applied["orphaned_tags_removed"] += 1

            # Fix malformed metadata
            if fix_metadata:
                cursor = b"0"
                while True:
                    cursor, keys = await self.aioredis_client.scan(
                        cursor=cursor, match="fact:*", count=100
                    )

                    if keys:
                        pipeline = self.aioredis_client.pipeline()
                        for key in keys:
                            pipeline.hget(key, "metadata")
                        metadata_list = await pipeline.execute()

                        for key, metadata_raw in zip(keys, metadata_list):
                            if metadata_raw:
                                try:
                                    metadata_str = (
                                        metadata_raw.decode()
                                        if isinstance(metadata_raw, bytes)
                                        else metadata_raw
                                    )
                                    json.loads(metadata_str)
                                except json.JSONDecodeError:
                                    fact_id = key.decode().replace("fact:", "")
                                    issues_found["malformed_metadata"].append(fact_id)

                                    if not dry_run:
                                        # Replace with empty metadata
                                        await self.aioredis_client.hset(
                                            key, "metadata", "{}"
                                        )
                                        fixes_applied["metadata_fixed"] += 1

                    if cursor == b"0":
                        break

            return {
                "success": True,
                "dry_run": dry_run,
                "issues_found": {
                    "empty_facts": len(issues_found["empty_facts"]),
                    "orphaned_tags": len(issues_found["orphaned_tags"]),
                    "malformed_metadata": len(issues_found["malformed_metadata"]),
                },
                "issues_details": issues_found if dry_run else {},
                "fixes_applied": fixes_applied if not dry_run else {},
            }

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return {"success": False, "error": str(e)}

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
