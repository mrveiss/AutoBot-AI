# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Async-native abstract base classes for pluggable vector-store backends.

Issue #5316: PR #5310 (#5194) migrated 2 sync callers onto
``BaseCollection``/``BaseClient``. Several async callers
(``knowledge/pipeline/loaders/chromadb_loader.py``,
``services/knowledge/doc_indexer.py``, ``knowledge/index.py``) were deferred
because the existing ABCs in ``knowledge.backends.base`` are sync-only —
forcing them onto a sync interface would block the event loop.

This module mirrors the sync ABC surface exactly — same kwargs, same return
shapes (see ``knowledge.backends.base`` for the return-shape contract). Every
``AsyncBaseCollection`` method is the ``async def`` equivalent of the matching
``BaseCollection`` method.

Callers should pick sync or async based on their surrounding context, never
because one interface supports something the other does not.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence

from knowledge.backends.base import Embedding, Metadata, Where, WhereDocument


class AsyncBaseCollection(ABC):
    """Async-native vector collection interface.

    Method signatures mirror ``BaseCollection`` exactly — same kwargs, same
    return shapes. Implementations MUST preserve the semantics documented in
    ``knowledge.backends.base.BaseCollection`` (add is no-op on duplicate id,
    upsert replaces, query returns nested-list dict, etc.).
    """

    name: str

    @abstractmethod
    async def add(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        """Insert new items. Duplicate ids are a no-op (original retained);
        use ``upsert`` for replace semantics."""

    @abstractmethod
    async def upsert(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        """Insert-or-replace items by id. No error on duplicate."""

    @abstractmethod
    async def update(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        """Modify existing items by id. Missing ids are silently skipped."""

    @abstractmethod
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
        """Fetch items by id / filter. Returns flat-list dict."""

    @abstractmethod
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
        """Vector search. Returns nested-list dict, one inner list per query."""

    async def query_batch(
        self,
        query_embeddings: Sequence[Embedding],
        n_results: int = 10,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
        include: Sequence[str] | None = None,
    ) -> Dict[str, Any]:
        """Batch vector search — multiple embeddings in a single backend call.

        Issue #8153: default implementation forwards to ``query()`` so all
        existing subclasses gain the method without changes. Backend adapters
        that support native multi-query (ChromaDB, etc.) should override.

        Returns nested-list dict: ``results["ids"][i]`` is the hit list for
        query ``i``.
        """
        return await self.query(
            query_embeddings=list(query_embeddings),
            n_results=n_results,
            where=where,
            where_document=where_document,
            include=include,
        )

    @abstractmethod
    async def delete(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
    ) -> None:
        """Delete items by id or filter. At least one filter required."""

    @abstractmethod
    async def count(self) -> int:
        """Return total number of stored items."""

    @abstractmethod
    async def peek(self, limit: int = 10) -> Dict[str, Any]:
        """Return up to ``limit`` items (any order). Flat-list dict."""


class AsyncBaseClient(ABC):
    """Async-native client / factory for collections.

    Implementations back a persistent or in-memory store and MUST enforce
    unique collection names per client instance. Method signatures mirror
    ``BaseClient`` exactly — see that class for semantics.
    """

    @abstractmethod
    async def get_or_create_collection(
        self,
        name: str,
        *,
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> AsyncBaseCollection:
        """Return existing collection or create a new one."""

    @abstractmethod
    async def get_collection(self, name: str) -> AsyncBaseCollection:
        """Return existing collection. Raise ``ValueError`` if missing."""

    @abstractmethod
    async def create_collection(
        self,
        name: str,
        *,
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> AsyncBaseCollection:
        """Create collection. Raise ``ValueError`` if name already exists."""

    @abstractmethod
    async def list_collections(self) -> List[AsyncBaseCollection]:
        """Return known collections as ``AsyncBaseCollection`` instances.

        Adapters MUST wrap any raw backend objects so callers get a uniform
        interface regardless of backend (#5134).
        """

    @abstractmethod
    async def delete_collection(self, name: str) -> None:
        """Delete a collection by name. Missing name MUST raise ``ValueError``."""

    @abstractmethod
    async def reset(self) -> None:
        """Drop ALL collections. Destructive — guarded by backend config."""


__all__ = [
    "AsyncBaseClient",
    "AsyncBaseCollection",
]
