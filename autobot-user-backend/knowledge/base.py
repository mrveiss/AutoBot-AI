# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Core Module

Contains the core KnowledgeBaseCore class with initialization, configuration,
and connection management functionality.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import aioredis
import redis
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.storage.storage_context import StorageContext
from llama_index.embeddings.ollama import OllamaEmbedding as LlamaIndexOllamaEmbedding
from llama_index.llms.ollama import Ollama as LlamaIndexOllamaLLM
from llama_index.vector_stores.chroma import ChromaVectorStore

from config import UnifiedConfigManager
from utils.chromadb_client import get_chromadb_client as create_chromadb_client
from utils.chromadb_client import wrap_collection_async
from autobot_shared.error_boundaries import error_boundary, get_error_boundary_manager
from utils.knowledge_base_timeouts import kb_timeouts

if TYPE_CHECKING:
    pass

# Create singleton config instance
config = UnifiedConfigManager()

logger = logging.getLogger(__name__)


def _extract_embedding_model_from_metadata(
    metadata_json: bytes | str | None,
) -> str | None:
    """Extract embedding model from JSON metadata (Issue #315: extracted).

    Args:
        metadata_json: JSON string or bytes containing metadata

    Returns:
        Embedding model name if found, None otherwise
    """
    if not metadata_json:
        return None

    try:
        if isinstance(metadata_json, bytes):
            metadata_json = metadata_json.decode("utf-8")
        metadata = json.loads(metadata_json)
        return metadata.get("embedding_model")
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return None


