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
    from src.utils.async_chromadb_client import (
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

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)

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

    def __init__(self, collection: chromadb.Collection):
        """Initialize async wrapper around a ChromaDB collection."""
        self._collection = collection

    @property
    def name(self) -> str:
        """Get collection name."""
        return self._collection.name

    @property
    def metadata(self) -> Optional[Dict[str, Any]]:
        """Get collection metadata."""
        return self._collection.metadata

    async def count(self) -> int:
        """Get the number of items in the collection (async)."""
        return await asyncio.to_thread(self._collection.count)

    async def add(
        self,
        ids: List[str],
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        documents: Optional[List[str]] = None,
    ) -> None:
        """
        Add items to the collection (async).

        Args:
            ids: List of unique IDs for the items
            embeddings: Optional list of embedding vectors
            metadatas: Optional list of metadata dicts
            documents: Optional list of document strings
        """
        await asyncio.to_thread(
            self._collection.add,
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

    async def query(
        self,
        query_embeddings: Optional[List[List[float]]] = None,
        query_texts: Optional[List[str]] = None,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
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

    async def get(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
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
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        documents: Optional[List[str]] = None,
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
        embeddings: Optional[List[List[float]]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        documents: Optional[List[str]] = None,
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
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
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
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Modify collection name or metadata (async)."""
        await asyncio.to_thread(
            self._collection.modify,
            name=name,
            metadata=metadata,
        )


class AsyncChromaClient:
    """
    Async wrapper for ChromaDB PersistentClient.

    Provides async methods for collection management operations.
    """

    def __init__(self, client: chromadb.PersistentClient):
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
        embedding_function: Optional[Any] = None,
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
        metadata: Optional[Dict[str, Any]] = None,
        embedding_function: Optional[Any] = None,
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
        metadata: Optional[Dict[str, Any]] = None,
        embedding_function: Optional[Any] = None,
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
    db_path: str,
    allow_reset: bool = False,
    anonymized_telemetry: bool = False,
) -> AsyncChromaClient:
    """
    Get or create an async ChromaDB client (singleton per path).

    This is the recommended entry point for async ChromaDB access.

    Args:
        db_path: Path to the ChromaDB database directory
        allow_reset: Whether to allow database resets (default: False)
        anonymized_telemetry: Whether to enable telemetry (default: False)

    Returns:
        AsyncChromaClient wrapper for async operations
    """
    # Return cached client if exists
    if db_path in _async_client_cache:
        return _async_client_cache[db_path]

    try:
        # Ensure directory exists
        # Issue #358 - avoid blocking
        chroma_path = Path(db_path)
        await asyncio.to_thread(chroma_path.mkdir, parents=True, exist_ok=True)

        # Create sync client (this is fast, doesn't need to_thread)
        sync_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(
                allow_reset=allow_reset,
                anonymized_telemetry=anonymized_telemetry,
            ),
        )

        # Wrap in async client
        async_client = AsyncChromaClient(sync_client)
        _async_client_cache[db_path] = async_client

        logger.info("Async ChromaDB client initialized at: %s", chroma_path)
        return async_client

    except Exception as e:
        logger.error("Failed to initialize async ChromaDB client: %s", e)
        raise


def wrap_collection_async(collection: chromadb.Collection) -> AsyncChromaCollection:
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
