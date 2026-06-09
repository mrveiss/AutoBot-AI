# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for held-out dev/test split enforcement in rag_benchmarks.

Issue #5074 — verifies:
  * tune() allows dev access and blocks test access
  * score() allows test access and blocks dev access
  * hash-based split is deterministic across runs
  * held_out_score is True only for split=TEST, False for DEV / ALL
  * POST /rag/benchmark/run contract exposes all new fields
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from knowledge.rag_benchmarks import (
    _GROUND_TRUTH,
    BenchmarkDataset,
    BenchmarkHarness,
    BenchmarkResult,
    BenchmarkSplit,
    _deterministic_dev_test_split,
    get_default_dataset,
    publish_feedback_events,
)

# ---------------------------------------------------------------------------
# Dataset split correctness
# ---------------------------------------------------------------------------


def test_deterministic_split_is_reproducible():
    """Same query list must always produce the same split."""
    qs = list(_GROUND_TRUTH.keys())
    a = _deterministic_dev_test_split(sorted(qs), dev_fraction=0.8)
    b = _deterministic_dev_test_split(sorted(qs), dev_fraction=0.8)
    assert a == b
    # And across dataset instantiations
    ds1 = BenchmarkDataset.from_ground_truth(_GROUND_TRUTH)
    ds2 = BenchmarkDataset.from_ground_truth(_GROUND_TRUTH)
    assert ds1.dev_ids == ds2.dev_ids
    assert ds1.test_ids == ds2.test_ids


def test_split_is_disjoint_and_covering():
    ds = get_default_dataset()
    assert ds.dev_ids.isdisjoint(ds.test_ids)
    assert ds.dev_ids | ds.test_ids == set(_GROUND_TRUTH.keys())
    # Sizes sum correctly
    assert ds.dev_size + ds.test_size == len(_GROUND_TRUTH)


def test_split_non_empty_for_small_dataset():
    """Tiny datasets should still get at least one query in each split."""
    tiny = {"only_query": {"doc_1"}}
    ds = BenchmarkDataset.from_ground_truth(tiny, dev_fraction=0.8)
    assert ds.dev_size + ds.test_size == 1
    # Exactly one of the two must be non-empty (can't split 1 into two non-empty).
    assert (ds.dev_size == 1) ^ (ds.test_size == 1)


# ---------------------------------------------------------------------------
# Enforcement: tune/score boundary
# ---------------------------------------------------------------------------


def _pick_ids(ds: BenchmarkDataset):
    dev_qid = next(iter(ds.dev_ids))
    test_qid = next(iter(ds.test_ids))
    return dev_qid, test_qid


def test_tune_allows_dev_access():
    ds = get_default_dataset()
    harness = BenchmarkHarness(dataset=ds)

    def runner(dataset: BenchmarkDataset):
        out = []
        for qid in dataset.iter_split(BenchmarkSplit.DEV):
            dataset.expected(qid)  # should not raise
            out.append(BenchmarkResult(qid, [], [], 1.0, split_used=BenchmarkSplit.DEV.value))
        return out

    report = harness.tune(runner)
    assert report.split_used == BenchmarkSplit.DEV.value
    assert report.held_out_score is False
    assert report.tuned_on_dev is True
    assert len(report.results) == ds.dev_size


def test_tune_raises_on_test_access():
    ds = get_default_dataset()
    harness = BenchmarkHarness(dataset=ds)
    _dev_qid, test_qid = _pick_ids(ds)

    def leaky_runner(dataset: BenchmarkDataset):
        dataset.expected(test_qid)  # boundary violation
        return []

    with pytest.raises(RuntimeError, match="tune\\(\\) accessed test"):
        harness.tune(leaky_runner)


def test_score_allows_test_access():
    ds = get_default_dataset()
    harness = BenchmarkHarness(dataset=ds)

    def runner(dataset: BenchmarkDataset):
        out = []
        for qid in dataset.iter_split(BenchmarkSplit.TEST):
            dataset.expected(qid)
            out.append(BenchmarkResult(qid, [], [], 1.0, split_used=BenchmarkSplit.TEST.value))
        return out

    report = harness.score(runner)
    assert report.split_used == BenchmarkSplit.TEST.value
    assert report.held_out_score is True
    assert len(report.results) == ds.test_size


def test_score_raises_on_dev_access():
    ds = get_default_dataset()
    harness = BenchmarkHarness(dataset=ds)
    dev_qid, _test_qid = _pick_ids(ds)

    def leaky_runner(dataset: BenchmarkDataset):
        dataset.expected(dev_qid)  # boundary violation
        return []

    with pytest.raises(RuntimeError, match="score\\(\\) accessed dev"):
        harness.score(leaky_runner)


def test_expected_rejects_unknown_query():
    ds = get_default_dataset()
    with pytest.raises(KeyError):
        ds.expected("not-a-known-query")


# ---------------------------------------------------------------------------
# held_out_score flag semantics
# ---------------------------------------------------------------------------