class KnowledgeBaseCore:
    """
    Core knowledge base functionality including initialization,
    configuration, and connection management.

    This class provides:
    - Async initialization with proper locking
    - Redis connection management (sync and async)
    - ChromaDB vector store initialization
    - LlamaIndex configuration with Ollama
    - V1 compatibility methods
    """

    def _init_redis_config(self) -> None:
        """Initialize Redis configuration (Issue #398: extracted)."""
        self.redis_host = config.get("redis.host")
        self.redis_port = config.get("redis.port")
        self.redis_password = config.get("redis.password")
        self.redis_db = 1  # Default for knowledge base (historical compatibility)
        self.redis_index_name = config.get(
            "redis.indexes.knowledge_base", "llama_index"
        )

    def _init_chromadb_config(self) -> None:
        """Initialize ChromaDB configuration (Issue #398: extracted)."""
        self.chromadb_path = config.get("memory.chromadb.path", "data/chromadb")
        self.chromadb_collection = config.get(
            "memory.chromadb.collection_name", "autobot_memory"
        )
        # Issue #72: HNSW parameters optimized for 545K+ vectors
        self.hnsw_space = config.get("memory.chromadb.hnsw.space", "cosine")
        self.hnsw_construction_ef = config.get(
            "memory.chromadb.hnsw.construction_ef", 300
        )
        self.hnsw_search_ef = config.get("memory.chromadb.hnsw.search_ef", 100)
        self.hnsw_m = config.get("memory.chromadb.hnsw.M", 32)

    def _init_connection_vars(self) -> None:
        """Initialize connection and state variables (Issue #398: extracted)."""
        self.redis_client: Optional[redis.Redis] = None
        self.aioredis_client: Optional[aioredis.Redis] = None
        self.vector_store: Optional[ChromaVectorStore] = None
        self.vector_index: Optional[VectorStoreIndex] = None
        self._async_chroma_collection = None
        self.llama_index_configured = False
        self.embedding_model_name: Optional[str] = None
        self.embedding_dimensions: Optional[int] = None
        self._redis_initialized = False
        self._stats_key = "kb:stats"

    def __init__(self):
        """Initialize instance variables only (Issue #398: refactored)."""
        # Call super().__init__() to ensure mixin __init__ methods are called
        # This is critical for SearchMixin to initialize _query_processor
        super().__init__()

        self.initialized = False
        self.initialization_lock = asyncio.Lock()
        self.error_manager = get_error_boundary_manager()

        self._init_redis_config()
        self._init_chromadb_config()
        self._init_connection_vars()

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

                # Verify vector store was actually initialized
                if not self.vector_store:
                    logger.error(
                        "Vector store initialization failed - self.vector_store is None"
                    )
                    raise RuntimeError("Vector store failed to initialize")

                # Step 4: Initialize stats counters (Issue #71 - O(1) stats)
                # Note: This will be called from StatsMixin when it's composed
                # For now, we'll assume it's handled by the composed class

                self.initialized = True
                self._redis_initialized = True  # V1 compatibility flag
                logger.info("Knowledge base initialization completed successfully")
                return True

            except Exception as e:
                logger.error("Knowledge base initialization failed: %s", e)
                await self._cleanup_on_failure()
                return False

    async def ainit(self) -> bool:
        """Alias for initialize() - backward compatibility with existing scripts."""
        return await self.initialize()

    def _configure_llm_provider(
        self, provider: str, model: str, endpoint: str, timeout: float, ssot_config
    ) -> None:
        """Configure LLM provider for LlamaIndex (Issue #665: extracted helper).

        Args:
            provider: Provider name (ollama, openai, anthropic)
            model: Model name to use
            endpoint: Provider endpoint URL
            timeout: Request timeout in seconds
            ssot_config: SSOT configuration object
        """
        if provider == "ollama":
            Settings.llm = LlamaIndexOllamaLLM(
                model=model,
                request_timeout=timeout,
                base_url=endpoint,
            )
        elif provider == "openai":
            from llama_index.llms.openai import OpenAI as LlamaIndexOpenAI

            Settings.llm = LlamaIndexOpenAI(
                model=model,
                api_key=ssot_config.llm.openai_api_key,
                timeout=timeout,
            )
        elif provider == "anthropic":
            from llama_index.llms.anthropic import Anthropic as LlamaIndexAnthropic

            Settings.llm = LlamaIndexAnthropic(
                model=model,
                api_key=ssot_config.llm.anthropic_api_key,
                timeout=timeout,
            )
        else:
            raise ValueError(f"Unsupported LlamaIndex LLM provider: {provider}")

    def _configure_embedding_provider(
        self, provider: str, model_name: str, endpoint: str, ssot_config
    ) -> int:
        """Configure embedding provider for LlamaIndex (Issue #665: extracted helper).

        Args:
            provider: Provider name (ollama, openai)
            model_name: Embedding model name
            endpoint: Provider endpoint URL
            ssot_config: SSOT configuration object

        Returns:
            int: Embedding dimensions for the configured provider
        """
        if provider == "ollama":
            Settings.embed_model = LlamaIndexOllamaEmbedding(
                model_name=model_name,
                base_url=endpoint,
                ollama_additional_kwargs={"num_ctx": 2048},
            )
            return 768  # nomic-embed-text dimensions
        elif provider == "openai":
            from llama_index.embeddings.openai import OpenAIEmbedding

            Settings.embed_model = OpenAIEmbedding(
                model=model_name,
                api_key=ssot_config.llm.openai_api_key,
            )
            # OpenAI text-embedding-3-small: 1536, text-embedding-3-large: 3072
            return 1536
        else:
            raise ValueError(f"Unsupported LlamaIndex embedding provider: {provider}")

    async def _resolve_embedding_model_name(self, ssot_config) -> str:
        """Resolve embedding model name from stored or config. Issue #620.

        Checks for a stored embedding model first (for consistency with
        existing data), then falls back to config setting.

        Args:
            ssot_config: SSOT configuration object

        Returns:
            Resolved embedding model name
        """
        stored_model = await self._detect_stored_embedding_model()
        if stored_model:
            logger.info(
                "Using stored embedding model for consistency: %s", stored_model
            )
            return stored_model

        embed_model_name = ssot_config.llm.embedding_model
        logger.info("Using embedding model from config: %s", embed_model_name)
        return embed_model_name

    async def _configure_llama_index(self):
        """Configure LlamaIndex with explicit SSOT settings.

        Uses AUTOBOT_LLAMAINDEX_* environment variables for RAG/vectorization.
        No fallbacks - settings must be explicitly configured.
        Issue #665: Refactored to use extracted helper methods.
        """
        from autobot_shared.ssot_config import config as ssot_config

        llm_provider = ssot_config.llm.llamaindex_llm_provider.lower()
        llm_endpoint = ssot_config.llm.llamaindex_llm_endpoint
        llm_model = ssot_config.llm.llamaindex_llm_model
        embed_provider = ssot_config.llm.llamaindex_embedding_provider.lower()
        embed_endpoint = ssot_config.llm.llamaindex_embedding_endpoint

        logger.info(
            "Configuring LlamaIndex: llm=%s@%s, embed_provider=%s@%s",
            llm_model,
            llm_provider,
            embed_provider,
            embed_endpoint,
        )

        self._configure_llm_provider(
            llm_provider, llm_model, llm_endpoint, kb_timeouts.llm_default, ssot_config
        )

        embed_model_name = await self._resolve_embedding_model_name(ssot_config)

        self.embedding_dimensions = self._configure_embedding_provider(
            embed_provider, embed_model_name, embed_endpoint, ssot_config
        )

        self.embedding_model_name = embed_model_name
        self.llama_index_configured = True

        logger.info(
            "LlamaIndex configured: llm=%s@%s, embed=%s@%s",
            llm_model,
            llm_provider,
            embed_model_name,
            embed_provider,
        )

    async def _init_redis_connections(self):
        """Initialize Redis connections using canonical utility"""
        try:
            # Use canonical Redis utility following CLAUDE.md "🔴 REDIS CLIENT USAGE" policy
            from autobot_shared.redis_client import get_redis_client

            # Get sync Redis client for knowledge base operations
            # Note: Uses DB 1 (knowledge) - canonical utility handles connection pooling
            self.redis_client = get_redis_client(database="knowledge")
            if self.redis_client is None:
                raise Exception("Redis client initialization returned None")

            # Test sync connection
            await asyncio.to_thread(self.redis_client.ping)
            logger.info(
                "Knowledge Base Redis sync client connected (database %d)",
                self.redis_db,
            )

            # Get async Redis client using pool manager
            self.aioredis_client = await get_redis_client(
                async_client=True, database="knowledge"
            )

            # Test async connection
            await self.aioredis_client.ping()
            logger.info("Knowledge Base async Redis client connected successfully")

        except Exception as e:
            logger.error("Failed to initialize Redis connections: %s", e)
            raise

    def _build_hnsw_metadata(self) -> dict:
        """Build HNSW metadata for ChromaDB collection (Issue #398: extracted)."""
        return {
            "hnsw:space": self.hnsw_space,
            "hnsw:construction_ef": self.hnsw_construction_ef,
            "hnsw:search_ef": self.hnsw_search_ef,
            "hnsw:M": self.hnsw_m,
        }

    async def _create_chroma_collection(self, chroma_client, hnsw_metadata: dict):
        """Create ChromaDB collection with HNSW parameters (Issue #398: extracted)."""
        logger.info(
            "Creating ChromaDB collection with HNSW params: "
            "space=%s, construction_ef=%d, search_ef=%d, M=%d",
            self.hnsw_space,
            self.hnsw_construction_ef,
            self.hnsw_search_ef,
            self.hnsw_m,
        )

        chroma_collection = await asyncio.to_thread(
            chroma_client.get_or_create_collection,
            name=self.chromadb_collection,
            metadata=hnsw_metadata,
        )

        self._async_chroma_collection = wrap_collection_async(chroma_collection)
        self.vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

        logger.info(
            "ChromaDB vector store initialized: collection='%s'",
            self.chromadb_collection,
        )

        collection_count = await asyncio.to_thread(chroma_collection.count)
        logger.info("ChromaDB collection contains %d vectors", collection_count)

    async def _init_vector_store(self):
        """Initialize LlamaIndex vector store with ChromaDB (Issue #398: refactored)."""
        try:
            chroma_path = Path(self.chromadb_path)
            logger.info("Initializing ChromaDB at path: %s", chroma_path)

            chroma_client = create_chromadb_client(
                db_path=str(chroma_path), allow_reset=False, anonymized_telemetry=False
            )

            hnsw_metadata = self._build_hnsw_metadata()
            await self._create_chroma_collection(chroma_client, hnsw_metadata)

            logger.info(
                "Skipping eager vector index creation - will create on first query"
            )

        except Exception as e:
            logger.error("Failed to initialize ChromaDB vector store: %s", e)
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
            logger.error("Failed to create initial vector index: %s", e)
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
            logger.warning("Error during cleanup: %s", e)

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
            logger.error("Redis ping failed: %s", e)
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
            logger.error("Error scanning Redis keys: %s", e)
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

            logger.debug("Scanned %d keys matching pattern '%s'", len(keys), pattern)
            return keys

        except redis.RedisError as e:
            logger.error("Redis error scanning keys with pattern '%s': %s", pattern, e)
            return []
        except Exception as e:
            logger.exception("Unexpected error scanning Redis keys: %s", e)
            return []

    def _count_facts(self) -> int:
        """Count stored facts in Redis"""
        try:
            fact_keys = self._scan_redis_keys("fact:*")
            return len(fact_keys)
        except Exception as e:
            logger.error("Error counting facts: %s", e)
            return 0

    async def _detect_stored_embedding_model(self) -> Optional[str]:
        """Detect which embedding model was used for existing data.
        Issue #315: Refactored to use helper for reduced nesting.
        """
        if not self.aioredis_client:
            return None

        try:
            # Look for model metadata in existing facts
            async for key in self.aioredis_client.scan_iter(match="fact:*", count=10):
                metadata_json = await self.aioredis_client.hget(key, "metadata")
                model = _extract_embedding_model_from_metadata(metadata_json)
                if model:
                    return model
        except Exception as e:
            logger.debug("Could not detect stored embedding model: %s", e)

        return None

    async def close(self):
        """Close all connections and cleanup resources"""
        try:
            logger.info("Closing knowledge base connections...")

            if self.aioredis_client:
                await self.aioredis_client.close()
                self.aioredis_client = None

            if self.redis_client:
                await asyncio.to_thread(self.redis_client.close)
                self.redis_client = None

            self.vector_store = None
            self.vector_index = None
            self.initialized = False
            self._redis_initialized = False

            logger.info("Knowledge base connections closed successfully")

        except Exception as e:
            logger.error("Error closing knowledge base connections: %s", e)

    def __del__(self):
        """Destructor to ensure cleanup"""
        # Only log, don't perform async operations in __del__
        if self.initialized:
            logger.debug(
                "KnowledgeBase instance deleted while still initialized - "
                "consider calling await close() explicitly"
            )
