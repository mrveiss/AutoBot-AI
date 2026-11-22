# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one stale filter every retrieval path applies (#4689, #18141, #19280).

Two kinds of retrieved item, two staleness rules, one module:

* **Indexed document chunk** -- a chunk the doc indexer wrote (``metadata.source`` is one of
  :data:`DOC_INDEX_SOURCES`). It is stale when its file (``metadata.file_path``) is absent from
  the doc indexer's hash cache: removed or moved since the last index run (#4689). Only the doc
  indexer's own chunks are judged by its cache. A KB fact, a connector document or a graph
  entity is not in that cache because it was never indexed there, not because it was removed;
  judging it by the cache drops every one of them (#19280).
* **Graph-expanded KAG entity** -- a memory-graph entity reached over a relation. It is stale
  when the entity or that relation has been superseded or has expired, i.e. its validity window
  (``valid_from`` / ``valid_to``, ``is_active``) is closed. That is judged by the one serving
  predicate :func:`knowledge.serving.is_servable` (#18829), never by the hash cache.

Callers: ``RAGService`` (vector, mesh and fallback branches), ``GraphRAGService`` (KAG
expansion) and ``POST /knowledge/search``.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, List, TypeVar

from autobot_shared.env_registry import env
from autobot_shared.logging_manager import get_logger
from knowledge.chunk_identity import DOC_SEARCH_SOURCE, DOC_SOURCE
from knowledge.serving import is_servable

logger = get_logger(__name__)

T = TypeVar("T")

#: Seconds the doc indexer's hash cache is reused before it is re-read from disk.
HASH_CACHE_TTL_SECONDS: float = env("AUTOBOT_DOC_HASH_CACHE_TTL_SECONDS")
#: ``metadata.source`` values of chunks the doc indexer wrote -- the only chunks its cache can judge.
DOC_INDEX_SOURCES = frozenset({DOC_SOURCE, DOC_SEARCH_SOURCE})
#: Stale paths quoted in one log line, to keep the line bounded.
STALE_LOG_SAMPLE = 10

_cache: dict[str, Any] = {"paths": {}, "loaded_at": None}


def reset_hash_cache() -> None:
    """Forget the memoised hash cache so the next call re-reads it."""
    _cache.update(paths={}, loaded_at=None)


def _field(item: Any, name: str) -> Any:
    """*name* from a mapping key or an attribute, else ``None``."""
    return item.get(name) if isinstance(item, Mapping) else getattr(item, name, None)


def indexed_path(item: Any) -> str:
    """The doc-index file *item* was chunked from; ``""`` when the doc indexer did not write it."""
    metadata = _field(item, "metadata") or {}
    if metadata.get("source") not in DOC_INDEX_SOURCES:
        return ""
    return str(metadata.get("file_path") or _field(item, "source_path") or "")


def _read_hash_cache(path: Path) -> dict:
    """The hash cache file as ``{rel_path: hash}``; empty when absent or unreadable."""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
    except (OSError, ValueError) as exc:
        logger.warning("Doc hash cache unreadable (skipping provenance check): %s", exc)
        return {}
    return loaded if isinstance(loaded, dict) else {}


async def _indexed_paths() -> dict:
    """The doc indexer's hash cache, memoised for :data:`HASH_CACHE_TTL_SECONDS`."""
    try:
        from services.knowledge.doc_indexer import HASH_CACHE_FILE
        from services.knowledge.index_cache_paths import doc_index_hashes
    except ImportError as exc:
        logger.debug("Doc indexer unavailable (skipping provenance check): %s", exc)
        return {}
    now = time.monotonic()
    loaded_at = _cache["loaded_at"]
    if loaded_at is None or now - loaded_at > HASH_CACHE_TTL_SECONDS:
        _cache.update(paths=await asyncio.to_thread(_read_hash_cache, doc_index_hashes(HASH_CACHE_FILE)), loaded_at=now)
    return _cache["paths"]


async def drop_stale(items: Iterable[T]) -> List[T]:
    """*items* without the doc-index chunks whose file has left the index, order preserved.

    An empty or unavailable hash cache (indexer not run yet) filters nothing, so a fresh
    deployment never loses every doc chunk. Works on ``RankedResult`` objects and result dicts.
    """
    pool = list(items)
    if not any(indexed_path(item) for item in pool):
        return pool
    paths = await _indexed_paths()
    if not paths:
        return pool
    kept = [item for item in pool if not indexed_path(item) or indexed_path(item) in paths]
    if len(kept) != len(pool):
        stale = [indexed_path(item) for item in pool if indexed_path(item) and indexed_path(item) not in paths]
        logger.warning(
            "Provenance check: dropped %d stale chunk(s) -- source paths absent from hash cache: %s",
            len(stale),
            stale[:STALE_LOG_SAMPLE],
        )
    return kept


def graph_item_is_fresh(item: Mapping[str, Any]) -> bool:
    """Whether a traversal hit's entity AND the relation that reached it are both still valid."""
    return is_servable(item.get("entity") or {}) and is_servable(item.get("relation") or {})


def fresh_graph_items(items: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Traversal hits (``{entity, relation, direction}``) without the stale ones, order preserved."""
    pool = list(items)
    kept = [item for item in pool if graph_item_is_fresh(item)]
    if len(kept) != len(pool):
        logger.info("KAG staleness: dropped %d of %d graph-expanded entities", len(pool) - len(kept), len(pool))
    return kept
