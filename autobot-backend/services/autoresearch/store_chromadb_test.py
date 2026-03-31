# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ExperimentStore ChromaDB Indexing Tests

Issue #2637: Tests for _index_in_chromadb, _build_document, _build_metadata,
and the conditional indexing logic in save_experiment.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from services.autoresearch.config import AutoResearchConfig
from services.autoresearch.models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
)
from services.autoresearch.store import ExperimentStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_store(
    mock_redis: AsyncMock | None = None,
    mock_collection: AsyncMock | None = None,
) -> ExperimentStore:
    """Build an ExperimentStore with mocked Redis and ChromaDB."""
    store = ExperimentStore(AutoResearchConfig())
    if mock_redis is None:
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        mock_redis.zadd = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.srem = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()
    store._redis = mock_redis

    if mock_collection is not None:
        store._chromadb_collection = mock_collection

    return store


def _make_experiment(
    state: ExperimentState = ExperimentState.COMPLETED,
    val_bpb: float | None = 5.5,
    hypothesis: str = "Test higher learning rate",
    description: str = "Increase LR from 3e-4 to 1e-3",
    code_diff: str = "",
    tags: list | None = None,
    baseline: float | None = 6.0,
) -> Experiment:
    """Build a test experiment with optional result."""
    exp = Experiment(
        hypothesis=hypothesis,
        description=description,
        code_diff=code_diff,
        tags=tags or [],
        state=state,
        baseline_val_bpb=baseline,
    )
    if val_bpb is not None:
        exp.result = ExperimentResult(val_bpb=val_bpb)
    return exp


# ---------------------------------------------------------------------------
# _build_document tests
# ---------------------------------------------------------------------------


class TestBuildDocument:
    """Tests for ExperimentStore._build_document."""

    def test_includes_hypothesis(self):
        store = _make_store()
        exp = _make_experiment(hypothesis="Increase dropout")
        doc = store._build_document(exp)
        assert "Increase dropout" in doc

    def test_includes_description(self):
        store = _make_store()
        exp = _make_experiment(description="Raise dropout from 0.2 to 0.3")
        doc = store._build_document(exp)
        assert "Raise dropout" in doc

    def test_includes_val_bpb(self):
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5)
        doc = store._build_document(exp)
        assert "5.5" in doc

    def test_includes_improvement_when_available(self):
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5, baseline=6.0)
        doc = store._build_document(exp)
        assert "Improvement" in doc
        assert "0.5000" in doc

    def test_no_improvement_without_baseline(self):
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5, baseline=None)
        doc = store._build_document(exp)
        assert "Improvement" not in doc

    def test_includes_truncated_code_diff(self):
        store = _make_store()
        long_diff = "x" * 600
        exp = _make_experiment(code_diff=long_diff)
        doc = store._build_document(exp)
        assert "Code change:" in doc
        # Should be truncated to 500 chars
        assert len(doc.split("Code change:\n")[1]) == 500

    def test_no_code_diff_section_when_empty(self):
        store = _make_store()
        exp = _make_experiment(code_diff="")
        doc = store._build_document(exp)
        assert "Code change:" not in doc

    def test_no_result_omits_val_bpb(self):
        store = _make_store()
        exp = _make_experiment(val_bpb=None)
        exp.result = None
        doc = store._build_document(exp)
        assert "val_bpb" not in doc


# ---------------------------------------------------------------------------
# _build_metadata tests
# ---------------------------------------------------------------------------


class TestBuildMetadata:
    """Tests for ExperimentStore._build_metadata."""

    def test_includes_state(self):
        store = _make_store()
        exp = _make_experiment(state=ExperimentState.KEPT)
        meta = store._build_metadata(exp)
        assert meta["state"] == "kept"

    def test_includes_created_at(self):
        store = _make_store()
        exp = _make_experiment()
        meta = store._build_metadata(exp)
        assert "created_at" in meta
        assert isinstance(meta["created_at"], float)

    def test_includes_val_bpb_when_available(self):
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5)
        meta = store._build_metadata(exp)
        assert meta["val_bpb"] == 5.5

    def test_no_val_bpb_when_no_result(self):
        store = _make_store()
        exp = _make_experiment(val_bpb=None)
        exp.result = None
        meta = store._build_metadata(exp)
        assert "val_bpb" not in meta

    def test_includes_improvement(self):
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5, baseline=6.0)
        meta = store._build_metadata(exp)
        assert meta["improvement"] == 0.5

    def test_no_improvement_without_baseline(self):
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5, baseline=None)
        meta = store._build_metadata(exp)
        assert "improvement" not in meta

    def test_includes_tags_as_csv(self):
        store = _make_store()
        exp = _make_experiment(tags=["lr_sweep", "dropout"])
        meta = store._build_metadata(exp)
        assert meta["tags"] == "lr_sweep,dropout"

    def test_no_tags_key_when_empty(self):
        store = _make_store()
        exp = _make_experiment(tags=[])
        meta = store._build_metadata(exp)
        assert "tags" not in meta


