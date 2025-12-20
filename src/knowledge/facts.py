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
            await asyncio.to_thread(
                self.redis_client.set, unique_key_name, fact_id
            )

    async def _vectorize_fact_in_chromadb(
        self, fact_id: str, content: str, metadata: Dict[str, Any]
    ) -> None:
        """
        Vectorize and store fact in ChromaDB vector store.

        Issue #281: Extracted helper for ChromaDB vectorization.

        Args:
            fact_id: Fact identifier
            content: Fact content text
            metadata: Fact metadata dict
        """
        if not self.vector_store:
            return

        # Import sanitization utility
        from src.knowledge.utils import (
            sanitize_metadata_for_chromadb as _sanitize_metadata_for_chromadb,
        )

        # Sanitize metadata for ChromaDB
        sanitized_metadata = _sanitize_metadata_for_chromadb(metadata)

        # Create Document for LlamaIndex
        doc = Document(
            text=content, doc_id=fact_id, metadata=sanitized_metadata
        )

        # Add to vector store
        await asyncio.to_thread(self.vector_store.add, [doc])

        logger.info("Vectorized fact %s in ChromaDB", fact_id)

    async def store_fact(
        self, content: str, metadata: Dict[str, Any] = None, fact_id: str = None
    ) -> Dict[str, Any]:
        """
        Store a new fact in Redis and vectorize it in ChromaDB.

        Issue #281: Refactored from 113 lines to use extracted helper methods.

        Args:
            content: Fact content text
            metadata: Optional metadata dict
            fact_id: Optional custom fact ID

        Returns:
            Dict with status and fact_id
        """
        self.ensure_initialized()

        if not content or not content.strip():
            return {"status": "error", "message": "Empty content provided"}

        try:
            # Generate fact ID if not provided
            if not fact_id:
                fact_id = str(uuid.uuid4())

            # Prepare metadata
            if metadata is None:
                metadata = {}

            # Add system metadata
            metadata["fact_id"] = fact_id
            metadata["timestamp"] = datetime.now().isoformat()
            metadata["embedding_model"] = self.embedding_model_name

            # Issue #281: uses helper for duplicate checking
            duplicate_result = await self._check_for_duplicates(content, metadata)
            if duplicate_result:
                return duplicate_result

            # Issue #281: uses helper for Redis storage
            await self._store_fact_in_redis(fact_id, content, metadata)

            # Issue #281: uses helper for ChromaDB vectorization
            await self._vectorize_fact_in_chromadb(fact_id, content, metadata)

            # Issue #379: Increment stats counters in parallel (Issue #71)
            await asyncio.gather(
                self._increment_stat("total_facts"),
                self._increment_stat("total_vectors"),
            )

            return {"status": "success", "fact_id": fact_id, "action": "created"}

        except Exception as e:
            logger.error("Failed to store fact: %s", e)
            import traceback

            logger.error(traceback.format_exc())
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
            return {"status": "success", "message": "Fact vectorized successfully"}

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
        fact_id = key.split(":")[-1] if isinstance(key, str) else key.decode("utf-8").split(":")[-1]

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
        """Re-vectorize fact after content update (Issue #398: extracted)."""
        from src.knowledge.utils import sanitize_metadata_for_chromadb as _sanitize

        sanitized_metadata = _sanitize(current_metadata)
        sanitized_metadata["fact_id"] = fact_id
        await asyncio.to_thread(self.vector_store.delete, fact_id)
        doc = Document(text=content, doc_id=fact_id, metadata=sanitized_metadata)
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
                self.redis_client.hset, fact_key, mapping={
                    "content": decoded["content"],
                    "metadata": json.dumps(current_metadata),
                    "timestamp": decoded.get("timestamp", ""),
                }
            )

            if content is not None and self.vector_store:
                await self._revectorize_fact(fact_id, decoded["content"], current_metadata)

            return {"status": "success", "fact_id": fact_id, "action": "updated"}

        except Exception as e:
            logger.error("Failed to update fact %s: %s", fact_id, e)
            return {"status": "error", "message": str(e)}

    async def delete_fact(self, fact_id: str) -> dict:
        """
        Delete a fact from Redis and ChromaDB.

        Args:
            fact_id: ID of the fact to delete

        Returns:
            Dict with status
        """
        self.ensure_initialized()

        try:
            fact_key = "fact:%s" % fact_id

            # Check if fact exists
            exists = await asyncio.to_thread(self.redis_client.exists, fact_key)
            if not exists:
                return {"status": "error", "message": "Fact not found"}

            # Delete from Redis
            await asyncio.to_thread(self.redis_client.delete, fact_key)

            # Delete from ChromaDB
            if self.vector_store:
                try:
                    await asyncio.to_thread(self.vector_store.delete, fact_id)
                except Exception as e:
                    logger.warning("Could not delete vector for fact %s: %s", fact_id, e)

            # Issue #379: Decrement stats counters in parallel (Issue #71)
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
