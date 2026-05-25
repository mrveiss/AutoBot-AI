# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for FAISSIVFPQBuilder — build_or_load, benchmark_recall, index persistence."""

import asyncio
from unittest.mock import patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vectors(n: int, dim: int = 64) -> np.ndarray:
    rng = np.random.default_rng(seed=0)
    return rng.random((n, dim)).astype(np.float32)


# ---------------------------------------------------------------------------
# Fixture: builder with small parameters to keep tests fast
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_index_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture()
def builder(tmp_index_dir):
    from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

    # Patch IVFPQ_NLIST to a small value so tests train quickly
    with (
        patch("utils.faiss_ivfpq_builder.IVFPQ_NLIST", 8),
        patch("utils.faiss_ivfpq_builder.IVFPQ_M_PQ", 8),
        patch("utils.faiss_ivfpq_builder.IVFPQ_NBITS", 8),
        patch("utils.faiss_ivfpq_builder.IVFPQ_NPROBE", 4),
        patch("utils.faiss_ivfpq_builder.IVFPQ_TRAIN_SAMPLE", 500),
    ):
        yield FAISSIVFPQBuilder(dim=64, index_dir=tmp_index_dir, collection_name="test_col")


# ---------------------------------------------------------------------------
# Skip guard — skip all tests when faiss is not installed
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def require_faiss():
    pytest.importorskip("faiss", reason="faiss not installed — skipping IVFPQ tests")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFAISSIVFPQBuilderIndexPath:
    def test_index_path_contains_dim_and_nlist(self, tmp_index_dir):
        from utils.faiss_ivfpq_builder import IVFPQ_NLIST, FAISSIVFPQBuilder

        b = FAISSIVFPQBuilder(dim=768, index_dir=tmp_index_dir, collection_name="autobot_memory")
        path = b._index_path()
        assert "autobot_memory" in path.name
        assert "d768" in path.name
        assert f"n{IVFPQ_NLIST}" in path.name
        assert path.suffix == ".index"

    def test_index_path_inside_index_dir(self, tmp_index_dir):
        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        b = FAISSIVFPQBuilder(dim=64, index_dir=tmp_index_dir, collection_name="col")
        assert str(b._index_path()).startswith(tmp_index_dir)


