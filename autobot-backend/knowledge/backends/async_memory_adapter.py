# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Async in-memory vector-store backend for unit tests (Issue #5316).

Provides a deterministic, dependency-free implementation of
``AsyncBaseCollection`` / ``AsyncBaseClient`` by wrapping the existing sync
``InMemoryCollection`` / ``InMemoryClient`` in ``async def`` shims. The
underlying store is in-process, so no thread offloading is needed —
``async def ... return <sync_result>`` is sufficient to satisfy the async
contract for tests and adapter parity.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from knowledge.backends.async_base import AsyncBaseClient, AsyncBaseCollection
from knowledge.backends.base import Embedding, Metadata, Where, WhereDocument
from knowledge.backends.memory_adapter import InMemoryClient, InMemoryCollection


class AsyncInMemoryCollection(AsyncBaseCollection):
    """Async shim over ``InMemoryCollection`` — no thread offloading needed."""

    def __init__(self, sync_collection: InMemoryCollection) -> None:
        self._sync = sync_collection
        self.name = sync_collection.name

    async def add(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        self._sync.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    async def upsert(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        self._sync.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    async def update(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        self._sync.update(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    async def get(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
        limit: int | None = None,
        offset: int | None = None,
        include: Sequence[str] | None = None,
    ) -> Dict[str, Any]:
        return self._sync.get(
            ids=ids,
            where=where,
            where_document=where_document,
            limit=limit,
            offset=offset,
            include=include,
        )

    async def query(
        self,
        *,
        query_embeddings: Sequence[Embedding] | None = None,
        query_texts: Sequence[str] | None = None,
        n_results: int = 10,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
        include: Sequence[str] | None = None,
    ) -> Dict[str, Any]:
        return self._sync.query(
            query_embeddings=query_embeddings,
            query_texts=query_texts,
            n_results=n_results,
            where=where,
            where_document=where_document,
            include=include,
        )

    async def delete(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
    ) -> None:
        self._sync.delete(ids=ids, where=where, where_document=where_document)

    async def count(self) -> int:
        return self._sync.count()

    async def peek(self, limit: int = 10) -> Dict[str, Any]:
        return self._sync.peek(limit=limit)


class AsyncInMemoryClient(AsyncBaseClient):
    """Async shim over ``InMemoryClient`` — preserves collection identity so
    two ``get_or_create_collection`` calls return wrappers sharing the same
    underlying storage (required for the idempotence contract test)."""

    def __init__(self) -> None:
        self._sync = InMemoryClient()
        # Keep one AsyncInMemoryCollection per underlying sync collection so
        # callers get the same wrapper instance back each call — matches
        # InMemoryClient's sync behaviour and the contract test expectation.
        self._wrappers: Dict[str, AsyncInMemoryCollection] = {}

    def _wrap(self, sync_col: InMemoryCollection) -> AsyncInMemoryCollection:
        wrapper = self._wrappers.get(sync_col.name)
        if wrapper is None:
            wrapper = AsyncInMemoryCollection(sync_col)
            self._wrappers[sync_col.name] = wrapper
        return wrapper

    async def get_or_create_collection(
        self,
        name: str,
        *,
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> AsyncBaseCollection:
        sync_col = self._sync.get_or_create_collection(name, metadata=metadata, embedding_function=embedding_function)
        return self._wrap(sync_col)  # type: ignore[arg-type]

    async def get_collection(self, name: str) -> AsyncBaseCollection:
        sync_col = self._sync.get_collection(name)
        return self._wrap(sync_col)  # type: ignore[arg-type]

    async def create_collection(
        self,
        name: str,
        *,
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> AsyncBaseCollection:
        sync_col = self._sync.create_collection(name, metadata=metadata, embedding_function=embedding_function)
        return self._wrap(sync_col)  # type: ignore[arg-type]

    async def list_collections(self) -> List[AsyncBaseCollection]:
        return [self._wrap(c) for c in self._sync.list_collections()]  # type: ignore[arg-type,misc]

    async def delete_collection(self, name: str) -> None:
        self._sync.delete_collection(name)
        self._wrappers.pop(name, None)

    async def reset(self) -> None:
        self._sync.reset()
        self._wrappers.clear()


__all__ = ["AsyncInMemoryClient", "AsyncInMemoryCollection"]
