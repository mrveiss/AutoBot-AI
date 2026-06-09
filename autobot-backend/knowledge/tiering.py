# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Hot/Warm/Cold Collection Tiering with DiskANN (Issue #8160)

Implements three-tier storage for vector collections based on access frequency:

- **Hot**  (in-memory FAISS): recently/frequently accessed collections.
           Sub-millisecond query latency.
- **Warm** (memory-mapped FAISS on SSD): moderate-use collections that exceed
           the hot-tier memory budget.  Low-single-digit ms latency.
- **Cold** (DiskANN or fallback to file-backed FAISS): rarely accessed
           collections.  Query latency in the 5–50 ms range is acceptable.

Promotion/demotion happens lazily on each query:
- Any query promotes a collection one tier (cold→warm, warm→hot) if access
  frequency crosses a configurable threshold.
- A background reaper runs every REAP_INTERVAL_SECONDS and demotes collections
  whose access timestamps have grown stale.

DiskANN integration
-------------------
When ``diskann`` is importable (requires the ``diskann`` package, or a
compatible library such as ``pydiskann``), the cold tier uses it for
disk-resident ANN search.  When the package is absent, the cold tier falls
back to a file-backed ``faiss.IndexHNSWFlat`` loaded on demand — still
off-heap relative to the hot tier.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    import redis

from autobot_shared.logging_manager import get_logger
from autobot_shared.missing_dep import MissingDep

logger = get_logger(__name__)

# Optional DiskANN import
try:
    import diskann  # type: ignore[import-untyped]

    DISKANN_AVAILABLE = True
except ImportError as _e:
    diskann = MissingDep("diskann", _e)  # type: ignore[assignment]
    DISKANN_AVAILABLE = False

try:
    import faiss  # type: ignore[import-untyped]

    FAISS_AVAILABLE = True
except ImportError as _e:
    faiss = MissingDep("faiss", _e)  # type: ignore[assignment]
    FAISS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOT_MAX_COLLECTIONS = 16
WARM_MAX_COLLECTIONS = 64
PROMOTE_TO_HOT_ACCESSES = 10  # accesses in the last window to go hot
PROMOTE_TO_WARM_ACCESSES = 3  # accesses to go warm
REAP_INTERVAL_SECONDS = 60.0
HOT_STALE_AFTER_SECONDS = 300.0  # demote hot→warm if not accessed in 5 min
WARM_STALE_AFTER_SECONDS = 1800.0  # demote warm→cold if not accessed in 30 min


