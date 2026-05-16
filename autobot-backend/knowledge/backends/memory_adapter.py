# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
In-memory vector-store backend for unit tests (Issue #5062).

Provides a deterministic, dependency-free implementation of ``BaseCollection``
and ``BaseClient`` for tests that would otherwise spin up a real ChromaDB
instance. Not intended for production use.

Semantics match the contract documented in ``knowledge.backends.base``:
    * ``add`` is a no-op on duplicate ids (ChromaDB 1.x behaviour).
    * ``upsert`` is idempotent.
    * ``query`` uses brute-force cosine distance when embeddings are supplied.
    * ``get`` returns flat-list dicts; ``query`` returns nested-list dicts.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence

from knowledge.backends.base import (
    BaseClient,
    BaseCollection,
    Embedding,
    Metadata,
    Where,
    WhereDocument,
)


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Return 1 - cosine_similarity. Matches ChromaDB's default 'l2'-ish
    ordering intent: lower is more similar. Zero-vectors get distance 1.0.
    """
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    if da == 0 or db == 0:
        return 1.0
    return 1.0 - (num / (da * db))


def _match_where(meta: Metadata | None, where: Where | None) -> bool:
    """Minimal ``where`` filter: equality on top-level keys only.

    Full ChromaDB where syntax (``$and``, ``$or``, ``$in`` ...) is out of
    scope for the in-memory fake — tests that need it should use ChromaDB
    directly or extend this helper.
    """
    if not where:
        return True
    if meta is None:
        return False
    for key, expected in where.items():
        if meta.get(key) != expected:
            return False
    return True


class InMemoryCollection(BaseCollection):
    """Deterministic in-memory implementation of ``BaseCollection``."""

    def __init__(self, name: str, metadata: Metadata | None = None) -> None:
        self.name = name
        self.metadata = metadata or {}
        # Parallel dicts keyed by id — keeps add/upsert/update O(1).
        self._documents: Dict[str, str | None] = {}
        self._metadatas: Dict[str, Metadata | None] = {}
        self._embeddings: Dict[str, List[float] | None] = {}

    # ------------------------------------------------------------------ helpers

    def _store(
        self,
        ids: Sequence[str],
        documents: Sequence[str] | None,
        metadatas: Sequence[Metadata] | None,
        embeddings: Sequence[Embedding] | None,
        *,
        allow_overwrite: bool,
    ) -> None:
        if documents is not None and len(documents) != len(ids):
            raise ValueError("documents length mismatch with ids")
        if metadatas is not None and len(metadatas) != len(ids):
            raise ValueError("metadatas length mismatch with ids")
        if embeddings is not None and len(embeddings) != len(ids):
            raise ValueError("embeddings length mismatch with ids")

        for i, _id in enumerate(ids):
            exists = _id in self._documents
            # Match ChromaDB 1.x: add() on a duplicate id retains the
            # original record. Only upsert / update may overwrite.
            if exists and not allow_overwrite:
                continue
            if documents is not None:
                self._documents[_id] = documents[i]
            elif not exists:
                self._documents[_id] = None
            if metadatas is not None:
                self._metadatas[_id] = dict(metadatas[i]) if metadatas[i] else None
            elif not exists:
                self._metadatas[_id] = None
            if embeddings is not None:
                self._embeddings[_id] = list(embeddings[i])
            elif not exists:
                self._embeddings[_id] = None

    # -------------------------------------------------------------- write ops

    def add(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        self._store(ids, documents, metadatas, embeddings, allow_overwrite=False)

    def upsert(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        self._store(ids, documents, metadatas, embeddings, allow_overwrite=True)

    def update(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str] | None = None,
        metadatas: Sequence[Metadata] | None = None,
        embeddings: Sequence[Embedding] | None = None,
    ) -> None:
        # Build id → index map, detect duplicates in the same call.
        # list.index() only returns the first occurrence, so duplicate ids
        # in a single update call would silently reuse the first entry's
        # aligned values instead of surfacing the caller's mistake (#5133).
        id_to_idx: Dict[str, int] = {}
        for i, _id in enumerate(ids):
            if _id in id_to_idx:
                raise ValueError(f"duplicate id in single update call: {_id}")
            id_to_idx[_id] = i

        existing_ids = [_id for _id in ids if _id in self._documents]
        if not existing_ids:
            return
        idx = [id_to_idx[_id] for _id in existing_ids]

        def _pick(seq: Sequence[Any] | None) -> List[Any] | None:
            return [seq[i] for i in idx] if seq is not None else None

        self._store(
            existing_ids,
            _pick(documents),
            _pick(metadatas),
            _pick(embeddings),
            allow_overwrite=True,
        )

    # ------------------------------------------------------------- read ops

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
        include = list(include) if include is not None else ["documents", "metadatas"]
        candidate_ids: List[str] = list(ids) if ids is not None else list(self._documents.keys())
        filtered = [
            _id for _id in candidate_ids if _id in self._documents and _match_where(self._metadatas.get(_id), where)
        ]
        if offset:
            filtered = filtered[offset:]
        if limit is not None:
            filtered = filtered[:limit]

        result: Dict[str, Any] = {"ids": filtered}
        if "documents" in include:
            result["documents"] = [self._documents.get(_id) for _id in filtered]
        if "metadatas" in include:
            result["metadatas"] = [self._metadatas.get(_id) for _id in filtered]
        if "embeddings" in include:
            result["embeddings"] = [self._embeddings.get(_id) for _id in filtered]
        return result

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
        if query_embeddings is None and query_texts is None:
            raise ValueError("either query_embeddings or query_texts is required")
        if query_embeddings is None:
            # The fake has no embedding function. Surface the limitation
            # loudly so tests that need text queries don't get silent passes.
            raise NotImplementedError(
                "InMemoryCollection requires query_embeddings; text-only " "queries need a real embedding backend"
            )
        include = list(include) if include is not None else ["documents", "metadatas", "distances"]

        candidate_ids = [_id for _id in self._documents.keys() if _match_where(self._metadatas.get(_id), where)]

        out_ids: List[List[str]] = []
        out_docs: List[List[str | None]] = []
        out_metas: List[List[Metadata | None]] = []
        out_dist: List[List[float]] = []
        out_embs: List[List[List[float] | None]] = []

        for q_vec in query_embeddings:
            scored = []
            for _id in candidate_ids:
                emb = self._embeddings.get(_id)
                dist = _cosine_distance(q_vec, emb) if emb is not None else 1.0
                scored.append((dist, _id))
            scored.sort(key=lambda pair: pair[0])
            top = scored[:n_results]
            out_ids.append([_id for _, _id in top])
            out_docs.append([self._documents.get(_id) for _, _id in top])
            out_metas.append([self._metadatas.get(_id) for _, _id in top])
            out_dist.append([dist for dist, _ in top])
            out_embs.append([self._embeddings.get(_id) for _, _id in top])

        result: Dict[str, Any] = {"ids": out_ids}
        if "documents" in include:
            result["documents"] = out_docs
        if "metadatas" in include:
            result["metadatas"] = out_metas
        if "distances" in include:
            result["distances"] = out_dist
        if "embeddings" in include:
            result["embeddings"] = out_embs
        return result

    def delete(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Where | None = None,
        where_document: WhereDocument | None = None,
    ) -> None:
        if ids is None and where is None:
            raise ValueError("delete requires ids or where")
        target = list(ids) if ids is not None else list(self._documents.keys())
        for _id in target:
            if _id not in self._documents:
                continue
            if where and not _match_where(self._metadatas.get(_id), where):
                continue
            self._documents.pop(_id, None)
            self._metadatas.pop(_id, None)
            self._embeddings.pop(_id, None)

    def count(self) -> int:
        return len(self._documents)

    def peek(self, limit: int = 10) -> Dict[str, Any]:
        ids = list(self._documents.keys())[:limit]
        return {
            "ids": ids,
            "documents": [self._documents[_id] for _id in ids],
            "metadatas": [self._metadatas[_id] for _id in ids],
            "embeddings": [self._embeddings[_id] for _id in ids],
        }


class InMemoryClient(BaseClient):
    """Deterministic in-memory implementation of ``BaseClient``."""

    def __init__(self) -> None:
        self._collections: Dict[str, InMemoryCollection] = {}

    def get_or_create_collection(
        self,
        name: str,
        *,
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> BaseCollection:
        col = self._collections.get(name)
        if col is None:
            col = InMemoryCollection(name=name, metadata=metadata)
            self._collections[name] = col
        return col

    def get_collection(self, name: str) -> BaseCollection:
        col = self._collections.get(name)
        if col is None:
            raise ValueError(f"no such collection: {name}")
        return col

    def create_collection(
        self,
        name: str,
        *,
        metadata: Metadata | None = None,
        embedding_function: Any | None = None,
    ) -> BaseCollection:
        if name in self._collections:
            raise ValueError(f"collection already exists: {name}")
        col = InMemoryCollection(name=name, metadata=metadata)
        self._collections[name] = col
        return col

    def list_collections(self) -> List[BaseCollection]:
        return list(self._collections.values())

    def delete_collection(self, name: str) -> None:
        if name not in self._collections:
            raise ValueError(f"no such collection: {name}")
        del self._collections[name]

    def reset(self) -> None:
        self._collections.clear()


__all__ = ["InMemoryCollection", "InMemoryClient"]
