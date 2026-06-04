# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Async ChromaDB Client Wrapper

Provides async-compatible wrappers for ChromaDB operations to prevent
event loop blocking in async functions.

Issue #369: ChromaDB operations (add, query, upsert, get, delete) are synchronous
and block the event loop when called from async contexts. This module wraps
all blocking operations with asyncio.to_thread() for proper async handling.

Usage:
    from utils.async_chromadb_client import (
from autobot_shared.logging_manager import get_logger
        get_async_chromadb_client,
        AsyncChromaCollection
    )

    # Get async client
    client = await get_async_chromadb_client(db_path="data/chromadb")

    # Get async collection wrapper
    collection = await client.get_or_create_collection("my_collection")

    # All operations are now async
    await collection.add(ids=["1"], documents=["doc"], embeddings=[[0.1, 0.2]])
    results = await collection.query(query_embeddings=[[0.1, 0.2]], n_results=5)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as _ssot_config

if TYPE_CHECKING:
    import chromadb  # noqa: F401

# Issue #3094: Use SSOT config port so the default (8100) matches Ansible deployment.
# Host remains os.getenv-based: empty string = use local PersistentClient (dev mode).
_CHROMADB_HOST = _ssot_config.vm.chromadb
_CHROMADB_PORT = _ssot_config.port.chromadb

logger = get_logger(__name__)

# Issue #380: Module-level tuples for ChromaDB default includes
_DEFAULT_QUERY_INCLUDE = ["documents", "metadatas", "distances"]
_DEFAULT_GET_INCLUDE = ["documents", "metadatas", "embeddings"]


