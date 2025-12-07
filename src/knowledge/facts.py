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
            unique_key_name = f"unique_key:man_page:{unique_key}"
            fact_id = await asyncio.to_thread(self.redis_client.get, unique_key_name)

            if not fact_id:
                return None

            # Decode bytes if necessary
            if isinstance(fact_id, bytes):
                fact_id = fact_id.decode("utf-8")

            # Get the actual fact data
            fact_key = f"fact:{fact_id}"
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
            logger.debug(f"Error finding fact by unique key: {e}")

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
            hash_key = f"content_hash:{content_hash}"
            existing_id = await asyncio.to_thread(self.redis_client.get, hash_key)

            if existing_id:
                if isinstance(existing_id, bytes):
                    return existing_id.decode("utf-8")
                return existing_id

        except Exception as e:
            logger.debug(f"Error checking for existing fact: {e}")

        return None

    async def store_fact(
        self, content: str, metadata: Dict[str, Any] = None, fact_id: str = None
    ) -> Dict[str, Any]:
        """
        Store a new fact in Redis and vectorize it in ChromaDB.

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
            # Import sanitization utility
            from src.knowledge.utils import sanitize_metadata_for_chromadb as _sanitize_metadata_for_chromadb

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

            # Check for duplicates using unique_key if provided
            if "unique_key" in metadata:
                existing = await self._find_fact_by_unique_key(metadata["unique_key"])
                if existing:
                    logger.info(
                        f"Duplicate detected via unique_key: {metadata['unique_key']}"
                    )
                    return {
                        "status": "duplicate",
                        "fact_id": existing["fact_id"],
                        "message": "Fact already exists with this unique key",
                    }

            # Check for content duplicates
            existing_id = await self._find_existing_fact(content, metadata)
            if existing_id:
                logger.info(f"Duplicate content detected: {existing_id}")
                return {
                    "status": "duplicate",
                    "fact_id": existing_id,
                    "message": "Fact with identical content already exists",
                }

            # Store in Redis
            fact_key = f"fact:{fact_id}"
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
                self.redis_client.set, f"content_hash:{content_hash}", fact_id
            )

            # Store unique_key mapping if provided
            if "unique_key" in metadata:
                unique_key_name = f"unique_key:man_page:{metadata['unique_key']}"
                await asyncio.to_thread(
                    self.redis_client.set, unique_key_name, fact_id
                )

            # Vectorize and store in ChromaDB
            if self.vector_store:
                # Sanitize metadata for ChromaDB
                sanitized_metadata = _sanitize_metadata_for_chromadb(metadata)

                # Create Document for LlamaIndex
                doc = Document(
                    text=content, doc_id=fact_id, metadata=sanitized_metadata
                )

                # Add to vector store
                await asyncio.to_thread(self.vector_store.add, [doc])

                logger.info(f"Vectorized fact {fact_id} in ChromaDB")

            # Increment stats counter (Issue #71)
            await self._increment_stat("total_facts")
            await self._increment_stat("total_vectors")

            return {"status": "success", "fact_id": fact_id, "action": "created"}

        except Exception as e:
            logger.error(f"Failed to store fact: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}

    async def vectorize_existing_fact(self, fact_id: str) -> Dict[str, Any]:
        """
        Vectorize an existing fact that wasn't vectorized during initial storage.

        Args:
            fact_id: ID of the fact to vectorize

        Returns:
            Dict with status
        """
        self.ensure_initialized()

        try:
            # Get fact from Redis
            fact_key = f"fact:{fact_id}"
            fact_data = await asyncio.to_thread(self.redis_client.hgetall, fact_key)

            if not fact_data:
                return {"status": "error", "message": "Fact not found"}

            # Decode data
            decoded = {}
            for key, value in fact_data.items():
                k = key.decode("utf-8") if isinstance(key, bytes) else key
                v = value.decode("utf-8") if isinstance(value, bytes) else value
                decoded[k] = v

            content = decoded.get("content", "")
            if not content:
                return {"status": "error", "message": "Fact has no content"}

            # Parse metadata
            metadata = {}
            if "metadata" in decoded:
                try:
                    metadata = json.loads(decoded["metadata"])
                except json.JSONDecodeError:
                    pass

            metadata["fact_id"] = fact_id

            # Import sanitization utility
            from src.knowledge.utils import sanitize_metadata_for_chromadb as _sanitize_metadata_for_chromadb

            # Sanitize metadata
            sanitized_metadata = _sanitize_metadata_for_chromadb(metadata)

            # Vectorize
            if self.vector_store:
                doc = Document(
                    text=content, doc_id=fact_id, metadata=sanitized_metadata
                )
                await asyncio.to_thread(self.vector_store.add, [doc])

                logger.info(f"Vectorized existing fact {fact_id}")
                return {"status": "success", "message": "Fact vectorized successfully"}
            else:
                return {"status": "error", "message": "Vector store not available"}

        except Exception as e:
            logger.error(f"Failed to vectorize fact {fact_id}: {e}")
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
            fact_key = f"fact:{fact_id}"
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
            logger.error(f"Error retrieving fact {fact_id}: {e}")
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
                if not fact_data:
                    continue

                # Decode
                decoded = {}
                for k, v in fact_data.items():
                    dk = k.decode("utf-8") if isinstance(k, bytes) else k
                    dv = v.decode("utf-8") if isinstance(v, bytes) else v
                    decoded[dk] = dv

                # Extract fact_id from key
                fact_id = (
                    key.decode("utf-8").replace("fact:", "")
                    if isinstance(key, bytes)
                    else key.replace("fact:", "")
                )

                # Parse metadata
                metadata = {}
                if "metadata" in decoded:
                    try:
                        metadata = json.loads(decoded["metadata"])
                    except json.JSONDecodeError:
                        pass

                # Apply collection filter if specified
                if collection and metadata.get("collection") != collection:
                    continue

                facts.append(
                    {
                        "fact_id": fact_id,
                        "content": decoded.get("content", ""),
                        "metadata": metadata,
                        "timestamp": decoded.get("timestamp", ""),
                    }
                )

            return facts

        except Exception as e:
            logger.error(f"Error retrieving all facts: {e}")
            return []

    async def update_fact(
        self, fact_id: str, content: str = None, metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Update an existing fact.

        Args:
            fact_id: ID of the fact to update
            content: New content (optional)
            metadata: New or updated metadata (optional)

        Returns:
            Dict with status
        """
        self.ensure_initialized()

        try:
            fact_key = f"fact:{fact_id}"

            # Check if fact exists
            exists = await asyncio.to_thread(self.redis_client.exists, fact_key)
            if not exists:
                return {"status": "error", "message": "Fact not found"}

            # Get current fact data
            fact_data = await asyncio.to_thread(self.redis_client.hgetall, fact_key)

            # Decode current data
            decoded = {}
            for key, value in fact_data.items():
                k = key.decode("utf-8") if isinstance(key, bytes) else key
                v = value.decode("utf-8") if isinstance(value, bytes) else value
                decoded[k] = v

            # Parse current metadata
            current_metadata = {}
            if "metadata" in decoded:
                try:
                    current_metadata = json.loads(decoded["metadata"])
                except json.JSONDecodeError:
                    pass

            # Update content if provided
            if content is not None:
                decoded["content"] = content

            # Update metadata if provided
            if metadata is not None:
                current_metadata.update(metadata)

            # Update timestamp
            current_metadata["updated_at"] = datetime.now().isoformat()

            # Store updated fact
            await asyncio.to_thread(
                self.redis_client.hset,
                fact_key,
                mapping={
                    "content": decoded["content"],
                    "metadata": json.dumps(current_metadata),
                    "timestamp": decoded.get("timestamp", ""),
                },
            )

            # Re-vectorize if content changed
            if content is not None and self.vector_store:
                from src.knowledge.utils import sanitize_metadata_for_chromadb as _sanitize_metadata_for_chromadb

                sanitized_metadata = _sanitize_metadata_for_chromadb(current_metadata)
                sanitized_metadata["fact_id"] = fact_id

                # Delete old vector
                await asyncio.to_thread(self.vector_store.delete, fact_id)

                # Add new vector
                doc = Document(
                    text=decoded["content"],
                    doc_id=fact_id,
                    metadata=sanitized_metadata,
                )
                await asyncio.to_thread(self.vector_store.add, [doc])

                logger.info(f"Re-vectorized updated fact {fact_id}")

            return {"status": "success", "fact_id": fact_id, "action": "updated"}

        except Exception as e:
            logger.error(f"Failed to update fact {fact_id}: {e}")
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
            fact_key = f"fact:{fact_id}"

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
                    logger.warning(f"Could not delete vector for fact {fact_id}: {e}")

            # Decrement stats counter (Issue #71)
            await self._decrement_stat("total_facts")
            await self._decrement_stat("total_vectors")

            logger.info(f"Deleted fact {fact_id}")
            return {"status": "success", "fact_id": fact_id, "action": "deleted"}

        except Exception as e:
            logger.error(f"Failed to delete fact {fact_id}: {e}")
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
