# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one definition of a knowledge chunk's identity (#18142).

A graph node joins to a vector chunk by id, so every module must read the same id off a
chunk. It used to be derived eight ways (``metadata.chunk_id``, ``source_path``, an md5 prefix
that was the Chroma id but never stored, ...), so two modules disagreed about which chunk a
result was and the join silently missed.

Writers stamp their store id into ``metadata["chunk_id"]`` (:func:`stamp_chunk_id`); readers call
:func:`resolve_chunk_id`. Chunks written before the stamp existed are NOT rewritten: the
resolver rebuilds their id from the metadata they already carry (:func:`legacy_chunk_id`), so a
legacy chunk and a re-indexed copy of it resolve to the same id.

Precedence, fixed (first non-empty wins):

1. ``metadata["chunk_id"]``        -- stored at write time; the only id that is a fact, not a guess
2. ``metadata["chunk_store_id"]``  -- the store row id a retriever carried through for a row with no
                                      stamp; the only way to tell oversize split siblings
                                      (``base_L0`` / ``base_R0``) apart, as their metadata is equal
3. top-level ``chunk_id``          -- a result already normalised by a retriever or reranker
4. the rebuilt legacy id           -- doc / seed chunks written before the stamp (no data rewrite)
5. ``source_path``                 -- last resort; identifies the file, not the chunk
6. ``""``
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

DOC_SOURCE = "autobot_documentation"
DOC_SEARCH_SOURCE = "autobot_docs"  # what DocIndexerService.search relabels a doc hit's source to
STORE_ID_KEY = "chunk_store_id"
SEED_SOURCE = "cognition_store"
DOC_ID_LENGTH = 12  # oversize splits append "_L<depth>" / "_R<depth>" to the base id
SEED_ID_LENGTH = 16


def _md5_prefix(key: str, length: int) -> str:
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:length]


def doc_chunk_id(rel_path: str, section: str, index: int) -> str:
    """Id of a documentation chunk before any oversize split."""
    return _md5_prefix(f"{rel_path}:{section}:{index}", DOC_ID_LENGTH)


def seed_chunk_id(collection: str, rel_path: str, index: int) -> str:
    """Id of a cognition-seed chunk."""
    return _md5_prefix(f"seed:{collection}:{rel_path}:{index}", SEED_ID_LENGTH)


def stamp_chunk_id(metadata: Mapping[str, Any], chunk_id: str) -> dict[str, Any]:
    """Copy of *metadata* carrying the store id; call at the single write point of an indexer."""
    return {**metadata, "chunk_id": chunk_id}


def carry_store_id(metadata: Mapping[str, Any], row_id: str) -> dict[str, Any]:
    """Copy of a retrieved row's *metadata* carrying its store row id; a read-side copy, never a write."""
    return {**metadata, STORE_ID_KEY: row_id} if row_id else dict(metadata)


def legacy_chunk_id(metadata: Mapping[str, Any]) -> str:
    """Rebuild the id of a chunk written before ``chunk_id`` was stored; ``""`` when not derivable."""
    source = metadata.get("source")
    try:
        if source in (DOC_SOURCE, DOC_SEARCH_SOURCE):
            return doc_chunk_id(metadata["file_path"], metadata["section"], int(metadata["chunk_index"]))
        if source == SEED_SOURCE:
            return seed_chunk_id(metadata["seed_collection"], metadata["relative_path"], int(metadata["chunk_index"]))
    except (KeyError, TypeError, ValueError):
        return ""
    return ""


def _read(result: Any, name: str, default: Any) -> Any:
    if isinstance(result, Mapping):
        return result.get(name) or default
    return getattr(result, name, None) or default


def resolve_chunk_id(result: Any) -> str:
    """The canonical chunk id of a result dict or ``SearchResult``/``RankedResult``-like object."""
    metadata = _read(result, "metadata", {})
    return str(
        metadata.get("chunk_id")
        or metadata.get(STORE_ID_KEY)
        or _read(result, "chunk_id", "")
        or legacy_chunk_id(metadata)
        or _read(result, "source_path", "")
    )
