# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ExperimentStore ChromaDB Indexing Tests

Issue #2637: Tests for _index_in_chromadb, _build_document, _build_metadata,
and the conditional indexing logic in save_experiment.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.logging_manager import get_logger
from services.autoresearch.config import AutoResearchConfig
from services.autoresearch.models import (
    Experiment,
    ExperimentResult,
    ExperimentState,
    HyperParams,
)
from services.autoresearch.store import ExperimentStore

logger = get_logger(__name__)


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

    def test_includes_hypothesis(self) -> None:
        store = _make_store()
        exp = _make_experiment(hypothesis="Increase dropout")
        doc = store._build_document(exp)
        assert "Increase dropout" in doc

    def test_includes_description(self) -> None:
        store = _make_store()
        exp = _make_experiment(description="Raise dropout from 0.2 to 0.3")
        doc = store._build_document(exp)
        assert "Raise dropout" in doc

    def test_includes_val_bpb(self) -> None:
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5)
        doc = store._build_document(exp)
        assert "5.5" in doc

    def test_includes_improvement_when_available(self) -> None:
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5, baseline=6.0)
        doc = store._build_document(exp)
        assert "Improvement" in doc
        assert "0.5000" in doc

    def test_no_improvement_without_baseline(self) -> None:
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5, baseline=None)
        doc = store._build_document(exp)
        assert "Improvement" not in doc

    def test_includes_truncated_code_diff(self) -> None:
        store = _make_store()
        long_diff = "x" * 600
        exp = _make_experiment(code_diff=long_diff)
        doc = store._build_document(exp)
        assert "Code change:" in doc
        # Should be truncated to 500 chars
        assert len(doc.split("Code change:\n")[1]) == 500

    def test_no_code_diff_section_when_empty(self) -> None:
        store = _make_store()
        exp = _make_experiment(code_diff="")
        doc = store._build_document(exp)
        assert "Code change:" not in doc

    def test_no_result_omits_val_bpb(self) -> None:
        store = _make_store()
        exp = _make_experiment(val_bpb=None)
        exp.result = None
        doc = store._build_document(exp)
        assert "val_bpb" not in doc

    def test_val_bpb_none_with_baseline_set_omits_improvement(self) -> None:
        """val_bpb=None but baseline_val_bpb set must not include Improvement — Issue #3211."""
        store = _make_store()
        exp = _make_experiment(val_bpb=None, baseline=6.0)
        # result exists but val_bpb is None
        exp.result = ExperimentResult(val_bpb=None)
        doc = store._build_document(exp)
        assert "Improvement" not in doc
        assert "Baseline" not in doc


# ---------------------------------------------------------------------------
# _build_metadata tests
# ---------------------------------------------------------------------------


