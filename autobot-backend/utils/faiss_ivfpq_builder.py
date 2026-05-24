# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""FAISS IVFPQ index builder with training, persistence, and recall benchmarking."""

import asyncio
import os
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# IVFPQ parameters tuned for autobot_memory (~545K vectors, 768-dim)
IVFPQ_NLIST = 1024  # ~sqrt(545K) centroids
IVFPQ_M_PQ = 96  # 768-dim / 8 = 96 sub-vectors
IVFPQ_NBITS = 8  # 8-bit codes
IVFPQ_NPROBE = 64  # probe 6% of cells
IVFPQ_TRAIN_SAMPLE = 100_000  # training sample size

# Minimum training vectors per FAISS rule of thumb (nlist * 39)
_MIN_TRAIN_FACTOR = 39

try:
    import faiss  # type: ignore

    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False


class FAISSIVFPQBuilder:
    """Builds, trains, and persists a FAISS IndexIVFPQ index."""

    def __init__(self, dim: int, index_dir: str, collection_name: str) -> None:
        self.dim = dim
        self.index_dir = index_dir
        self.collection_name = collection_name

    def _index_path(self) -> Path:
        """Return path to persisted index file."""
        return Path(self.index_dir) / f"{self.collection_name}_ivfpq_d{self.dim}_n{IVFPQ_NLIST}.index"

    async def build_or_load(self, vectors: np.ndarray) -> Optional[Any]:
        """Load persisted index or train a new one from vectors."""
        if not _FAISS_AVAILABLE:
            logger.warning("faiss not available — IVFPQ index disabled")
            return None

        existing = await self.load()
        if existing is not None:
            logger.info("FAISSIVFPQBuilder: loaded persisted index from %s", self._index_path())
            return existing

        return await self.train_and_build(vectors)

    async def train_and_build(self, vectors: np.ndarray) -> Optional[Any]:
        """Train IVFPQ index on vectors and persist it."""
        if not _FAISS_AVAILABLE:
            logger.warning("faiss not available — skipping IVFPQ training")
            return None

        try:
            index = await asyncio.to_thread(self._train_sync, vectors)
            if index is None:
                return None

            path = self._index_path()
            await asyncio.to_thread(self._persist_sync, index, path)
            logger.info("FAISSIVFPQBuilder: trained and persisted IVFPQ index to %s", path)
            return index
        except Exception as exc:
            logger.warning("FAISSIVFPQBuilder: training failed (%s) — no index", exc)
            return None

    def _train_sync(self, vectors: np.ndarray) -> Optional[Any]:
        """Synchronous training logic executed in a thread."""
        min_required = IVFPQ_NLIST * _MIN_TRAIN_FACTOR
        n_vectors = len(vectors)

        if n_vectors < min_required:
            logger.warning(
                "FAISSIVFPQBuilder: only %d vectors provided but IVFPQ requires"
                " at least %d (nlist=%d * %d); training may be poor quality",
                n_vectors,
                min_required,
                IVFPQ_NLIST,
                _MIN_TRAIN_FACTOR,
            )

        # Sub-sample for training if needed
        if n_vectors > IVFPQ_TRAIN_SAMPLE:
            rng = np.random.default_rng(seed=42)
            idx = rng.choice(n_vectors, IVFPQ_TRAIN_SAMPLE, replace=False)
            train_vectors = np.ascontiguousarray(vectors[idx], dtype=np.float32)
        else:
            train_vectors = np.ascontiguousarray(vectors, dtype=np.float32)

        quantizer = faiss.IndexFlatIP(self.dim)
        index = faiss.IndexIVFPQ(quantizer, self.dim, IVFPQ_NLIST, IVFPQ_M_PQ, IVFPQ_NBITS)
        index.train(train_vectors)
        index.add(np.ascontiguousarray(vectors, dtype=np.float32))
        index.nprobe = IVFPQ_NPROBE
        return index

    def _persist_sync(self, index: Any, path: Path) -> None:
        """Write index to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(path))

    async def load(self) -> Optional[Any]:
        """Load persisted index from disk."""
        if not _FAISS_AVAILABLE:
            return None

        path = self._index_path()
        if not path.exists():
            return None

        try:
            index = await asyncio.to_thread(faiss.read_index, str(path))
            index.nprobe = IVFPQ_NPROBE
            return index
        except Exception as exc:
            logger.warning("FAISSIVFPQBuilder: could not load index from %s (%s)", path, exc)
            return None

    async def search(self, index: Any, query: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        """Search index returning (distances, indices)."""
        query_2d = np.ascontiguousarray(query.reshape(1, -1) if query.ndim == 1 else query, dtype=np.float32)
        distances, indices = await asyncio.to_thread(index.search, query_2d, k)
        return distances, indices

    def benchmark_recall(
        self,
        flat_index: Any,
        ivfpq_index: Any,
        queries: np.ndarray,
        k: int = 10,
    ) -> float:
        """Compute recall@k of IVFPQ vs flat ground truth.

        Returns fraction of top-k IDs returned by IVFPQ that appear in the
        flat (exact) result set, averaged across all query vectors.
        """
        queries_f32 = np.ascontiguousarray(queries, dtype=np.float32)
        if queries_f32.ndim == 1:
            queries_f32 = queries_f32.reshape(1, -1)

        _, flat_ids = flat_index.search(queries_f32, k)
        _, ivfpq_ids = ivfpq_index.search(queries_f32, k)

        total_hits = 0
        for flat_row, ivfpq_row in zip(flat_ids, ivfpq_ids):
            flat_set = set(flat_row.tolist())
            hits = sum(1 for i in ivfpq_row if i != -1 and i in flat_set)
            total_hits += hits

        n_queries = queries_f32.shape[0]
        recall = total_hits / (n_queries * k) if n_queries and k else 0.0
        logger.info(
            "FAISSIVFPQBuilder: recall@%d = %.4f over %d queries",
            k,
            recall,
            n_queries,
        )
        return recall
