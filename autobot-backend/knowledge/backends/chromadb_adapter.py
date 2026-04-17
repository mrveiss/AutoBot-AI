# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ChromaDB adapter implementing the ``BaseCollection`` / ``BaseClient`` ABCs
(Issue #5062).

This module wraps ``chromadb.Client`` / ``chromadb.Collection`` instances —
it does NOT reimplement any ChromaDB behaviour. The goal is a thin, explicit
seam so callers can target the ABC while we keep the existing production
client code (``utils/chromadb_client.py``) untouched.

Usage::

    from utils.chromadb_client import get_chromadb_client
    from knowledge.backends.chromadb_adapter import ChromaDBClient

    raw = get_chromadb_client()
    backend = ChromaDBClient(raw)
    col = backend.get_or_create_collection("knowledge_vectors")
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence

from knowledge.backends.base import (
    BaseClient,
    BaseCollection,
    Embedding,
    Metadata,
    Where,
    WhereDocument,
)

logger = logging.getLogger(__name__)


class ChromaDBCollection(BaseCollection):
    """Thin wrapper around a ``chromadb.Collection`` instance.

    Every method forwards its arguments verbatim to the underlying ChromaDB
    collection — ChromaDB already supplies the flat-list / nested-list return
    shapes documented in the ABC contract.
    """

    def __init__(self, raw: Any) -> None:
        self._raw = raw
        self.name = getattr(raw, "name", "")

    def add(
        self,
        *,
        ids: Sequence[str],
        documents: Optional[Sequence[str]] = None,
        metadatas: Optional[Sequence[Metadata]] = None,
        embeddings: Optional[Sequence[Embedding]] = None,
    ) -> None:
        self._raw.add(
            ids=list(ids),
            documents=list(documents) if documents is not None else None,
            metadatas=list(metadatas) if metadatas is not None else None,
            embeddings=list(embeddings) if embeddings is not None else None,
        )

    def upsert(
        self,
        *,
        ids: Sequence[str],
        documents: Optional[Sequence[str]] = None,
        metadatas: Optional[Sequence[Metadata]] = None,
        embeddings: Optional[Sequence[Embedding]] = None,
    ) -> None:
        self._raw.upsert(
            ids=list(ids),
            documents=list(documents) if documents is not None else None,
            metadatas=list(metadatas) if metadatas is not None else None,
            embeddings=list(embeddings) if embeddings is not None else None,
        )

    def update(
        self,
        *,
        ids: Sequence[str],
        documents: Optional[Sequence[str]] = None,
        metadatas: Optional[Sequence[Metadata]] = None,
        embeddings: Optional[Sequence[Embedding]] = None,
    ) -> None:
        self._raw.update(
            ids=list(ids),
            documents=list(documents) if documents is not None else None,
            metadatas=list(metadatas) if metadatas is not None else None,
            embeddings=list(embeddings) if embeddings is not None else None,
        )

    def get(
        self,
        *,
        ids: Optional[Sequence[str]] = None,
        where: Optional[Where] = None,
        where_document: Optional[WhereDocument] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        include: Optional[Sequence[str]] = None,
    ) -> dict:
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
        return self._raw.get(**kwargs)

    def query(
        self,
        *,
        query_embeddings: Optional[Sequence[Embedding]] = None,
        query_texts: Optional[Sequence[str]] = None,
        n_results: int = 10,
        where: Optional[Where] = None,
        where_document: Optional[WhereDocument] = None,
        include: Optional[Sequence[str]] = None,
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
        return self._raw.query(**kwargs)

    def delete(
        self,
        *,
        ids: Optional[Sequence[str]] = None,
        where: Optional[Where] = None,
        where_document: Optional[WhereDocument] = None,
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
        self._raw.delete(**kwargs)

    def count(self) -> int:
        return int(self._raw.count())

    def peek(self, limit: int = 10) -> dict:
        return self._raw.peek(limit=limit)


class ChromaDBClient(BaseClient):
    """Thin wrapper around a ``chromadb.Client`` / ``PersistentClient`` /
    ``HttpClient`` instance.

    The raw ChromaDB client is injected; this class does NOT construct one.
    Keeping construction in ``utils/chromadb_client.py`` means the HNSW /
    sqlite migration fixes (#1390, #2735) stay in a single place.
    """

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def get_or_create_collection(
        self,
        name: str,
        *,
        metadata: Optional[Metadata] = None,
        embedding_function: Optional[Any] = None,
    ) -> BaseCollection:
        kwargs: dict = {"name": name}
        if metadata is not None:
            kwargs["metadata"] = metadata
        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function
        return ChromaDBCollection(self._raw.get_or_create_collection(**kwargs))

    def get_collection(self, name: str) -> BaseCollection:
        try:
            return ChromaDBCollection(self._raw.get_collection(name=name))
        except Exception as exc:  # ChromaDB raises its own exception type
            raise ValueError(f"no such collection: {name}") from exc

    def create_collection(
        self,
        name: str,
        *,
        metadata: Optional[Metadata] = None,
        embedding_function: Optional[Any] = None,
    ) -> BaseCollection:
        kwargs: dict = {"name": name}
        if metadata is not None:
            kwargs["metadata"] = metadata
        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function
        try:
            return ChromaDBCollection(self._raw.create_collection(**kwargs))
        except Exception as exc:
            raise ValueError(f"collection already exists: {name}") from exc

    def list_collections(self) -> List[Any]:
        return list(self._raw.list_collections())

    def delete_collection(self, name: str) -> None:
        try:
            self._raw.delete_collection(name=name)
        except Exception as exc:
            raise ValueError(f"no such collection: {name}") from exc

    def reset(self) -> None:
        self._raw.reset()


__all__ = ["ChromaDBCollection", "ChromaDBClient"]