class TestBuildMetadata:
    """Tests for ExperimentStore._build_metadata."""

    def test_includes_state(self) -> None:
        store = _make_store()
        exp = _make_experiment(state=ExperimentState.KEPT)
        meta = store._build_metadata(exp)
        assert meta["state"] == "kept"

    def test_includes_created_at(self) -> None:
        store = _make_store()
        exp = _make_experiment()
        meta = store._build_metadata(exp)
        assert "created_at" in meta
        assert isinstance(meta["created_at"], float)

    def test_includes_val_bpb_when_available(self) -> None:
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5)
        meta = store._build_metadata(exp)
        assert meta["val_bpb"] == 5.5

    def test_no_val_bpb_when_no_result(self) -> None:
        store = _make_store()
        exp = _make_experiment(val_bpb=None)
        exp.result = None
        meta = store._build_metadata(exp)
        assert "val_bpb" not in meta

    def test_includes_improvement(self) -> None:
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5, baseline=6.0)
        meta = store._build_metadata(exp)
        assert meta["improvement"] == 0.5

    def test_no_improvement_without_baseline(self) -> None:
        store = _make_store()
        exp = _make_experiment(val_bpb=5.5, baseline=None)
        meta = store._build_metadata(exp)
        assert "improvement" not in meta

    def test_includes_tags_as_csv(self) -> None:
        store = _make_store()
        exp = _make_experiment(tags=["lr_sweep", "dropout"])
        meta = store._build_metadata(exp)
        assert meta["tags"] == "lr_sweep,dropout"

    def test_no_tags_key_when_empty(self) -> None:
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
    async def test_upserts_to_collection(self) -> None:
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
    async def test_document_contains_hypothesis(self) -> None:
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(hypothesis="Reduce block size")

        await store._index_in_chromadb(exp)

        doc = collection.upsert.call_args[1]["documents"][0]
        assert "Reduce block size" in doc

    @pytest.mark.asyncio
    async def test_metadata_contains_state(self) -> None:
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.KEPT)

        await store._index_in_chromadb(exp)

        meta = collection.upsert.call_args[1]["metadatas"][0]
        assert meta["state"] == "kept"

    @pytest.mark.asyncio
    async def test_chromadb_error_logged_not_raised(self) -> None:
        """ChromaDB failures should be logged but not propagate."""
        collection = AsyncMock()
        collection.upsert = AsyncMock(side_effect=RuntimeError("ChromaDB down"))
        store = _make_store(mock_collection=collection)
        exp = _make_experiment()

        # Should not raise
        await store._index_in_chromadb(exp)

    @pytest.mark.asyncio
    async def test_lazy_init_chromadb_on_first_call(self) -> None:
        """When _chromadb_collection is None, _get_chromadb is called."""
        store = _make_store()
        store._chromadb_collection = None  # force lazy init

        mock_collection = AsyncMock()
        mock_collection.upsert = AsyncMock()
        mock_client = AsyncMock()
        mock_client.get_or_create_collection = AsyncMock(return_value=mock_collection)

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
    async def test_completed_experiment_indexed(self) -> None:
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.COMPLETED, val_bpb=5.5)

        await store.save_experiment(exp)

        collection.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_kept_experiment_indexed(self) -> None:
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.KEPT, val_bpb=5.5)

        await store.save_experiment(exp)

        collection.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_experiment_not_indexed(self) -> None:
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.FAILED, val_bpb=None)
        exp.result = None

        await store.save_experiment(exp)

        collection.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_experiment_not_indexed(self) -> None:
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.PENDING, val_bpb=None)
        exp.result = None

        await store.save_experiment(exp)

        collection.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_discarded_experiment_not_indexed(self) -> None:
        collection = AsyncMock()
        collection.upsert = AsyncMock()
        store = _make_store(mock_collection=collection)
        exp = _make_experiment(state=ExperimentState.DISCARDED, val_bpb=5.5)

        await store.save_experiment(exp)

        collection.upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_transition_cleans_old_index(self) -> None:
        """When old_state differs from current, srem is called."""
        store = _make_store()
        exp = _make_experiment(state=ExperimentState.KEPT, val_bpb=5.5)

        await store.save_experiment(exp, old_state=ExperimentState.RUNNING)

        store._redis.srem.assert_called_once()
        call_args = store._redis.srem.call_args[0]
        assert "running" in call_args[0]

    @pytest.mark.asyncio
    async def test_same_state_no_srem(self) -> None:
        """When old_state equals current state, srem should not be called."""
        store = _make_store()
        exp = _make_experiment(state=ExperimentState.PENDING, val_bpb=None)
        exp.result = None

        await store.save_experiment(exp, old_state=ExperimentState.PENDING)

        store._redis.srem.assert_not_called()


# ---------------------------------------------------------------------------
# Enriched indexing tests (Task 8 — Issue #3199)
# ---------------------------------------------------------------------------


