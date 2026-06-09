# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Async ChromaDB adapter implementing the ``AsyncBaseCollection`` /
``AsyncBaseClient`` ABCs (Issue #5316).

Wraps the async ChromaDB client from ``utils/async_chromadb_client.py`` —
does NOT reimplement any ChromaDB behaviour. Mirrors the sync
``ChromaDBCollection`` / ``ChromaDBClient`` adapters one-for-one; the only
differences are ``async def`` and ``await``.
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Sequence

from autobot_shared.logging_manager import get_logger
from knowledge.backends.async_base import AsyncBaseClient, AsyncBaseCollection
from knowledge.backends.base import Embedding, Metadata, Where, WhereDocument

logger = get_logger(__name__)


class AsyncChromaDBCollection(AsyncBaseCollection):
    """Thin async wrapper around an ``AsyncChromaCollection`` instance.

    Every method forwards its arguments verbatim to the underlying async
    ChromaDB collection, which already wraps blocking ChromaDB calls in
    ``asyncio.to_thread``.
    """

    def __init__(self, raw: Any) -> None:
        self._raw = raw
        self.name = getattr(raw, "name", "")

    async def add(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        await self._raw.add(
            ids=list(ids),
            documents=list(documents) if documents is not None else None,
            metadatas=list(metadatas) if metadatas is not None else None,
            embeddings=list(embeddings) if embeddings is not None else None,
        )

    async def upsert(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        await self._raw.upsert(
            ids=list(ids),
            documents=list(documents) if documents is not None else None,
            metadatas=list(metadatas) if metadatas is not None else None,
            embeddings=list(embeddings) if embeddings is not None else None,
        )

    async def update(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        await self._raw.update(
            ids=list(ids),
            documents=list(documents) if documents is not None else None,
            metadatas=list(metadatas) if metadatas is not None else None,
            embeddings=list(embeddings) if embeddings is not None else None,
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
    ) -> dict:
        # AsyncChromaCollection.get has defaults for include — pass only the
        # fields caller set, letting the wrapper apply its own default when
        # include is None.
        kwargs: dict = {}
        if ids is not None:
            kwargs["ids"] = list(ids)
        if where is not None:
            kwargs["where"] = where
        if where_document is not None:
            kwargs["where_document"] = where_document
        if limit is not None:
            kwargs["limit"] = limit
        if offset is not None:
            kwargs["offset"] = offset
        if include is not None:
            kwargs["include"] = list(include)
        return await self._raw.get(**kwargs)

    async def query(
        self,
        *,
        query_embeddings: Sequence[Embedding] | None = None,
        query_texts: Sequence[str] | None = None,
        n_results: int = 10,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
        include: Sequence[str] | None = None,
    ) -> dict:
        kwargs: dict = {"n_results": n_results}
        if query_embeddings is not None:
            kwargs["query_embeddings"] = [list(e) for e in query_embeddings]
        if query_texts is not None:
            kwargs["query_texts"] = list(query_texts)
        if where is not None:
            kwargs["where"] = where
        if where_document is not None:
            kwargs["where_document"] = where_document
        if include is not None:
            kwargs["include"] = list(include)
        return await self._raw.query(**kwargs)

    async def query_batch(
        self,
        query_embeddings: Sequence[Embedding],
        n_results: int = 10,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
        include: Sequence[str] | None = None,
    ) -> dict:
        """Issue #8153: batch multiple embeddings into a single ChromaDB call.

        Delegates to ``AsyncChromaCollection.query_batch()`` which wraps the
        underlying synchronous ``collection.query()`` in one ``asyncio.to_thread``
        dispatch regardless of how many embeddings are in the batch.
        """
        return await self._raw.query_batch(
            query_embeddings=[list(e) for e in query_embeddings],
            n_results=n_results,
            where=where,
            where_document=where_document,
            include=list(include) if include is not None else None,
        )

    async def delete(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
    ) -> None:
        kwargs: dict = {}
        if ids is not None:
            kwargs["ids"] = list(ids)
        if where is not None:
            kwargs["where"] = where
        if where_document is not None:
            kwargs["where_document"] = where_document
        if not kwargs:
            raise ValueError("delete requires ids or where")
        await self._raw.delete(**kwargs)

    async def count(self) -> int:
        return int(await self._raw.count())

    async def peek(self, limit: int = 10) -> dict:
        return await self._raw.peek(limit=limit)


class AsyncChromaDBClient(AsyncBaseClient):
    """Thin async wrapper around an ``AsyncChromaClient`` instance.

    Construction is delegated to ``utils.async_chromadb_client`` so the
    existing HttpClient / PersistentClient selection, client cache and
    remote-vs-local logic continue to live in one place (#369).
    """

    def __init__(self, raw: Any) -> None:
        # ``raw`` is expected to be ``utils.async_chromadb_client.AsyncChromaClient``.
        self._raw = raw

    async def get_or_create_collection(
        self,
        name: str,
        *,
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> AsyncBaseCollection:
        from datetime import datetime, timezone

        provenance: dict = {"created_at": datetime.now(timezone.utc).isoformat()}
        if metadata:
            provenance.update(metadata)
        raw_col = await self._raw.get_or_create_collection(
            name=name,
            metadata=provenance,
            embedding_function=embedding_function,
        )
        return AsyncChromaDBCollection(raw_col)

    async def get_collection(self, name: str) -> AsyncBaseCollection:
        try:
            raw_col = await self._raw.get_collection(name=name)
        except Exception as exc:  # ChromaDB raises its own exception type
            raise ValueError(f"no such collection: {name}") from exc
        return AsyncChromaDBCollection(raw_col)

    async def create_collection(
        self,
        name: str,
        *,
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> AsyncBaseCollection:
        from datetime import datetime, timezone

        provenance: dict = {"created_at": datetime.now(timezone.utc).isoformat()}
        if metadata:
            provenance.update(metadata)
        try:
            raw_col = await self._raw.create_collection(
                name=name,
                metadata=provenance,
                embedding_function=embedding_function,
            )
        except Exception as exc:
            raise ValueError(f"collection already exists: {name}") from exc
        return AsyncChromaDBCollection(raw_col)

    async def list_collections(self) -> List[AsyncBaseCollection]:
        # ``AsyncChromaClient.list_collections`` currently returns a list of
        # names (see utils/async_chromadb_client.py). Reach through to the
        # underlying raw client to get actual collection objects so we can
        # wrap them — matches the sync ``ChromaDBClient.list_collections``
        # contract (#5134).
        raw_cols = await asyncio.to_thread(self._raw._client.list_collections)
        return [AsyncChromaDBCollection(c) for c in raw_cols]

    async def delete_collection(self, name: str) -> None:
        try:
            await self._raw.delete_collection(name=name)
        except Exception as exc:
            raise ValueError(f"no such collection: {name}") from exc

    async def reset(self) -> None:
        await self._raw.reset()


__all__ = ["AsyncChromaDBClient", "AsyncChromaDBCollection"]