# ---------------------------------------------------------------------------
# _index_in_chromadb tests
# ---------------------------------------------------------------------------


class TestIndexInChromadb:
    """Tests for ExperimentStore._index_in_chromadb."""

    @pytest.mark.asyncio
    async def test_upserts_to_collection(self):
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(val_bpb=5.5)

        await store._index_in_chromadb(exp)

        collection.upsert.assert_called_once()
        call_kwargs = collection.upsert.call_args[1]
        assert call_kwargs["ids"] == [exp.id]
        assert len(call_kwargs["documents"]) == 1
        assert len(call_kwargs["metadatas"]) == 1

    @pytest.mark.asyncio
    async def test_document_contains_hypothesis(self):
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(hypothesis="Reduce block size")

        await store._index_in_chromadb(exp)

        doc = collection.upsert.call_args[1]["documents"][0]
        assert "Reduce block size" in doc

    @pytest.mark.asyncio
    async def test_metadata_contains_state(self):
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.KEPT)

        await store._index_in_chromadb(exp)

        meta = collection.upsert.call_args[1]["metadatas"][0]
        assert meta["state"] == "kept"

    @pytest.mark.asyncio
    async def test_chromadb_error_logged_not_raised(self):
        """ChromaDB failures should be logged but not propagate."""
        collection = AsyncMock()
        collection.upsert = AsyncMock(
            side_effect=RuntimeError("ChromaDB down")
        )
        store = _make_store(mock_collection=collection)
        exp = _make_experiment()

        # Should not raise
        await store._index_in_chromadb(exp)

    @pytest.mark.asyncio
    async def test_lazy_init_chromadb_on_first_call(self):
        """When _chromadb_collection is None, _get_chromadb is called."""
        store = _make_store()
        store._chromadb_collection = None  # force lazy init

        mock_collection = AsyncMock()
        mock_collection.upsert = AsyncMock()
        mock_client = AsyncMock()
        mock_client.get_or_create_collection = AsyncMock(
            return_value=mock_collection
        )

        with patch(
            "utils.chromadb_client.get_async_chromadb_client",
            new_callable=AsyncMock,
            return_value=mock_client,
        ) as mock_get_client:
            exp = _make_experiment()
            await store._index_in_chromadb(exp)

            mock_get_client.assert_called_once()
            mock_client.get_or_create_collection.assert_called_once()
            mock_collection.upsert.assert_called_once()


# ---------------------------------------------------------------------------
# save_experiment conditional indexing tests
# ---------------------------------------------------------------------------


class TestSaveExperimentIndexing:
    """Tests for the ChromaDB indexing trigger in save_experiment."""

    @pytest.mark.asyncio
    async def test_completed_experiment_indexed(self):
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.COMPLETED, val_bpb=5.5)

        await store.save_experiment(exp)

        collection.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_kept_experiment_indexed(self):
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.KEPT, val_bpb=5.5)

        await store.save_experiment(exp)

        collection.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_experiment_not_indexed(self):
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.FAILED, val_bpb=None)
        exp.result = None

        await store.save_experiment(exp)

        collection.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_experiment_not_indexed(self):
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.PENDING, val_bpb=None)
        exp.result = None

        await store.save_experiment(exp)

        collection.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_discarded_experiment_not_indexed(self):
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.DISCARDED, val_bpb=5.5)

        await store.save_experiment(exp)

        collection.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_transition_cleans_old_index(self):
        """When old_state differs from current, srem is called."""
        store = _make_store()
        exp = _make_experiment(state=ExperimentState.KEPT, val_bpb=5.5)

        await store.save_experiment(exp, old_state=ExperimentState.RUNNING)

        store._redis.srem.assert_called_once()
        call_args = store._redis.srem.call_args[0]
        assert "running" in call_args[0]

    @pytest.mark.asyncio
    async def test_same_state_no_srem(self):
        """When old_state equals current state, srem should not be called."""
        store = _make_store()
        exp = _make_experiment(state=ExperimentState.PENDING, val_bpb=None)
        exp.result = None

        await store.save_experiment(exp, old_state=ExperimentState.PENDING)

        store._redis.srem.assert_not_called()