class AsyncChromaCollection:
    """
    Async wrapper for ChromaDB Collection.

    Wraps all blocking ChromaDB collection operations with asyncio.to_thread()
    to prevent event loop blocking in async contexts.

    All methods mirror the synchronous ChromaDB Collection API but are async.
    """

    def __init__(self, collection: Any):
        """Initialize async wrapper around a ChromaDB collection."""
        self._collection = collection

    @property
    def name(self) -> str:
        """Get collection name."""
        return self._collection.name

    @property
    def metadata(self) -> Dict[str, Any] | None:
        """Get collection metadata."""
        return self._collection.metadata

    async def count(self) -> int:
        """Get the number of items in the collection (async)."""
        return await asyncio.to_thread(self._collection.count)

    async def add(
        self,
        ids: List[str],
        embeddings: List[List[float]] | None = None,
        metadatas: List[Dict[str, Any]] | None = None,
        documents: List[str] | None = None,
    ) -> None:
        """
        Add items to the collection (async).

        Args:
            ids: List of unique IDs for the items
            embeddings: Optional list of embedding vectors
            metadatas: Optional list of metadata dicts
            documents: Optional list of document strings

        #6514: if the collection metadata declares an embedding-provenance
        tag (model_name + dim), this guard rejects writes whose vector
        dim doesn't match. Stops silent cross-model contamination at the
        chokepoint instead of letting it land in the index and
        corrupt cosine-distance recall at query time.

        Untagged (legacy) collections fall through unchanged — the guard
        only fires when a writer-side caller has tagged the collection.
        """
        if embeddings is not None:
            from autobot_shared.embedding_provenance import (
                provenance_from_metadata,
                validate_vectors_against_provenance,
            )

            provenance = provenance_from_metadata(self._collection.metadata)
            if provenance is not None:
                # Raises EmbeddingMismatchError (subclass of ValueError) on
                # cross-model write attempts. Caller catches the type or
                # the existing `except ValueError:` block degrades it.
                validate_vectors_against_provenance(embeddings, provenance)

        await asyncio.to_thread(
            self._collection.add,
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

    async def query(
        self,
        query_embeddings: List[List[float]] | None = None,
        query_texts: List[str] | None = None,
        n_results: int = 10,
        where: Dict[str, Any] | None = None,
        where_document: Dict[str, Any] | None = None,
        include: List[str] | None = None,
    ) -> Dict[str, Any]:
        """
        Query the collection for similar items (async).

        Args:
            query_embeddings: List of query embedding vectors
            query_texts: List of query text strings (alternative to embeddings)
            n_results: Number of results to return
            where: Optional metadata filter
            where_document: Optional document content filter
            include: Fields to include in results (documents, metadatas, distances)

        Returns:
            Dict with query results including ids, documents, metadatas, distances
        """
        if include is None:
            include = _DEFAULT_QUERY_INCLUDE  # Issue #380: use module constant

        return await asyncio.to_thread(
            self._collection.query,
            query_embeddings=query_embeddings,
            query_texts=query_texts,
            n_results=n_results,
            where=where,
            where_document=where_document,
            include=include,
        )

    async def query_batch(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 10,
        where: Dict[str, Any] | None = None,
        where_document: Dict[str, Any] | None = None,
        include: List[str] | None = None,
    ) -> Dict[str, Any]:
        """Batch vector search — all embeddings in a single ChromaDB call.

        Issue #8153: eliminates per-query thread dispatch overhead. ChromaDB
        returns nested-list results: results["ids"][i] is the hit-list for
        query i. Callers must slice the returned dict by query index.

        Args:
            query_embeddings: N query vectors; each is a list[float].
            n_results: Number of results per query.
            where: Optional metadata filter applied to every query.
            where_document: Optional document content filter.
            include: Fields to include (default: documents, metadatas, distances).

        Returns:
            Dict with nested lists, one inner list per query vector.
        """
        if include is None:
            include = _DEFAULT_QUERY_INCLUDE
        return await asyncio.to_thread(
            self._collection.query,
            query_embeddings=query_embeddings,
            n_results=n_results,
            where=where,
            where_document=where_document,
            include=include,
        )

    async def get(
        self,
        ids: List[str] | None = None,
        where: Dict[str, Any] | None = None,
        where_document: Dict[str, Any] | None = None,
        include: List[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Dict[str, Any]:
        """
        Get items from the collection by ID or filter (async).

        Args:
            ids: Optional list of IDs to retrieve
            where: Optional metadata filter
            where_document: Optional document content filter
            include: Fields to include in results
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Dict with matching items
        """
        if include is None:
            include = _DEFAULT_GET_INCLUDE  # Issue #380: use module constant

        return await asyncio.to_thread(
            self._collection.get,
            ids=ids,
            where=where,
            where_document=where_document,
            include=include,
            limit=limit,
            offset=offset,
        )

    async def update(
        self,
        ids: List[str],
        embeddings: List[List[float]] | None = None,
        metadatas: List[Dict[str, Any]] | None = None,
        documents: List[str] | None = None,
    ) -> None:
        """
        Update items in the collection (async).

        Args:
            ids: List of IDs to update
            embeddings: Optional new embeddings
            metadatas: Optional new metadata
            documents: Optional new documents
        """
        await asyncio.to_thread(
            self._collection.update,
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

    async def upsert(
        self,
        ids: List[str],
        embeddings: List[List[float]] | None = None,
        metadatas: List[Dict[str, Any]] | None = None,
        documents: List[str] | None = None,
    ) -> None:
        """
        Upsert (insert or update) items in the collection (async).

        Args:
            ids: List of IDs
            embeddings: Optional embeddings
            metadatas: Optional metadata
            documents: Optional documents
        """
        await asyncio.to_thread(
            self._collection.upsert,
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

    async def delete(
        self,
        ids: List[str] | None = None,
        where: Dict[str, Any] | None = None,
        where_document: Dict[str, Any] | None = None,
    ) -> None:
        """
        Delete items from the collection (async).

        Args:
            ids: Optional list of IDs to delete
            where: Optional metadata filter for deletion
            where_document: Optional document content filter
        """
        await asyncio.to_thread(
            self._collection.delete,
            ids=ids,
            where=where,
            where_document=where_document,
        )

    async def peek(self, limit: int = 10) -> Dict[str, Any]:
        """Peek at the first N items in the collection (async)."""
        return await asyncio.to_thread(self._collection.peek, limit=limit)

    async def modify(
        self,
        name: str | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """Modify collection name or metadata (async)."""
        await asyncio.to_thread(
            self._collection.modify,
            name=name,
            metadata=metadata,
        )


class AsyncChromaClient:
    """
    Async wrapper for ChromaDB client (HttpClient or PersistentClient).

    Provides async methods for collection management operations.
    """

    def __init__(self, client: Any):
        """Initialize async wrapper around a ChromaDB client."""
        self._client = client
        self._collection_cache: Dict[str, AsyncChromaCollection] = {}

    async def list_collections(self) -> List[str]:
        """List all collection names (async)."""
        collections = await asyncio.to_thread(self._client.list_collections)
        return [c.name for c in collections]

    async def get_collection(
        self,
        name: str,
        embedding_function: Any | None = None,
    ) -> AsyncChromaCollection:
        """
        Get an existing collection by name (async).

        Args:
            name: Collection name
            embedding_function: Optional embedding function

        Returns:
            AsyncChromaCollection wrapper
        """
        if name in self._collection_cache:
            return self._collection_cache[name]

        collection = await asyncio.to_thread(
            self._client.get_collection,
            name=name,
            embedding_function=embedding_function,
        )
        async_collection = AsyncChromaCollection(collection)
        self._collection_cache[name] = async_collection
        return async_collection

    async def get_or_create_collection(
        self,
        name: str,
        metadata: Dict[str, Any] | None = None,
        embedding_function: Any | None = None,
    ) -> AsyncChromaCollection:
        """
        Get or create a collection (async).

        Args:
            name: Collection name
            metadata: Optional collection metadata (including HNSW params)
            embedding_function: Optional embedding function

        Returns:
            AsyncChromaCollection wrapper
        """
        if name in self._collection_cache:
            return self._collection_cache[name]

        collection = await asyncio.to_thread(
            self._client.get_or_create_collection,
            name=name,
            metadata=metadata,
            embedding_function=embedding_function,
        )
        async_collection = AsyncChromaCollection(collection)
        self._collection_cache[name] = async_collection
        return async_collection

    async def create_collection(
        self,
        name: str,
        metadata: Dict[str, Any] | None = None,
        embedding_function: Any | None = None,
    ) -> AsyncChromaCollection:
        """
        Create a new collection (async).

        Args:
            name: Collection name
            metadata: Optional collection metadata
            embedding_function: Optional embedding function

        Returns:
            AsyncChromaCollection wrapper
        """
        collection = await asyncio.to_thread(
            self._client.create_collection,
            name=name,
            metadata=metadata,
            embedding_function=embedding_function,
        )
        async_collection = AsyncChromaCollection(collection)
        self._collection_cache[name] = async_collection
        return async_collection

    async def delete_collection(self, name: str) -> None:
        """Delete a collection (async)."""
        await asyncio.to_thread(self._client.delete_collection, name=name)
        self._collection_cache.pop(name, None)

    async def heartbeat(self) -> int:
        """Check if the client is alive (async)."""
        return await asyncio.to_thread(self._client.heartbeat)

    async def reset(self) -> bool:
        """Reset the database (async). Only works if allow_reset=True."""
        result = await asyncio.to_thread(self._client.reset)
        self._collection_cache.clear()
        return result


# Module-level client cache for singleton pattern
_async_client_cache: Dict[str, AsyncChromaClient] = {}


async def get_async_chromadb_client(
    db_path: str = "",
    allow_reset: bool = False,
    anonymized_telemetry: bool = False,
) -> AsyncChromaClient:
    """
    Get or create an async ChromaDB client (singleton per key).

    Uses remote HttpClient when AUTOBOT_CHROMADB_HOST is set, otherwise
    falls back to local PersistentClient.

    Args:
        db_path: Path for local PersistentClient (ignored when remote)
        allow_reset: Whether to allow database resets (default: False)
        anonymized_telemetry: Whether to enable telemetry (default: False)

    Returns:
        AsyncChromaClient wrapper for async operations
    """
    # Issue #3016: lazy import — chromadb is heavy (~1s import)
    import chromadb  # noqa: F811
    from chromadb.config import Settings as ChromaSettings

    cache_key = f"http://{_CHROMADB_HOST}:{_CHROMADB_PORT}" if _CHROMADB_HOST else db_path

    if cache_key in _async_client_cache:
        return _async_client_cache[cache_key]

    try:
        if _CHROMADB_HOST:
            sync_client = chromadb.HttpClient(
                host=_CHROMADB_HOST,
                port=_CHROMADB_PORT,
                settings=ChromaSettings(
                    anonymized_telemetry=anonymized_telemetry,
                ),
            )
            async_client = AsyncChromaClient(sync_client)
            _async_client_cache[cache_key] = async_client
            logger.info(
                "Async ChromaDB HTTP client connected to %s:%s",
                _CHROMADB_HOST,
                _CHROMADB_PORT,
            )
            return async_client

        # Fallback: local PersistentClient
        chroma_path = Path(db_path or "data/chromadb")
        await asyncio.to_thread(chroma_path.mkdir, parents=True, exist_ok=True)

        sync_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(
                allow_reset=allow_reset,
                anonymized_telemetry=anonymized_telemetry,
            ),
        )
        async_client = AsyncChromaClient(sync_client)
        _async_client_cache[cache_key] = async_client
        logger.info("Async ChromaDB persistent client at: %s", chroma_path)
        return async_client

    except Exception as e:
        logger.error("Failed to initialize async ChromaDB client: %s", e)
        raise


def wrap_collection_async(collection: Any) -> AsyncChromaCollection:
    """
    Wrap an existing synchronous collection for async use.

    Use this when you already have a collection instance and need
    to convert it to async operations.

    Args:
        collection: Synchronous ChromaDB collection

    Returns:
        AsyncChromaCollection wrapper
    """
    return AsyncChromaCollection(collection)
