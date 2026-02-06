# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Facts Management Module

Contains the FactsMixin class for CRUD operations on facts including
store, retrieve, update, delete, and vectorization.
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from llama_index.core import Document

if TYPE_CHECKING:
    import aioredis
    import redis
    from llama_index.core import VectorStoreIndex
    from llama_index.vector_stores.chroma import ChromaVectorStore

logger = logging.getLogger(__name__)


# =============================================================================
# NPU-ACCELERATED EMBEDDING GENERATION (Issue #165)
# =============================================================================
# Cached state to avoid repeated imports and availability checks
_npu_client_cache: Optional[Any] = None
_npu_available_cache: Optional[bool] = None
_npu_cache_timestamp: float = 0.0
_NPU_CACHE_TTL: float = 30.0  # Cache availability for 30 seconds

# Metrics counters for observability
_npu_embedding_count: int = 0
_fallback_embedding_count: int = 0

# Bounded concurrency for fallback to prevent overwhelming Ollama
_FALLBACK_MAX_CONCURRENT: int = 5

# Warmup state tracking
_npu_warmup_complete: bool = False
_npu_warmup_time_ms: float = 0.0


def _init_warmup_result() -> Dict[str, Any]:
    """Issue #665: Extracted from warmup_npu_connection to reduce function length.

    Initialize the warmup result dictionary with default values.

    Returns:
        Dict with default warmup status values
    """
    return {
        "status": "skipped",
        "npu_available": False,
        "warmup_time_ms": 0.0,
        "message": "",
    }


def _update_warmup_cache(client: Any, warmup_time: float) -> None:
    """Issue #665: Extracted from warmup_npu_connection to reduce function length."""
    global _npu_warmup_complete, _npu_warmup_time_ms
    global _npu_client_cache, _npu_available_cache, _npu_cache_timestamp
    import time

    _npu_warmup_time_ms = warmup_time
    _npu_warmup_complete = True
    _npu_client_cache = client
    _npu_available_cache = True
    _npu_cache_timestamp = time.time()


async def _build_warmup_success_result(
    embedding: List[float], warmup_time: float, client: Any
) -> Dict[str, Any]:
    """Issue #665: Extracted from warmup_npu_connection to reduce function length."""
    result = {
        "status": "success",
        "npu_available": True,
        "warmup_time_ms": warmup_time,
        "embedding_dimensions": len(embedding),
        "message": f"NPU connection warmed up in {warmup_time:.1f}ms",
    }
    try:
        device_info = await client.get_device_info()
        if device_info:
            result.update(
                device=device_info.device_name,
                is_npu=device_info.is_npu,
                is_gpu=device_info.is_gpu,
            )
    except Exception:
        pass  # nosec B110 - Non-critical device info, intentional no-op
    logger.info(
        "NPU warmup complete: %d dimensions in %.1fms", len(embedding), warmup_time
    )
    return result


async def warmup_npu_connection() -> Dict[str, Any]:
    """Warm up the NPU worker connection by performing a test embedding.

    Issue #165: Called during backend startup (Phase 2) to eliminate
    first-request latency. Pre-initializes the HTTP connection pool
    and ensures the NPU worker's embedding model is ready.

    Returns:
        Dict with warmup status and timing information
    """
    import time

    start_time = time.time()
    result = _init_warmup_result()

    try:
        from backend.services.npu_client import get_npu_client

        client = get_npu_client()
        if not await client.is_available(force_check=True):
            result.update(
                status="npu_unavailable",
                message="NPU worker not available, will use fallback",
            )
            logger.info("NPU warmup: Worker not available")
            return result

        embedding = await client.generate_embedding(
            "NPU warmup test embedding for connection initialization"
        )
        warmup_time = (time.time() - start_time) * 1000
        _update_warmup_cache(client, warmup_time)

        if embedding and len(embedding) > 0:
            result = await _build_warmup_success_result(embedding, warmup_time, client)
        else:
            result.update(
                status="empty_embedding",
                message="NPU returned empty embedding during warmup",
            )
            logger.warning("NPU warmup returned empty embedding")
    except Exception as e:
        result.update(
            status="error",
            warmup_time_ms=(time.time() - start_time) * 1000,
            message=f"NPU warmup failed: {e}",
        )
        logger.warning("NPU warmup failed: %s", e)

    return result


