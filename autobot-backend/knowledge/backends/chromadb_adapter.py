# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

from typing import Any, List, Sequence

from autobot_shared.logging_manager import get_logger
from knowledge.backends._chroma_args import (
    collection_provenance,
    delete_args,
    get_args,
    query_args,
    write_args,
)
from knowledge.backends.base import (
    BaseClient,
    BaseCollection,
    Embedding,
    Metadata,
    Where,
    WhereDocument,
)

logger = get_logger(__name__)


class ChromaDBCollection(BaseCollection):
    """Thin wrapper around a ``chromadb.Collection`` instance.

    Every method forwards its arguments verbatim to the underlying ChromaDB
    collection — ChromaDB already supplies the flat-list / nested-list return
    shapes documented in the ABC contract.
    """

    def __init__(self, raw: Any) -> None:
        self._raw = raw
        self.name = getattr(raw, "name", "")
        # Expose collection metadata so callers can read embedding provenance
        # without reaching into the raw ChromaDB object (#10420). Mirrors the
        # in-memory adapter, which already carries a ``metadata`` attribute.
        self.metadata = getattr(raw, "metadata", None) or {}

    def add(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        self._raw.add(**write_args(ids, documents, metadatas, embeddings))

    def upsert(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        self._raw.upsert(**write_args(ids, documents, metadatas, embeddings))

    def update(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        self._raw.update(**write_args(ids, documents, metadatas, embeddings))

    def get(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
        limit: int | None = None,
        offset: int | None = None,
        include: Sequence[str] | None = None,
    ) -> dict:
        return self._raw.get(**get_args(ids, where, where_document, limit, offset, include))

    def query(
        self,
        *,
        query_embeddings: Sequence[Embedding] | None = None,
        query_texts: Sequence[str] | None = None,
        n_results: int = 10,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
        include: Sequence[str] | None = None,
    ) -> dict:
        kwargs = query_args(query_embeddings, query_texts, n_results, where, where_document, include)
        return self._raw.query(**kwargs)

    def delete(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
    ) -> None:
        self._raw.delete(**delete_args(ids, where, where_document))

    def count(self) -> int:
        return int(self._raw.count())

    def peek(self, limit: int = 10) -> dict:
        return self._raw.peek(limit=limit)

    def modify_metadata(self, metadata: Metadata) -> None:
        """Merge into the existing metadata. ChromaDB refuses ``hnsw:*`` keys on modify (they are fixed at
        creation and stay in force), so they are left out of the request, not dropped from the collection."""
        merged = {k: v for k, v in {**self.metadata, **metadata}.items() if not k.startswith("hnsw:")}
        self._raw.modify(metadata=merged)
        self.metadata = merged

    @property
    def configuration(self) -> Any:
        """ChromaDB's collection configuration, where the HNSW settings stay in force after a modify."""
        return getattr(self._raw, "configuration", None)


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
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> BaseCollection:

        kwargs: dict = {"name": name, "metadata": collection_provenance(metadata)}
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
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> BaseCollection:

        kwargs: dict = {"name": name, "metadata": collection_provenance(metadata)}
        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function
        try:
            return ChromaDBCollection(self._raw.create_collection(**kwargs))
        except Exception as exc:
            raise ValueError(f"collection already exists: {name}") from exc

    def list_collections(self) -> List[BaseCollection]:
        # Wrap every returned raw chromadb.Collection so callers get
        # a uniform BaseCollection — ChromaDB 1.x returns raw objects,
        # older 0.4.x returns names; wrapping normalises the shape (#5134).
        return [ChromaDBCollection(c) for c in self._raw.list_collections()]

    def delete_collection(self, name: str) -> None:
        try:
            self._raw.delete_collection(name=name)
        except Exception as exc:
            raise ValueError(f"no such collection: {name}") from exc

    def reset(self) -> None:
        self._raw.reset()


__all__ = ["ChromaDBCollection", "ChromaDBClient"]