class TestBuildOrLoad:
    def test_train_and_build_creates_index(self, tmp_index_dir):
        """build_or_load trains a new index when no persisted file exists."""
        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        with (
            patch("utils.faiss_ivfpq_builder.IVFPQ_NLIST", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_M_PQ", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_NBITS", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_NPROBE", 4),
            patch("utils.faiss_ivfpq_builder.IVFPQ_TRAIN_SAMPLE", 500),
        ):
            b = FAISSIVFPQBuilder(dim=64, index_dir=tmp_index_dir, collection_name="c1")
            vectors = _make_vectors(600, 64)
            index = asyncio.run(b.build_or_load(vectors))

        assert index is not None
        assert index.is_trained

    def test_build_or_load_returns_existing_on_second_call(self, tmp_index_dir):
        """Second call loads persisted index instead of retraining."""
        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        with (
            patch("utils.faiss_ivfpq_builder.IVFPQ_NLIST", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_M_PQ", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_NBITS", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_NPROBE", 4),
            patch("utils.faiss_ivfpq_builder.IVFPQ_TRAIN_SAMPLE", 500),
        ):
            b = FAISSIVFPQBuilder(dim=64, index_dir=tmp_index_dir, collection_name="c2")
            vectors = _make_vectors(600, 64)
            index1 = asyncio.run(b.build_or_load(vectors))
            assert b._index_path().exists(), "index file must be persisted after first call"

            index2 = asyncio.run(b.build_or_load(vectors))

        # Both should be valid trained indexes
        assert index1 is not None and index2 is not None
        assert index1.is_trained and index2.is_trained

    def test_build_or_load_returns_none_when_faiss_unavailable(self, tmp_index_dir):
        """Graceful fallback when faiss is not importable."""
        from utils import faiss_ivfpq_builder

        original = faiss_ivfpq_builder._FAISS_AVAILABLE
        faiss_ivfpq_builder._FAISS_AVAILABLE = False
        try:
            b = faiss_ivfpq_builder.FAISSIVFPQBuilder(dim=64, index_dir=tmp_index_dir, collection_name="c3")
            result = asyncio.run(b.build_or_load(_make_vectors(100, 64)))
            assert result is None
        finally:
            faiss_ivfpq_builder._FAISS_AVAILABLE = original

    def test_insufficient_vectors_logs_warning(self, tmp_index_dir, caplog):
        """Warning is logged when fewer vectors than nlist * 39 are supplied."""
        import logging

        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        with (
            patch("utils.faiss_ivfpq_builder.IVFPQ_NLIST", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_M_PQ", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_NBITS", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_NPROBE", 4),
            patch("utils.faiss_ivfpq_builder.IVFPQ_TRAIN_SAMPLE", 500),
            caplog.at_level(logging.WARNING, logger="utils.faiss_ivfpq_builder"),
        ):
            b = FAISSIVFPQBuilder(dim=64, index_dir=tmp_index_dir, collection_name="c4")
            # 8 * 39 = 312 required; supply only 50
            asyncio.run(b.build_or_load(_make_vectors(50, 64)))

        assert any("requires" in r.message for r in caplog.records)


class TestPersistence:
    def test_index_file_written_after_train(self, tmp_index_dir):
        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        with (
            patch("utils.faiss_ivfpq_builder.IVFPQ_NLIST", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_M_PQ", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_NBITS", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_NPROBE", 4),
            patch("utils.faiss_ivfpq_builder.IVFPQ_TRAIN_SAMPLE", 500),
        ):
            b = FAISSIVFPQBuilder(dim=64, index_dir=tmp_index_dir, collection_name="persist_col")
            vectors = _make_vectors(600, 64)
            asyncio.run(b.train_and_build(vectors))

        assert b._index_path().exists()
        assert b._index_path().stat().st_size > 0

    def test_load_returns_none_when_file_missing(self, tmp_index_dir):
        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        b = FAISSIVFPQBuilder(dim=64, index_dir=tmp_index_dir, collection_name="no_file")
        result = asyncio.run(b.load())
        assert result is None

    def test_load_returns_index_when_file_present(self, tmp_index_dir):
        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        with (
            patch("utils.faiss_ivfpq_builder.IVFPQ_NLIST", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_M_PQ", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_NBITS", 8),
            patch("utils.faiss_ivfpq_builder.IVFPQ_NPROBE", 4),
            patch("utils.faiss_ivfpq_builder.IVFPQ_TRAIN_SAMPLE", 500),
        ):
            b = FAISSIVFPQBuilder(dim=64, index_dir=tmp_index_dir, collection_name="saved")
            vectors = _make_vectors(600, 64)
            asyncio.run(b.train_and_build(vectors))
            loaded = asyncio.run(b.load())

        assert loaded is not None
        assert loaded.is_trained


class TestBenchmarkRecall:
    def _build_indexes(self, dim: int = 32, n: int = 500):
        import faiss

        vectors = _make_vectors(n, dim)

        flat = faiss.IndexFlatIP(dim)
        flat.add(vectors)

        quantizer = faiss.IndexFlatIP(dim)
        ivfpq = faiss.IndexIVFPQ(quantizer, dim, 8, 4, 8)
        ivfpq.train(vectors)
        ivfpq.add(vectors)
        ivfpq.nprobe = 4
        return flat, ivfpq, vectors

    def test_recall_between_zero_and_one(self, tmp_index_dir):
        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        b = FAISSIVFPQBuilder(dim=32, index_dir=tmp_index_dir, collection_name="recall")
        flat, ivfpq, vectors = self._build_indexes()
        queries = _make_vectors(20, 32)
        recall = b.benchmark_recall(flat, ivfpq, queries, k=5)
        assert 0.0 <= recall <= 1.0

    def test_flat_vs_flat_gives_perfect_recall(self, tmp_index_dir):
        """An exact flat index compared with itself must yield recall=1.0."""
        import faiss

        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        dim = 32
        vectors = _make_vectors(200, dim)
        flat = faiss.IndexFlatIP(dim)
        flat.add(vectors)

        b = FAISSIVFPQBuilder(dim=dim, index_dir=tmp_index_dir, collection_name="flat_recall")
        queries = _make_vectors(10, dim)
        recall = b.benchmark_recall(flat, flat, queries, k=5)
        assert recall == pytest.approx(1.0)

    def test_recall_single_query_vector(self, tmp_index_dir):
        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        b = FAISSIVFPQBuilder(dim=32, index_dir=tmp_index_dir, collection_name="single_q")
        flat, ivfpq, vectors = self._build_indexes()
        query = _make_vectors(1, 32)
        recall = b.benchmark_recall(flat, ivfpq, query, k=3)
        assert 0.0 <= recall <= 1.0


class TestSearch:
    def test_search_returns_correct_shape(self, tmp_index_dir):
        import faiss

        from utils.faiss_ivfpq_builder import FAISSIVFPQBuilder

        dim = 32
        vectors = _make_vectors(200, dim)
        flat = faiss.IndexFlatIP(dim)
        flat.add(vectors)

        b = FAISSIVFPQBuilder(dim=dim, index_dir=tmp_index_dir, collection_name="search_test")
        query = _make_vectors(1, dim).reshape(-1)  # 1-D query
        distances, indices = asyncio.run(b.search(flat, query, k=5))
        assert distances.shape == (1, 5)
        assert indices.shape == (1, 5)