def get_npu_warmup_status() -> Dict[str, Any]:
    """
    Get NPU warmup status for diagnostics.

    Returns:
        Dict with warmup completion status and timing
    """
    return {
        "warmup_complete": _npu_warmup_complete,
        "warmup_time_ms": _npu_warmup_time_ms,
        "cache_valid": _npu_available_cache is not None,
        "npu_available": _npu_available_cache,
    }


async def _get_npu_client_cached() -> tuple:
    """
    Get cached NPU client and availability status.

    Issue #165: Caches client instance and availability check to reduce
    overhead on repeated embedding calls.

    Returns:
        Tuple of (client, is_available)
    """
    global _npu_client_cache, _npu_available_cache, _npu_cache_timestamp

    import time

    current_time = time.time()

    # Check if cache is still valid
    if (
        _npu_client_cache is not None
        and _npu_available_cache is not None
        and (current_time - _npu_cache_timestamp) < _NPU_CACHE_TTL
    ):
        return _npu_client_cache, _npu_available_cache

    # Refresh cache
    try:
        from backend.services.npu_client import get_npu_client

        _npu_client_cache = get_npu_client()
        _npu_available_cache = await _npu_client_cache.is_available()
        _npu_cache_timestamp = current_time
        return _npu_client_cache, _npu_available_cache
    except Exception as e:
        logger.debug("Failed to get NPU client: %s", e)
        _npu_available_cache = False
        _npu_cache_timestamp = current_time
        return None, False


def get_embedding_metrics() -> Dict[str, int]:
    """
    Get metrics on NPU vs fallback embedding usage.

    Returns:
        Dict with npu_count and fallback_count
    """
    return {
        "npu_count": _npu_embedding_count,
        "fallback_count": _fallback_embedding_count,
    }


async def _generate_embedding_with_npu_fallback(text: str) -> List[float]:
    """
    Generate embedding using NPU worker with fallback to LlamaIndex.

    Issue #165: Uses NPU worker (172.16.168.20:8082) for hardware-accelerated
    embedding generation. Falls back to LlamaIndex's embed_model if NPU
    is unavailable.

    Optimizations:
    - Caches NPU client and availability to reduce overhead
    - Tracks metrics for observability

    Args:
        text: Text content to embed

    Returns:
        Embedding vector as list of floats
    """
    global _npu_embedding_count, _fallback_embedding_count

    client, is_available = await _get_npu_client_cached()

    if is_available and client:
        try:
            embedding = await client.generate_embedding(text)
            if embedding:
                _npu_embedding_count += 1
                logger.debug("Generated embedding via NPU worker")
                return embedding
            logger.warning("NPU worker returned empty embedding, falling back")
        except Exception as e:
            logger.debug("NPU embedding failed, falling back: %s", e)

    # Fallback to LlamaIndex embed_model
    from llama_index.core import Settings

    embedding = await asyncio.to_thread(Settings.embed_model.get_text_embedding, text)
    _fallback_embedding_count += 1
    logger.debug("Generated embedding via LlamaIndex fallback")
    return embedding


async def _try_npu_batch_embeddings(
    texts: List[str], client: Any
) -> Optional[List[List[float]]]:
    """Try to generate batch embeddings via NPU worker. Issue #620.

    Args:
        texts: List of text contents to embed
        client: NPU client instance

    Returns:
        List of embeddings if successful, None otherwise
    """
    global _npu_embedding_count

    try:
        result = await client.generate_embeddings(texts)
        if result and len(result.embeddings) == len(texts):
            _npu_embedding_count += len(texts)
            logger.info(
                "Generated %d embeddings via NPU worker in %.2fms",
                len(texts),
                result.processing_time_ms,
            )
            return result.embeddings
        logger.warning("NPU batch returned incomplete results, falling back")
    except Exception as e:
        logger.debug("NPU batch failed, falling back: %s", e)
    return None


async def _generate_embeddings_fallback(texts: List[str]) -> List[List[float]]:
    """Generate embeddings via LlamaIndex fallback. Issue #620.

    Args:
        texts: List of text contents to embed

    Returns:
        List of embedding vectors
    """
    global _fallback_embedding_count
    from llama_index.core import Settings

    semaphore = asyncio.Semaphore(_FALLBACK_MAX_CONCURRENT)

    async def embed_one(text: str) -> List[float]:
        async with semaphore:
            return await asyncio.to_thread(
                Settings.embed_model.get_text_embedding, text
            )

    embeddings = await asyncio.gather(*[embed_one(t) for t in texts])
    _fallback_embedding_count += len(texts)
    logger.debug("Generated %d embeddings via LlamaIndex fallback", len(texts))
    return list(embeddings)


