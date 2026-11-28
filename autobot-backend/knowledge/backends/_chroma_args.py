# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The argument shapes ChromaDB expects, shared by the sync and async adapters (#18557).

Pure functions only: each adapter still makes its own call, sync or awaited.
"""

from __future__ import annotations

from typing import Any, Sequence

from autobot_shared.time_utils import utc_timestamp


def optional_list(values: Sequence[Any] | None) -> list | None:
    """A list copy of *values*, keeping ``None`` as ``None``."""
    return list(values) if values is not None else None


def write_args(
    ids: Sequence[str],
    documents: Sequence[str] | None,
    metadatas: Sequence[Any] | None,
    embeddings: Sequence[Any] | None,
) -> dict:
    """Arguments for ``add``, ``upsert`` and ``update``."""
    return {
        "ids": list(ids),
        "documents": optional_list(documents),
        "metadatas": optional_list(metadatas),
        "embeddings": optional_list(embeddings),
    }


def filter_args(ids: Any = None, where: Any = None, where_document: Any = None) -> dict:
    """The record filters a caller set; an unset one is left out."""
    kwargs: dict = {}
    if ids is not None:
        kwargs["ids"] = list(ids)
    if where is not None:
        kwargs["where"] = where
    if where_document is not None:
        kwargs["where_document"] = where_document
    return kwargs


def get_args(ids: Any, where: Any, where_document: Any, limit: Any, offset: Any, include: Any) -> dict:
    """Arguments for ``get``, passing only what the caller set."""
    kwargs = filter_args(ids, where, where_document)
    if limit is not None:
        kwargs["limit"] = limit
    if offset is not None:
        kwargs["offset"] = offset
    if include is not None:
        kwargs["include"] = list(include)
    return kwargs


def query_args(
    query_embeddings: Any, query_texts: Any, n_results: int, where: Any, where_document: Any, include: Any
) -> dict:
    """Arguments for ``query``, passing only what the caller set."""
    kwargs: dict = {"n_results": n_results}
    if query_embeddings is not None:
        kwargs["query_embeddings"] = [list(e) for e in query_embeddings]
    if query_texts is not None:
        kwargs["query_texts"] = list(query_texts)
    kwargs.update(filter_args(where=where, where_document=where_document))
    if include is not None:
        kwargs["include"] = list(include)
    return kwargs


def delete_args(ids: Any, where: Any, where_document: Any) -> dict:
    """Arguments for ``delete``, which refuses to run with no filter at all."""
    kwargs = filter_args(ids, where, where_document)
    if not kwargs:
        raise ValueError("delete requires ids or where")
    return kwargs


def collection_provenance(metadata: dict | None) -> dict:
    """A new collection's metadata: its creation time, then the caller's values."""
    provenance: dict = {"created_at": utc_timestamp()}
    if metadata:
        provenance.update(metadata)
    return provenance
