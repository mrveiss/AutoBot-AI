# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Abstract base classes for pluggable vector-store backends.

Issue #5062: AutoBot's vector-store layer is currently coupled to ChromaDB via
``utils/chromadb_client.py`` and direct ``chromadb`` imports in 10+ call sites.
This module defines backend-agnostic ABCs so Qdrant / LanceDB / pgvector / an
in-memory fake can all be swapped in behind a single interface.

Scope of this module (per PR #5062):
    * Define ``BaseCollection`` and ``BaseClient`` with ChromaDB-compatible
      method signatures (kwargs-only, same return shapes) so existing callers
      can migrate without rewriting their call sites.
    * Production call-site migration is a follow-up.

Return-shape contract (matches ChromaDB 1.x):
    ``get(...)``  -> flat-list dict::
        {"ids": [...], "documents": [...], "metadatas": [...],
         "embeddings": [...] | None, ...}
    ``query(...)`` -> nested-list dict (one inner list per query)::
        {"ids": [[...]], "documents": [[...]], "metadatas": [[...]],
         "distances": [[...]], "embeddings": [[...]] | None, ...}

Any new adapter must honour this shape so existing callers keep working.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence

# Type aliases kept loose on purpose: callers already use plain lists/dicts
# against ChromaDB, so tightening these would break the migration seam.
Embedding = Sequence[float]
Metadata = Dict[str, Any]
Where = Dict[str, Any]
WhereDocument = Dict[str, Any]


class BaseCollection(ABC):
    """Backend-agnostic vector collection interface.

    Method signatures mirror ``chromadb.Collection`` so call sites can switch
    backends without touching keyword arguments. Implementations MUST preserve
    these semantics:

    * ``add`` inserts new items; on duplicate id the backend MAY warn but
      MUST NOT raise (ChromaDB 1.x keeps the original; callers MUST use
      ``upsert`` when they want replace semantics).
    * ``upsert`` inserts or replaces by id with no warning.
    * ``update`` modifies existing ids only; missing ids are a no-op or error
      depending on backend — callers MUST NOT rely on one behaviour.
    * ``get`` returns a flat-list dict (see module docstring).
    * ``query`` returns a nested-list dict — one inner list per query vector.
    * ``delete`` by ids OR by ``where`` filter; at least one must be provided.
    * ``count`` returns the total number of stored items.
    """

    name: str

    @abstractmethod
    def add(
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
    def upsert(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        """Insert-or-replace items by id. No error on duplicate."""

    @abstractmethod
    def update(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        """Modify existing items by id. Missing ids are silently skipped."""

    @abstractmethod
    def get(
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
    def query(
        self,
        *,
        query_embeddings: Sequence[Embedding] | None = None,
        query_texts: Sequence[str] | None = None,
        n_results: int = 10,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
        include: Sequence[str] | None = None,
    ) -> Dict[str, Any]:
        """Vector search. Returns nested-list dict, one inner list per query.

        At least one of ``query_embeddings`` / ``query_texts`` must be given.
        Backends that do not support text-only queries MUST raise
        ``NotImplementedError`` rather than silently returning empty.
        """

    @abstractmethod
    def delete(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
    ) -> None:
        """Delete items by id or filter. At least one filter required."""

    @abstractmethod
    def count(self) -> int:
        """Return total number of stored items."""

    @abstractmethod
    def peek(self, limit: int = 10) -> Dict[str, Any]:
        """Return up to ``limit`` items (any order). Flat-list dict."""


class BaseClient(ABC):
    """Backend-agnostic client / factory for collections.

    Implementations back a persistent or in-memory store and MUST enforce
    unique collection names per client instance.
    """

    @abstractmethod
    def get_or_create_collection(
        self,
        name: str,
        *,
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> BaseCollection:
        """Return existing collection or create a new one."""

    @abstractmethod
    def get_collection(self, name: str) -> BaseCollection:
        """Return existing collection. Raise ``ValueError`` if missing."""

    @abstractmethod
    def create_collection(
        self,
        name: str,
        *,
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> BaseCollection:
        """Create collection. Raise ``ValueError`` if name already exists."""

    @abstractmethod
    def list_collections(self) -> List[BaseCollection]:
        """Return known collections as ``BaseCollection`` instances.

        Adapters MUST wrap any raw backend objects so callers get a
        uniform interface regardless of backend (#5134).
        """

    @abstractmethod
    def delete_collection(self, name: str) -> None:
        """Delete a collection by name. Missing name MUST raise ``ValueError``."""

    @abstractmethod
    def reset(self) -> None:
        """Drop ALL collections. Destructive — guarded by backend config."""


__all__ = [
    "BaseCollection",
    "BaseClient",
    "Embedding",
    "Metadata",
    "Where",
    "WhereDocument",
]