async def _generate_embeddings_batch_with_npu_fallback(
    texts: List[str],
) -> List[List[float]]:
    """Generate batch embeddings with NPU worker and fallback. Issue #620.

    Args:
        texts: List of text contents to embed

    Returns:
        List of embedding vectors
    """
    if not texts:
        return []

    client, is_available = await _get_npu_client_cached()

    if is_available and client:
        embeddings = await _try_npu_batch_embeddings(texts, client)
        if embeddings:
            return embeddings

    return await _generate_embeddings_fallback(texts)


def _decode_redis_hash(fact_data: Dict[bytes, bytes]) -> Dict[str, Any]:
    """Decode Redis hash bytes to strings and parse metadata (Issue #315: extracted).

    Args:
        fact_data: Raw Redis hash data with bytes keys/values

    Returns:
        Decoded dict with parsed metadata
    """
    decoded = {}
    for key, value in fact_data.items():
        k = key.decode("utf-8") if isinstance(key, bytes) else key
        v = value.decode("utf-8") if isinstance(value, bytes) else value
        decoded[k] = v

    # Parse metadata JSON if present
    if "metadata" in decoded:
        try:
            decoded["_parsed_metadata"] = json.loads(decoded["metadata"])
        except json.JSONDecodeError:
            decoded["_parsed_metadata"] = {}
    else:
        decoded["_parsed_metadata"] = {}

    return decoded