def test_run_dev_is_not_held_out():
    ds = get_default_dataset()
    harness = BenchmarkHarness(dataset=ds)

    def runner(dataset: BenchmarkDataset):
        return [
            BenchmarkResult(q, [], [], 0.5, split_used=BenchmarkSplit.DEV.value)
            for q in dataset.iter_split(BenchmarkSplit.DEV)
        ]

    report = harness.run(runner, split=BenchmarkSplit.DEV)
    assert report.held_out_score is False
    assert report.split_used == BenchmarkSplit.DEV.value


def test_run_test_is_held_out():
    ds = get_default_dataset()
    harness = BenchmarkHarness(dataset=ds)

    def runner(dataset: BenchmarkDataset):
        out = []
        for q in dataset.iter_split(BenchmarkSplit.TEST):
            dataset.expected(q)  # Issue #5160: must access to mark held_out
            out.append(BenchmarkResult(q, [], [], 0.5, split_used=BenchmarkSplit.TEST.value))
        return out

    report = harness.run(runner, split=BenchmarkSplit.TEST)
    assert report.held_out_score is True
    assert report.split_used == BenchmarkSplit.TEST.value


def test_run_all_is_never_held_out():
    ds = get_default_dataset()
    harness = BenchmarkHarness(dataset=ds)

    def runner(dataset: BenchmarkDataset):
        return [
            BenchmarkResult(q, [], [], 1.0, split_used=BenchmarkSplit.ALL.value)
            for q in dataset.iter_split(BenchmarkSplit.ALL)
        ]

    report = harness.run(runner, split=BenchmarkSplit.ALL)
    assert report.held_out_score is False
    assert report.split_used == BenchmarkSplit.ALL.value


# ---------------------------------------------------------------------------
# Feedback publisher: split_used tag (Issue #5074 x #4676)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_feedback_events_tags_split():
    """Emitted xadd entries must carry split_used so RetrievalLearner can
    exclude test-set feedback from training."""
    redis = AsyncMock()
    redis.xadd = AsyncMock()
    redis.expire = AsyncMock()

    results = [
        BenchmarkResult(
            query="q1",
            retrieved_ids=["a"],
            ranked_ids=["a"],
            precision_at_k=0.5,
            split_used=BenchmarkSplit.TEST.value,
        )
    ]
    published = await publish_feedback_events(redis, results)
    assert published == 1
    redis.xadd.assert_awaited_once()
    call_args = redis.xadd.await_args
    _stream_key, entry = call_args.args
    assert entry["split_used"] == BenchmarkSplit.TEST.value


# ---------------------------------------------------------------------------
# Endpoint contract: new fields present in response
# ---------------------------------------------------------------------------


def test_endpoint_response_shape_has_new_fields():
    """POST /rag/benchmark/run must return all Issue #5074 fields."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.knowledge_rag import router
    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(router, prefix="/rag")
    app.dependency_overrides[check_admin_permission] = lambda: True

    client = TestClient(app)

    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new=AsyncMock(return_value=None),
    ):
        resp = client.post("/rag/benchmark/run", json={"split": "test", "k": 5})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in (
        "published",
        "total",
        "split_used",
        "dev_size",
        "test_size",
        "tuned_on_dev",
        "held_out_score",
        "mean_precision_at_k",
    ):
        assert key in body, f"missing field: {key}"
    assert body["split_used"] == "test"
    assert body["held_out_score"] is True


def test_endpoint_rejects_invalid_split():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.knowledge_rag import router
    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(router, prefix="/rag")
    app.dependency_overrides[check_admin_permission] = lambda: True

    client = TestClient(app)
    resp = client.post("/rag/benchmark/run", json={"split": "holdout"})
    assert resp.status_code == 422  # pydantic validation error


# ---------------------------------------------------------------------------
# Issue #5160: empty-results guard on score()
# ---------------------------------------------------------------------------


def test_score_with_empty_results_raises():
    """score() must raise when the scorer accesses zero test_ids.

    Otherwise `held_out_score=True` would be falsely confident on an
    empty run (harness silently succeeded with no evidence).
    """
    ds = get_default_dataset()
    harness = BenchmarkHarness(dataset=ds)

    def noop_runner(_dataset: BenchmarkDataset):
        return []

    with pytest.raises(RuntimeError, match="no test_ids were accessed"):
        harness.score(noop_runner)


def test_held_out_score_requires_test_access():
    """run(split=TEST) with zero test accesses must surface as a RuntimeError.

    Previously `held_out_score` could be True on a run that touched no
    test_ids (no leakage, but also no evidence). The guard in score()
    now refuses that outcome.
    """
    ds = get_default_dataset()
    harness = BenchmarkHarness(dataset=ds)

    def noop_runner(_dataset: BenchmarkDataset):
        return []

    with pytest.raises(RuntimeError, match="no test_ids were accessed"):
        harness.run(noop_runner, split=BenchmarkSplit.TEST)


def test_endpoint_dev_split_is_not_held_out():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.knowledge_rag import router
    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(router, prefix="/rag")
    app.dependency_overrides[check_admin_permission] = lambda: True

    client = TestClient(app)
    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new=AsyncMock(return_value=None),
    ):
        resp = client.post("/rag/benchmark/run", json={"split": "dev"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["split_used"] == "dev"
    assert body["held_out_score"] is False