class TestEnrichedIndexing:
    """Tests for enriched _build_document and _build_metadata (Task 8)."""

    def test_build_document_includes_hyperparams(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test hypothesis",
            description="Test description",
            hyperparams=HyperParams(learning_rate=1e-4, dropout=0.1),
            result=ExperimentResult(val_bpb=4.5),
            baseline_val_bpb=5.0,
            state=ExperimentState.KEPT,
            tags=["session:s1", "attention"],
        )

        doc = store._build_document(exp)
        assert "learning_rate" in doc
        assert "1e-4" in doc or "0.0001" in doc
        assert "dropout" in doc
        assert "Baseline: 5.0" in doc
        assert "Improvement: 0.5" in doc

    def test_build_document_includes_session_context(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["session:mysession", "lr_sweep"],
        )
        doc = store._build_document(exp)
        assert "Session: mysession" in doc

    def test_build_document_no_session_tag(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["lr_sweep"],
        )
        doc = store._build_document(exp)
        assert "Session:" not in doc

    def test_build_metadata_includes_hyperparams(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(learning_rate=1e-4),
            result=ExperimentResult(val_bpb=4.5),
            state=ExperimentState.KEPT,
            tags=["session:s1"],
        )

        meta = store._build_metadata(exp)
        assert "learning_rate" in meta
        assert meta["learning_rate"] == 1e-4
        assert "session_id" in meta
        assert meta["session_id"] == "s1"

    def test_build_metadata_key_hyperparams_present(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(
                learning_rate=3e-4,
                dropout=0.2,
                batch_size=64,
                n_layer=6,
                n_head=6,
            ),
            state=ExperimentState.COMPLETED,
            tags=[],
        )
        meta = store._build_metadata(exp)
        assert meta["learning_rate"] == 3e-4
        assert meta["dropout"] == 0.2
        assert meta["batch_size"] == 64
        assert meta["n_layer"] == 6
        assert meta["n_head"] == 6

    def test_build_metadata_no_session_when_no_session_tag(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["lr_sweep"],
        )
        meta = store._build_metadata(exp)
        assert "session_id" not in meta


# ---------------------------------------------------------------------------
# Missing spec fields: iteration, trend, variant ID (Issue #3212)
# ---------------------------------------------------------------------------


class TestSpecFieldsIterationTrendVariant:
    """Tests for iteration, trend_direction, and variant_id in _build_document
    and _build_metadata — spec section 2.1 (#3212)."""

    # --- _build_document ---

    def test_document_includes_iteration(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["session:s1", "iteration:3"],
        )
        doc = store._build_document(exp)
        assert "Iteration: 3" in doc

    def test_document_no_iteration_when_tag_absent(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["session:s1"],
        )
        doc = store._build_document(exp)
        assert "Iteration:" not in doc

    def test_document_includes_trend(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["trend:improving"],
        )
        doc = store._build_document(exp)
        assert "Trend: improving" in doc

    def test_document_no_trend_when_tag_absent(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=[],
        )
        doc = store._build_document(exp)
        assert "Trend:" not in doc

    def test_document_includes_variant(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["variant:v-abc123"],
        )
        doc = store._build_document(exp)
        assert "Variant: v-abc123" in doc

    def test_document_no_variant_when_tag_absent(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["session:s1"],
        )
        doc = store._build_document(exp)
        assert "Variant:" not in doc

    def test_document_all_three_spec_fields(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Full spec test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["session:s1", "iteration:2", "trend:plateau", "variant:v-xyz"],
        )
        doc = store._build_document(exp)
        assert "Iteration: 2" in doc
        assert "Trend: plateau" in doc
        assert "Variant: v-xyz" in doc

    # --- _build_metadata ---

    def test_metadata_includes_iteration(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["iteration:4"],
        )
        meta = store._build_metadata(exp)
        assert meta["iteration"] == 4

    def test_metadata_iteration_is_int(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["iteration:7"],
        )
        meta = store._build_metadata(exp)
        assert isinstance(meta["iteration"], int)

    def test_metadata_no_iteration_when_tag_absent(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["session:s1"],
        )
        meta = store._build_metadata(exp)
        assert "iteration" not in meta

    def test_metadata_includes_trend_direction(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["trend:declining"],
        )
        meta = store._build_metadata(exp)
        assert meta["trend_direction"] == "declining"

    def test_metadata_no_trend_when_tag_absent(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=[],
        )
        meta = store._build_metadata(exp)
        assert "trend_direction" not in meta

    def test_metadata_includes_variant_id(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["variant:var-001"],
        )
        meta = store._build_metadata(exp)
        assert meta["variant_id"] == "var-001"

    def test_metadata_no_variant_when_tag_absent(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["session:s1"],
        )
        meta = store._build_metadata(exp)
        assert "variant_id" not in meta

    def test_metadata_all_three_spec_fields(self) -> None:
        store = _make_store()
        exp = Experiment(
            hypothesis="Full spec test",
            hyperparams=HyperParams(),
            state=ExperimentState.COMPLETED,
            tags=["session:s1", "iteration:1", "trend:improving", "variant:v-best"],
        )
        meta = store._build_metadata(exp)
        assert meta["iteration"] == 1
        assert meta["trend_direction"] == "improving"
        assert meta["variant_id"] == "v-best"