class FactsMixin:
    """
    Facts management mixin for knowledge base.

    Provides CRUD operations for individual facts:
    - Store new facts with vectorization
    - Retrieve facts by ID
    - Update existing facts
    - Delete facts
    - Get all facts with pagination
    - Vectorize existing unvectorized facts

    Key Features:
    - Duplicate detection via unique keys
    - Atomic counter updates (Issue #71)
    - ChromaDB vector storage
    - Metadata sanitization for ChromaDB compatibility
    """

    # Type hints for attributes from base class
    redis_client: "redis.Redis"
    aioredis_client: "aioredis.Redis"
    vector_store: "ChromaVectorStore"
    vector_index: "VectorStoreIndex"
    initialized: bool
    embedding_model_name: str

    async def _find_fact_by_unique_key(
        self, unique_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find an existing fact by unique key (fast Redis SET lookup).
        Issue #315: Refactored to use helper for reduced nesting.

        Args:
            unique_key: The unique key to search for (e.g., "machine:os:command:section")

        Returns:
            Dict with fact info if found, None otherwise
        """
        try:
            # Check Redis SET for unique key mapping
            unique_key_name = "unique_key:man_page:%s" % unique_key
            fact_id = await asyncio.to_thread(self.redis_client.get, unique_key_name)

            if not fact_id:
                return None

            # Decode bytes if necessary
            if isinstance(fact_id, bytes):
                fact_id = fact_id.decode("utf-8")

            # Get the actual fact data
            fact_key = "fact:%s" % fact_id
            fact_data = await asyncio.to_thread(self.redis_client.hgetall, fact_key)

            if not fact_data:
                return None

            # Use helper for decoding (Issue #315: extracted)
            decoded_data = _decode_redis_hash(fact_data)

            return {
                "fact_id": fact_id,
                "content": decoded_data.get("content", ""),
                "metadata": decoded_data.get("_parsed_metadata", {}),
            }

        except Exception as e:
            logger.debug("Error finding fact by unique key: %s", e)

        return None

    async def _find_existing_fact(
        self, content: str, metadata: Dict[str, Any]
    ) -> Optional[str]:
        """
        Check if a fact with identical content and metadata already exists.

        Args:
            content: Fact content
            metadata: Fact metadata

        Returns:
            Existing fact_id if found, None otherwise
        """
        try:
            # Create content hash for deduplication
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

            # Check if hash exists in Redis
            hash_key = "content_hash:%s" % content_hash
            existing_id = await asyncio.to_thread(self.redis_client.get, hash_key)

            if existing_id:
                if isinstance(existing_id, bytes):
                    return existing_id.decode("utf-8")
                return existing_id

        except Exception as e:
            logger.debug("Error checking for existing fact: %s", e)

        return None

    async def _check_for_duplicates(
        self, content: str, metadata: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Check for duplicate facts by unique_key or content hash.

        Issue #281: Extracted helper for duplicate detection.

        Args:
            content: Fact content text
            metadata: Fact metadata dict

        Returns:
            Duplicate result dict if found, None otherwise
        """
        # Check for duplicates using unique_key if provided
        if "unique_key" in metadata:
            existing = await self._find_fact_by_unique_key(metadata["unique_key"])
            if existing:
                logger.info(
                    "Duplicate detected via unique_key: %s", metadata["unique_key"]
                )
                return {
                    "status": "duplicate",
                    "fact_id": existing["fact_id"],
                    "message": "Fact already exists with this unique key",
                }

        # Check for content duplicates
        existing_id = await self._find_existing_fact(content, metadata)
        if existing_id:
            logger.info("Duplicate content detected: %s", existing_id)
            return {
                "status": "duplicate",
                "fact_id": existing_id,
                "message": "Fact with identical content already exists",
            }

        return None

    async def _store_fact_in_redis(
        self, fact_id: str, content: str, metadata: Dict[str, Any]
    ) -> None:
        """
        Store fact data in Redis with hash mappings.

        Issue #281: Extracted helper for Redis storage operations.
        Issue #547: Added session-fact relationship tracking for orphan cleanup.

        Args:
            fact_id: Fact identifier
            content: Fact content text
            metadata: Fact metadata dict
        """
        # Store in Redis
        fact_key = "fact:%s" % fact_id
        await asyncio.to_thread(
            self.redis_client.hset,
            fact_key,
            mapping={
                "content": content,
                "metadata": json.dumps(metadata),
                "timestamp": datetime.now().isoformat(),
            },
        )

        # Store content hash for deduplication
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        await asyncio.to_thread(
            self.redis_client.set, "content_hash:%s" % content_hash, fact_id
        )

        # Store unique_key mapping if provided
        if "unique_key" in metadata:
            unique_key_name = "unique_key:man_page:%s" % metadata["unique_key"]
            await asyncio.to_thread(self.redis_client.set, unique_key_name, fact_id)

        # Issue #547: Track session-fact relationship for orphan cleanup
        source_session_id = metadata.get("source_session_id")
        if source_session_id:
            await self._track_session_fact_relationship(source_session_id, fact_id)

    async def _vectorize_fact_in_chromadb(
        self, fact_id: str, content: str, metadata: Dict[str, Any]
    ) -> None:
        """
        Vectorize and store fact in ChromaDB vector store.

        Issue #281: Extracted helper for ChromaDB vectorization.
        Issue #165: Uses NPU worker for hardware-accelerated embedding generation.

        Args:
            fact_id: Fact identifier
            content: Fact content text
            metadata: Fact metadata dict
        """
        if not self.vector_store:
            return

        # Import sanitization utility
        from knowledge.utils import (
            sanitize_metadata_for_chromadb as _sanitize_metadata_for_chromadb,
        )

        # Sanitize metadata for ChromaDB
        sanitized_metadata = _sanitize_metadata_for_chromadb(metadata)

        # Issue #165: Generate embedding using NPU worker with fallback
        # ChromaVectorStore.add() expects nodes with embeddings already set
        embedding = await _generate_embedding_with_npu_fallback(content)

        # Create Document for LlamaIndex with embedding
        doc = Document(text=content, doc_id=fact_id, metadata=sanitized_metadata)
        doc.embedding = embedding

        # Add to vector store
        await asyncio.to_thread(self.vector_store.add, [doc])

        logger.info("Vectorized fact %s in ChromaDB", fact_id)

    def _prepare_fact_metadata(
        self, fact_id: str, metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Prepare metadata with system fields for new fact (Issue #398: extracted)."""
        if metadata is None:
            metadata = {}
        metadata["fact_id"] = fact_id
        metadata["timestamp"] = datetime.now().isoformat()
        metadata["embedding_model"] = self.embedding_model_name
        return metadata

    async def _store_and_vectorize_fact(
        self, fact_id: str, content: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Store fact in Redis, vectorize, and update stats (Issue #398: extracted)."""
        await self._store_fact_in_redis(fact_id, content, metadata)
        await self._vectorize_fact_in_chromadb(fact_id, content, metadata)
        await asyncio.gather(
            self._increment_stat("total_facts"),
            self._increment_stat("total_vectors"),
        )
        return {"status": "success", "fact_id": fact_id, "action": "created"}

    async def store_fact(
        self, content: str, metadata: Dict[str, Any] = None, fact_id: str = None
    ) -> Dict[str, Any]:
        """Store a new fact in Redis and vectorize it (Issue #398: refactored)."""
        self.ensure_initialized()

        if not content or not content.strip():
            return {"status": "error", "message": "Empty content provided"}

        try:
            fact_id = fact_id or str(uuid.uuid4())
            metadata = self._prepare_fact_metadata(fact_id, metadata)

            duplicate_result = await self._check_for_duplicates(content, metadata)
            if duplicate_result:
                return duplicate_result

            return await self._store_and_vectorize_fact(fact_id, content, metadata)

        except Exception as e:
            logger.error("Failed to store fact: %s", e)
            return {"status": "error", "message": str(e)}

    async def _get_fact_for_vectorization(
        self, fact_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get and decode fact data for vectorization (Issue #398: extracted)."""
        fact_key = "fact:%s" % fact_id
        fact_data = await asyncio.to_thread(self.redis_client.hgetall, fact_key)

        if not fact_data:
            return None

        decoded = _decode_redis_hash(fact_data)
        content = decoded.get("content", "")
        if not content:
            return {"error": "Fact has no content"}

        metadata = decoded.get("_parsed_metadata", {})
        metadata["fact_id"] = fact_id

        return {"content": content, "metadata": metadata}

    async def vectorize_existing_fact(self, fact_id: str) -> Dict[str, Any]:
        """Vectorize an existing fact (Issue #398: refactored)."""
        self.ensure_initialized()

        try:
            fact_info = await self._get_fact_for_vectorization(fact_id)

            if fact_info is None:
                return {"status": "error", "message": "Fact not found"}
            if "error" in fact_info:
                return {"status": "error", "message": fact_info["error"]}

            if not self.vector_store:
                return {"status": "error", "message": "Vector store not available"}

            await self._vectorize_fact_in_chromadb(
                fact_id, fact_info["content"], fact_info["metadata"]
            )

            logger.info("Vectorized existing fact %s", fact_id)
            return {
                "status": "success",
                "message": "Fact vectorized successfully",
                "vector_indexed": True,
                "fact_id": fact_id,
            }

        except Exception as e:
            logger.error("Failed to vectorize fact %s: %s", fact_id, e)
            return {"status": "error", "message": str(e)}

    def get_fact(self, fact_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single fact by ID (synchronous).

        Args:
            fact_id: Fact ID to retrieve

        Returns:
            Dict with fact data or None if not found
        """
        try:
            fact_key = "fact:%s" % fact_id
            fact_data = self.redis_client.hgetall(fact_key)

            if not fact_data:
                return None

            # Decode data
            decoded = {}
            for key, value in fact_data.items():
                k = key.decode("utf-8") if isinstance(key, bytes) else key
                v = value.decode("utf-8") if isinstance(value, bytes) else value
                decoded[k] = v

            # Parse metadata
            metadata = {}
            if "metadata" in decoded:
                try:
                    metadata = json.loads(decoded["metadata"])
                except json.JSONDecodeError:
                    pass

            return {
                "fact_id": fact_id,
                "content": decoded.get("content", ""),
                "metadata": metadata,
                "timestamp": decoded.get("timestamp", ""),
            }

        except Exception as e:
            logger.error("Error retrieving fact %s: %s", fact_id, e)
            return None

    def _process_fact_data(
        self,
        key: str,
        fact_data: Dict[bytes, bytes],
        collection: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Process raw Redis fact data into structured dict (Issue #315: extracted helper).

        Args:
            key: Redis key for the fact
            fact_data: Raw Redis hash data
            collection: Optional collection filter

        Returns:
            Processed fact dict or None if filtered out
        """
        if not fact_data:
            return None

        # Extract fact_id from key
        fact_id = (
            key.split(":")[-1]
            if isinstance(key, str)
            else key.decode("utf-8").split(":")[-1]
        )

        # Decode data using helper
        decoded = _decode_redis_hash(fact_data)

        # Apply collection filter if specified
        metadata = decoded.get("_parsed_metadata", {})
        if collection and metadata.get("collection") != collection:
            return None

        return {
            "fact_id": fact_id,
            "content": decoded.get("content", ""),
            "metadata": metadata,
            "timestamp": decoded.get("timestamp", ""),
        }

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
                return []

            # Apply offset and limit
            if offset > 0:
                fact_keys = fact_keys[offset:]
            if limit is not None:
                fact_keys = fact_keys[:limit]

            # Batch fetch facts
            facts = []
            pipeline = self.aioredis_client.pipeline()
            for key in fact_keys:
                pipeline.hgetall(key)
            facts_data = await pipeline.execute()

            for key, fact_data in zip(fact_keys, facts_data):
                fact = self._process_fact_data(key, fact_data, collection)
                if fact:
                    facts.append(fact)

            return facts

        except Exception as e:
            logger.error("Error retrieving all facts: %s", e)
            return []

    def _decode_fact_data(self, fact_data: Dict) -> Dict[str, str]:
        """Decode Redis fact data from bytes (Issue #398: extracted)."""
        decoded = {}
        for key, value in fact_data.items():
            k = key.decode("utf-8") if isinstance(key, bytes) else key
            v = value.decode("utf-8") if isinstance(value, bytes) else value
            decoded[k] = v
        return decoded

    async def _revectorize_fact(
        self, fact_id: str, content: str, current_metadata: Dict
    ) -> None:
        """Re-vectorize fact after content update (Issue #398: extracted).

        Issue #165: Uses NPU worker for hardware-accelerated embedding generation.
        """
        from knowledge.utils import sanitize_metadata_for_chromadb as _sanitize

        sanitized_metadata = _sanitize(current_metadata)
        sanitized_metadata["fact_id"] = fact_id
        await asyncio.to_thread(self.vector_store.delete, fact_id)

        # Issue #165: Generate embedding using NPU worker with fallback
        embedding = await _generate_embedding_with_npu_fallback(content)
        doc = Document(text=content, doc_id=fact_id, metadata=sanitized_metadata)
        doc.embedding = embedding

        await asyncio.to_thread(self.vector_store.add, [doc])
        logger.info("Re-vectorized updated fact %s", fact_id)

    async def update_fact(
        self, fact_id: str, content: str = None, metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Update an existing fact (Issue #398: refactored)."""
        self.ensure_initialized()

        try:
            fact_key = "fact:%s" % fact_id
            exists = await asyncio.to_thread(self.redis_client.exists, fact_key)
            if not exists:
                return {"status": "error", "message": "Fact not found"}

            fact_data = await asyncio.to_thread(self.redis_client.hgetall, fact_key)
            decoded = self._decode_fact_data(fact_data)

            current_metadata = {}
            if "metadata" in decoded:
                try:
                    current_metadata = json.loads(decoded["metadata"])
                except json.JSONDecodeError:
                    pass

            if content is not None:
                decoded["content"] = content
            if metadata is not None:
                current_metadata.update(metadata)
            current_metadata["updated_at"] = datetime.now().isoformat()

            await asyncio.to_thread(
                self.redis_client.hset,
                fact_key,
                mapping={
                    "content": decoded["content"],
                    "metadata": json.dumps(current_metadata),
                    "timestamp": decoded.get("timestamp", ""),
                },
            )

            if content is not None and self.vector_store:
                await self._revectorize_fact(
                    fact_id, decoded["content"], current_metadata
                )

            return {"status": "success", "fact_id": fact_id, "action": "updated"}

        except Exception as e:
            logger.error("Failed to update fact %s: %s", fact_id, e)
            return {"status": "error", "message": str(e)}

    async def _cleanup_fact_mappings(
        self, fact_id: str, content: str, metadata: Dict[str, Any]
    ) -> None:
        """Clean up Redis mappings for a deleted fact. Issue #620.

        Removes content hash, unique key, and session tracking mappings
        to prevent memory leaks.

        Args:
            fact_id: ID of the fact being deleted
            content: Fact content for hash cleanup
            metadata: Fact metadata for unique key cleanup
        """
        if content:
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
            await asyncio.to_thread(
                self.redis_client.delete, "content_hash:%s" % content_hash
            )

        unique_key = metadata.get("unique_key")
        if unique_key:
            await asyncio.to_thread(
                self.redis_client.delete, "unique_key:man_page:%s" % unique_key
            )

        await asyncio.to_thread(
            self.redis_client.delete, "fact:origin:session:%s" % fact_id
        )

    async def _delete_fact_from_vector_store(self, fact_id: str) -> None:
        """Delete fact from ChromaDB vector store. Issue #620.

        Args:
            fact_id: ID of the fact to delete from vector store
        """
        if self.vector_store:
            try:
                await asyncio.to_thread(self.vector_store.delete, fact_id)
            except Exception as e:
                logger.warning("Could not delete vector for fact %s: %s", fact_id, e)

    async def delete_fact(self, fact_id: str) -> dict:
        """Delete a fact from Redis and ChromaDB. Issue #620.

        Args:
            fact_id: ID of the fact to delete

        Returns:
            Dict with status
        """
        self.ensure_initialized()

        try:
            fact_key = "fact:%s" % fact_id
            fact_data = await asyncio.to_thread(self.redis_client.hgetall, fact_key)
            if not fact_data:
                return {"status": "error", "message": "Fact not found"}

            decoded = _decode_redis_hash(fact_data)
            content = decoded.get("content", "")
            metadata = decoded.get("_parsed_metadata", {})

            await asyncio.to_thread(self.redis_client.delete, fact_key)
            await self._cleanup_fact_mappings(fact_id, content, metadata)
            await self._delete_fact_from_vector_store(fact_id)

            await asyncio.gather(
                self._decrement_stat("total_facts"),
                self._decrement_stat("total_vectors"),
            )

            logger.info("Deleted fact %s", fact_id)
            return {"status": "success", "fact_id": fact_id, "action": "deleted"}

        except Exception as e:
            logger.error("Failed to delete fact %s: %s", fact_id, e)
            return {"status": "error", "message": str(e)}

    # Method references needed from other mixins
    async def _scan_redis_keys_async(self, pattern: str):
        """Scan Redis keys - implemented in base class"""
        raise NotImplementedError("Should be implemented in composed class")

    async def _increment_stat(self, field: str, amount: int = 1):
        """Increment stats counter - implemented in stats mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    async def _decrement_stat(self, field: str, amount: int = 1):
        """Decrement stats counter - implemented in stats mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    def ensure_initialized(self):
        """Ensure initialized - implemented in base class"""
        raise NotImplementedError("Should be implemented in composed class")

    # =========================================================================
    # SESSION-FACT RELATIONSHIP TRACKING (Issue #547)
    # =========================================================================

    async def _track_session_fact_relationship(
        self, session_id: str, fact_id: str
    ) -> None:
        """
        Track bidirectional relationship between session and fact for orphan cleanup.

        Issue #547: Creates Redis indexes to enable cleanup when session is deleted.

        Redis Keys Created:
        - session:facts:{session_id} -> Set of fact IDs created in this session
        - fact:origin:session:{fact_id} -> String of session ID that created this fact

        Args:
            session_id: Chat session ID
            fact_id: Fact ID
        """
        try:
            # Add fact to session's fact set
            await asyncio.to_thread(
                self.redis_client.sadd, "session:facts:%s" % session_id, fact_id
            )

            # Store reverse lookup (fact -> session)
            await asyncio.to_thread(
                self.redis_client.set, "fact:origin:session:%s" % fact_id, session_id
            )

            logger.debug(
                "Tracked session-fact relationship: session=%s, fact=%s",
                session_id,
                fact_id,
            )

        except Exception as e:
            logger.warning(
                "Failed to track session-fact relationship: session=%s, fact=%s, error=%s",
                session_id,
                fact_id,
                e,
            )

    async def get_facts_by_session(self, session_id: str) -> List[str]:
        """
        Get all fact IDs created during a specific session.

        Issue #547: Used for orphan cleanup when session is deleted.

        Args:
            session_id: Chat session ID

        Returns:
            List of fact IDs created in this session
        """
        try:
            fact_ids = await asyncio.to_thread(
                self.redis_client.smembers, "session:facts:%s" % session_id
            )

            # Decode bytes to strings
            return [
                fid.decode("utf-8") if isinstance(fid, bytes) else fid
                for fid in (fact_ids or [])
            ]

        except Exception as e:
            logger.error("Failed to get facts by session %s: %s", session_id, e)
            return []

    async def get_session_for_fact(self, fact_id: str) -> Optional[str]:
        """
        Get the session ID that created a specific fact.

        Issue #547: Reverse lookup for fact -> session relationship.

        Args:
            fact_id: Fact ID

        Returns:
            Session ID or None if not tracked
        """
        try:
            session_id = await asyncio.to_thread(
                self.redis_client.get, "fact:origin:session:%s" % fact_id
            )

            if session_id:
                return (
                    session_id.decode("utf-8")
                    if isinstance(session_id, bytes)
                    else session_id
                )
            return None

        except Exception as e:
            logger.error("Failed to get session for fact %s: %s", fact_id, e)
            return None

    async def _batch_check_important_facts(self, fact_ids: List[str]) -> set:
        """
        Batch check which facts are marked as important/preserve.

        Issue #547 code review: Optimizes performance by using Redis pipeline
        instead of individual blocking get_fact() calls.

        Args:
            fact_ids: List of fact IDs to check

        Returns:
            Set of fact IDs that should be preserved
        """
        if not fact_ids:
            return set()

        try:
            # Use pipeline for batch fetch
            pipeline = self.aioredis_client.pipeline()
            for fact_id in fact_ids:
                pipeline.hgetall("fact:%s" % fact_id)

            facts_data = await pipeline.execute()

            important_fact_ids = set()
            for fact_id, fact_data in zip(fact_ids, facts_data):
                if not fact_data:
                    continue
                decoded = _decode_redis_hash(fact_data)
                metadata = decoded.get("_parsed_metadata", {})
                if metadata.get("important") or metadata.get("preserve"):
                    important_fact_ids.add(fact_id)

            return important_fact_ids

        except Exception as e:
            logger.warning("Failed to batch check important facts: %s", e)
            return set()

    async def _delete_single_fact_for_session(
        self,
        fact_id: str,
        session_id: str,
        important_ids: set,
        preserve_important: bool,
        result: Dict[str, Any],
    ) -> None:
        """Delete a single fact during session cleanup (Issue #665: extracted helper).

        Args:
            fact_id: Fact ID to process
            session_id: Session ID being cleaned up
            important_ids: Set of fact IDs to preserve
            preserve_important: Whether to preserve important facts
            result: Result dict to update with counts/errors
        """
        try:
            # Check if fact should be preserved
            if preserve_important and fact_id in important_ids:
                logger.debug(
                    "Preserving important fact %s from session %s", fact_id, session_id
                )
                result["preserved_count"] += 1
                return

            # Delete the fact
            delete_result = await self.delete_fact(fact_id)

            if delete_result.get("status") == "success":
                result["deleted_count"] += 1
            else:
                result["errors"].append(
                    {
                        "fact_id": fact_id,
                        "error": delete_result.get("message", "Unknown error"),
                    }
                )

        except Exception as e:
            result["errors"].append({"fact_id": fact_id, "error": str(e)})

    async def _process_session_facts_deletion(
        self,
        session_id: str,
        fact_ids: List[str],
        preserve_important: bool,
        result: Dict[str, Any],
    ) -> None:
        """Process deletion of all facts in a session. Issue #620.

        Args:
            session_id: Session ID being cleaned up
            fact_ids: List of fact IDs to process
            preserve_important: Whether to preserve important facts
            result: Result dict to update with counts
        """
        important_ids = set()
        if preserve_important:
            important_ids = await self._batch_check_important_facts(fact_ids)

        for fact_id in fact_ids:
            await self._delete_single_fact_for_session(
                fact_id, session_id, important_ids, preserve_important, result
            )

        await self._cleanup_session_tracking(session_id, fact_ids)

    async def delete_facts_by_session(
        self, session_id: str, preserve_important: bool = True
    ) -> Dict[str, Any]:
        """Delete all facts created during a specific session. Issue #620.

        Args:
            session_id: Chat session ID to cleanup
            preserve_important: If True, preserve facts marked as 'important'

        Returns:
            Dict with deletion statistics
        """
        self.ensure_initialized()

        result: Dict[str, Any] = {
            "deleted_count": 0,
            "preserved_count": 0,
            "errors": [],
        }

        try:
            fact_ids = await self.get_facts_by_session(session_id)
            if not fact_ids:
                logger.info("No facts found for session %s", session_id)
                return result

            logger.info(
                "Cleaning up %d facts for session %s (preserve_important=%s)",
                len(fact_ids),
                session_id,
                preserve_important,
            )

            await self._process_session_facts_deletion(
                session_id, fact_ids, preserve_important, result
            )

            logger.info(
                "Session %s cleanup complete: deleted=%d, preserved=%d, errors=%d",
                session_id,
                result["deleted_count"],
                result["preserved_count"],
                len(result["errors"]),
            )
            return result

        except Exception as e:
            logger.error("Failed to delete facts for session %s: %s", session_id, e)
            result["errors"].append({"session_id": session_id, "error": str(e)})
            return result

    async def _cleanup_session_tracking(
        self, session_id: str, fact_ids: List[str]
    ) -> None:
        """
        Clean up session tracking keys after facts deletion.

        Issue #547: Remove session-fact relationship tracking data.

        Args:
            session_id: Session ID being cleaned up
            fact_ids: List of fact IDs to clean up
        """
        try:
            # Delete the session's fact set
            await asyncio.to_thread(
                self.redis_client.delete, "session:facts:%s" % session_id
            )

            # Delete reverse lookup keys for each fact
            for fact_id in fact_ids:
                await asyncio.to_thread(
                    self.redis_client.delete, "fact:origin:session:%s" % fact_id
                )

            logger.debug("Cleaned up tracking for session %s", session_id)

        except Exception as e:
            logger.warning(
                "Failed to cleanup session tracking for %s: %s", session_id, e
            )
