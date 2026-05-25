# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
HNSW Neighbor-List Prefetch During Graph Traversal (Issue #8161)

HNSW graph traversal follows a beam of candidate nodes across multiple levels.
When the index is larger than the CPU cache (or memory-mapped from disk),
traversal causes cache/page-fault stalls as each node's neighbor list is first
touched during traversal — by which time the CPU is already stalled waiting.

This module implements a two-phase prefetch:

1. **Entry-point warmup** — before the actual search, touch the neighbor lists
   of the entry point and its immediate neighborhood at the highest HNSW level.
   This loads the top-of-graph data into CPU L3/LLC ahead of the traversal.

2. **Speculative prefetch cache** — after a search completes, record which
   nodes were in the result set and pre-touch their level-0 neighborhoods.
   Subsequent near-duplicate queries (common in RAG pipelines) skip the page
   faults because the data is already warm.

The prefetch is best-effort: it silently degrades when the HNSW graph
attributes are unavailable (e.g., FLAT indexes, GPU-resident indexes).

Usage::

    prefetcher = HNSWPrefetcher(index)
    prefetcher.warmup_entry_point()          # call once before search loop
    ids, dists = index.search(query, k)
    prefetcher.speculative_prefetch(ids[0])  # warm cache for follow-up queries
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class HNSWPrefetcher:
    """
    Prefetch HNSW neighbor lists to reduce traversal latency.

    Attach one instance per FAISS ``IndexHNSWFlat`` (or HNSW variant).
    Call ``warmup_entry_point`` before the first search on a query batch
    and ``speculative_prefetch`` after each search to warm the cache for
    expected follow-up traversals.
    """

    def __init__(self, index: Any, max_warmup_nodes: int = 64) -> None:
        """
        Args:
            index: A ``faiss.IndexHNSWFlat`` (or subclass).  The ``hnsw``
                   attribute and ``storage`` sub-index are accessed directly.
            max_warmup_nodes: Cap on number of nodes touched during warmup.
        """
        self._index = index
        self._max_warmup = max_warmup_nodes
        self._hnsw = getattr(index, "hnsw", None)
        self._storage = getattr(index, "storage", index)
        self._enabled = self._hnsw is not None and hasattr(self._hnsw, "neighbor_range")

        if not self._enabled:
            logger.debug("HNSWPrefetcher: HNSW graph attributes not found — prefetch disabled")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def warmup_entry_point(self) -> int:
        """
        Touch the entry-point and its top-level neighbors to warm CPU cache.

        Returns the number of neighbor-list entries touched (0 if disabled).
        """
        if not self._enabled:
            return 0

        try:
            return self._touch_entry_neighbors()
        except Exception:
            logger.debug("HNSW entry-point warmup failed (non-critical)", exc_info=True)
            return 0

    def speculative_prefetch(self, result_ids: Sequence[int], level: int = 0) -> int:
        """
        Pre-touch level-0 neighbor lists for a set of result node IDs.

        Call this immediately after ``index.search`` to pre-warm the
        neighborhoods of returned nodes for likely follow-up traversals.

        Args:
            result_ids: FAISS internal IDs from a previous search result.
            level: HNSW level to prefetch (0 = bottom/densest layer).

        Returns the number of neighbor-list entries touched.
        """
        if not self._enabled:
            return 0

        try:
            return self._touch_neighbors_for_ids(result_ids, level)
        except Exception:
            logger.debug("HNSW speculative prefetch failed (non-critical)", exc_info=True)
            return 0

    def warmup_query_path(self, query: np.ndarray, ef_warmup: int = 8) -> None:
        """
        Lightweight coarse traversal to warm the path a full-efSearch will follow.

        Temporarily lowers ``efSearch`` to *ef_warmup* and executes a throwaway
        search so the OS/CPU prefetcher sees the access pattern and starts
        loading ahead.  Restores original ``efSearch`` afterwards.

        This is most effective when the index is memory-mapped from disk and the
        OS prefetch window is small relative to HNSW fan-out.
        """
        if not self._enabled:
            return

        original_ef = getattr(self._hnsw, "efSearch", None)
        if original_ef is None:
            return

        try:
            self._hnsw.efSearch = max(1, ef_warmup)
            q = np.ascontiguousarray(query.reshape(1, -1).astype(np.float32))
            self._index.search(q, 1)
        except Exception:
            logger.debug("HNSW query-path warmup failed (non-critical)", exc_info=True)
        finally:
            self._hnsw.efSearch = original_ef

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _touch_entry_neighbors(self) -> int:
        """Touch neighbor list of the HNSW entry point at the top level."""
        entry = getattr(self._hnsw, "entry_point", -1)
        if entry < 0:
            return 0

        max_level = getattr(self._hnsw, "max_level", 0)
        touched = 0

        # Walk from the top level down to level 1; prefetch each level's neighbors
        for lv in range(max_level, 0, -1):
            begin, end = self._hnsw.neighbor_range(entry, lv)
            neighbors_slice = self._hnsw.neighbors[begin:end]
            # The slice access itself loads the memory into CPU cache
            touched += len(neighbors_slice)
            if touched >= self._max_warmup:
                break

            # Follow first valid neighbor one hop deeper
            if len(neighbors_slice) > 0 and neighbors_slice[0] >= 0:
                entry = int(neighbors_slice[0])

        return touched

    def _touch_neighbors_for_ids(self, node_ids: Sequence[int], level: int) -> int:
        """Touch the level-*level* neighbor lists for each node in node_ids."""
        touched = 0
        for nid in node_ids:
            if nid < 0:
                continue
            try:
                begin, end = self._hnsw.neighbor_range(int(nid), level)
                _ = self._hnsw.neighbors[begin:end]
                touched += end - begin
            except Exception:
                continue
            if touched >= self._max_warmup * len(node_ids):
                break
        return touched


def attach_prefetcher(index: Any, max_warmup_nodes: int = 64) -> Optional[HNSWPrefetcher]:
    """
    Return an ``HNSWPrefetcher`` for *index* if it is HNSW-backed, else None.

    Convenience factory used by ``GPUVectorIndex.search`` to avoid touching
    the HNSW attributes on non-HNSW indexes.
    """
    if getattr(index, "hnsw", None) is not None:
        return HNSWPrefetcher(index, max_warmup_nodes=max_warmup_nodes)
    return None