class Tier(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


@dataclass
class TierEntry:
    """Metadata tracked per collection for tiering decisions."""

    collection_id: str
    tier: Tier = Tier.COLD
    access_count: int = 0
    last_accessed: float = field(default_factory=time.monotonic)
    index: Optional[Any] = None  # in-memory or mmap index handle


# ---------------------------------------------------------------------------
# DiskANN cold-tier index wrapper
# ---------------------------------------------------------------------------


class _DiskANNIndex:
    """Thin wrapper around a DiskANN (or fallback FAISS) cold index."""

    def __init__(self, index_path: str, dim: int) -> None:
        self._path = index_path
        self._dim = dim
        self._handle: Optional[Any] = None

    def load(self) -> None:
        if DISKANN_AVAILABLE:
            self._handle = diskann.load_index(self._path, num_threads=1)
            logger.debug("DiskANN cold index loaded from %s", self._path)
        elif FAISS_AVAILABLE:
            # Fallback: load HNSW index stored on disk
            self._handle = faiss.read_index(self._path)
            logger.debug("FAISS cold index loaded (DiskANN unavailable) from %s", self._path)
        else:
            raise RuntimeError("Neither diskann nor faiss available for cold-tier search")

    def search(self, query: List[float], k: int) -> Tuple[List[int], List[float]]:
        if self._handle is None:
            self.load()
        import numpy as np  # noqa: PLC0415

        q = np.array([query], dtype="float32")
        if DISKANN_AVAILABLE:
            ids, dists = self._handle.search(q, k)
        else:
            dists, ids = self._handle.search(q, k)
        return ids[0].tolist(), dists[0].tolist()

    def unload(self) -> None:
        self._handle = None


# ---------------------------------------------------------------------------
# Tier manager
# ---------------------------------------------------------------------------

_REDIS_PREFIX = "tiering"
_REDIS_TTL = 3600  # seconds; refreshed on each write


class CollectionTierManager:
    """
    Manages hot/warm/cold placement of vector collections.

    Callers notify this manager on each collection access via ``record_access``.
    The manager decides whether the collection should be promoted and, if so,
    loads the appropriate index tier.  ``search`` delegates to whichever
    tier currently holds the collection's index.

    Issue #8408: When ``redis_client`` is supplied the manager backs access counts
    and tier assignments in Redis so all uvicorn workers share state.  Falls back
    to the in-process dict when Redis is unavailable.
    """

    def __init__(
        self,
        hot_max: int = HOT_MAX_COLLECTIONS,
        warm_max: int = WARM_MAX_COLLECTIONS,
        reap_interval: float = REAP_INTERVAL_SECONDS,
        redis_client: Optional["redis.Redis"] = None,
    ) -> None:
        self._hot_max = hot_max
        self._warm_max = warm_max
        self._reap_interval = reap_interval
        self._entries: Dict[str, TierEntry] = {}
        self._lock = asyncio.Lock()
        self._reaper: Optional[asyncio.Task] = None
        # O(1) tier counters — updated on every promote/demote (Issue #8402)
        self._hot_count: int = 0
        self._warm_count: int = 0
        # Pluggable index loaders — set by the caller for each tier
        self._hot_loader: Optional[Any] = None  # callable(collection_id) → index
        self._warm_loader: Optional[Any] = None
        self._cold_loader: Optional[Any] = None  # returns _DiskANNIndex
        # Issue #8408: shared state backend
        self._redis: Optional[Any] = redis_client

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._reaper is None or self._reaper.done():
            self._reaper = asyncio.create_task(self._reap_loop(), name="tiering-reaper")
            logger.info("CollectionTierManager started (hot=%d, warm=%d)", self._hot_max, self._warm_max)

    async def stop(self) -> None:
        if self._reaper and not self._reaper.done():
            self._reaper.cancel()
            try:
                await self._reaper
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_loaders(
        self,
        hot_loader: Any,
        warm_loader: Any,
        cold_loader: Any,
    ) -> None:
        """Register index-loading callables for each tier."""
        self._hot_loader = hot_loader
        self._warm_loader = warm_loader
        self._cold_loader = cold_loader

    # ------------------------------------------------------------------
    # Redis helpers (Issue #8408)
    # ------------------------------------------------------------------

    async def _redis_hincrby(self, key: str, field: str, amount: int = 1) -> Optional[int]:
        """HINCRBY on a Redis hash; refreshes TTL. Returns new value or None on error."""
        if self._redis is None:
            return None
        try:
            val = await asyncio.to_thread(self._redis.hincrby, key, field, amount)
            await asyncio.to_thread(self._redis.expire, key, _REDIS_TTL)
            return int(val)
        except Exception as e:
            logger.warning("Redis HINCRBY %s %s failed: %s", key, field, e)
            return None

    async def _redis_hset(self, key: str, field: str, value: str) -> None:
        """HSET on a Redis hash; refreshes TTL. No-op on error."""
        if self._redis is None:
            return
        try:
            await asyncio.to_thread(self._redis.hset, key, field, value)
            await asyncio.to_thread(self._redis.expire, key, _REDIS_TTL)
        except Exception as e:
            logger.warning("Redis HSET %s %s failed: %s", key, field, e)

    async def _redis_tier_count(self, tier: Tier) -> int:
        """Return count of collections in ``tier`` from Redis; falls back to in-process dict."""
        if self._redis is None:
            return sum(1 for e in self._entries.values() if e.tier == tier)
        try:
            raw = await asyncio.to_thread(self._redis.hget, f"{_REDIS_PREFIX}:counts", tier.value)
            return int(raw) if raw else 0
        except Exception as e:
            logger.warning("Redis HGET counts %s failed: %s", tier.value, e)
            return sum(1 for e in self._entries.values() if e.tier == tier)

    async def _redis_update_tier(self, collection_id: str, old_tier: Tier, new_tier: Tier) -> None:
        """Update the shared tier assignment and adjust hot/warm counters in Redis."""
        await self._redis_hset(f"{_REDIS_PREFIX}:tiers", collection_id, new_tier.value)
        if old_tier == new_tier:
            return
        # Increment new tier count; decrement old tier count (if not COLD, which is the default/uncounted)
        if new_tier in (Tier.HOT, Tier.WARM):
            await self._redis_hincrby(f"{_REDIS_PREFIX}:counts", new_tier.value, 1)
        if old_tier in (Tier.HOT, Tier.WARM):
            await self._redis_hincrby(f"{_REDIS_PREFIX}:counts", old_tier.value, -1)

    async def record_access(self, collection_id: str) -> Tier:
        """
        Record an access to collection_id. May trigger a tier promotion.
        Returns the resulting tier.
        """
        async with self._lock:
            entry = self._entries.setdefault(collection_id, TierEntry(collection_id=collection_id))
            entry.last_accessed = time.monotonic()

            # Issue #8408: use Redis shared counter when available so all workers
            # see the same access frequency, preventing per-worker tier divergence.
            shared_count = await self._redis_hincrby(f"{_REDIS_PREFIX}:access_counts", collection_id, 1)
            entry.access_count = shared_count if shared_count is not None else entry.access_count + 1

            new_tier = self._desired_tier(entry)
            if new_tier != entry.tier:
                await self._promote(entry, new_tier)
            return entry.tier

    async def search(
        self,
        collection_id: str,
        query: List[float],
        k: int = 10,
    ) -> Tuple[List[int], List[float]]:
        """
        Search collection_id using its current tier index.
        Records the access and potentially triggers promotion.
        """
        await self.record_access(collection_id)
        async with self._lock:
            entry = self._entries.get(collection_id)

        if entry is None or entry.index is None:
            raise KeyError(f"Collection {collection_id!r} not loaded in any tier")

        if asyncio.iscoroutinefunction(getattr(entry.index, "search", None)):
            return await entry.index.search(query, k)
        return await asyncio.to_thread(entry.index.search, query, k)

    def tier_of(self, collection_id: str) -> Optional[Tier]:
        entry = self._entries.get(collection_id)
        return entry.tier if entry else None

    def stats(self) -> Dict[str, Any]:
        hot = sum(1 for e in self._entries.values() if e.tier == Tier.HOT)
        warm = sum(1 for e in self._entries.values() if e.tier == Tier.WARM)
        cold = sum(1 for e in self._entries.values() if e.tier == Tier.COLD)
        return {"hot": hot, "warm": warm, "cold": cold, "total": len(self._entries)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _desired_tier(self, entry: TierEntry) -> Tier:
        if entry.access_count >= PROMOTE_TO_HOT_ACCESSES and self._hot_count < self._hot_max:
            return Tier.HOT
        if entry.access_count >= PROMOTE_TO_WARM_ACCESSES and self._warm_count < self._warm_max:
            return Tier.WARM
        return Tier.COLD

    async def _promote(self, entry: TierEntry, new_tier: Tier) -> None:
        old_tier = entry.tier
        loader = {Tier.HOT: self._hot_loader, Tier.WARM: self._warm_loader, Tier.COLD: self._cold_loader}.get(new_tier)
        if loader:
            try:
                if asyncio.iscoroutinefunction(loader):
                    entry.index = await loader(entry.collection_id)
                else:
                    entry.index = await asyncio.to_thread(loader, entry.collection_id)
            except Exception:
                logger.exception("Failed to load %s-tier index for %s", new_tier, entry.collection_id)
                return
        if old_tier == Tier.HOT:
            self._hot_count -= 1
        elif old_tier == Tier.WARM:
            self._warm_count -= 1
        if new_tier == Tier.HOT:
            self._hot_count += 1
        elif new_tier == Tier.WARM:
            self._warm_count += 1
        entry.tier = new_tier
        # Issue #8408: persist tier assignment so other workers see the promotion.
        await self._redis_update_tier(entry.collection_id, old_tier, new_tier)
        logger.info("Collection %s promoted %s→%s", entry.collection_id, old_tier, new_tier)

    async def _demote(self, entry: TierEntry) -> None:
        if entry.tier == Tier.HOT:
            new_tier = Tier.WARM
            self._hot_count -= 1
            self._warm_count += 1
        elif entry.tier == Tier.WARM:
            new_tier = Tier.COLD
            self._warm_count -= 1
        else:
            return
        old_tier = entry.tier
        entry.index = None
        entry.tier = new_tier
        # Issue #8408: persist demotion so other workers see it.
        await self._redis_update_tier(entry.collection_id, old_tier, new_tier)
        logger.info("Collection %s demoted %s→%s (stale)", entry.collection_id, old_tier, new_tier)

    async def _reap_loop(self) -> None:
        while True:
            await asyncio.sleep(self._reap_interval)
            now = time.monotonic()
            async with self._lock:
                for entry in list(self._entries.values()):
                    age = now - entry.last_accessed
                    if entry.tier == Tier.HOT and age > HOT_STALE_AFTER_SECONDS:
                        await self._demote(entry)
                    elif entry.tier == Tier.WARM and age > WARM_STALE_AFTER_SECONDS:
                        await self._demote(entry)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tier_manager: Optional[CollectionTierManager] = None


def get_tier_manager(redis_client: Optional[Any] = None) -> CollectionTierManager:
    """Return the process-singleton CollectionTierManager.

    Issue #8408: pass ``redis_client`` on the first call (typically from lifespan)
    to enable cross-worker Redis-backed tier state.  Subsequent calls without
    ``redis_client`` return the already-configured singleton unchanged.
    """
    global _tier_manager
    if _tier_manager is None:
        _tier_manager = CollectionTierManager(redis_client=redis_client)
    elif redis_client is not None and _tier_manager._redis is None:
        _tier_manager._redis = redis_client
    return _tier_manager
