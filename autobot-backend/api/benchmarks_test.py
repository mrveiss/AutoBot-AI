# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the LLM benchmark runs API (Issue #9024)."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.benchmarks import BUILTIN_PROMPT_SETS, router

USER = {"user_id": "u-1", "username": "testuser", "role": "user"}
OTHER = {"user_id": "u-2", "username": "otheruser", "role": "user"}
USER_HASH_KEY = "benchmark:runs:user:u-1"
OTHER_HASH_KEY = "benchmark:runs:user:u-2"


def _make_app(current_user=None) -> FastAPI:
    app = FastAPI()

    async def _override_user():
        return current_user or USER

    from auth_middleware import get_current_user

    app.dependency_overrides[get_current_user] = _override_user
    app.include_router(router)
    return app


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    with patch(
        "api.benchmarks.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=redis,
    ) as p:
        p.return_value = redis
        yield redis


@pytest.fixture
def client(mock_redis):
    return TestClient(_make_app())


@pytest.fixture
def other_client(mock_redis):
    return TestClient(_make_app(current_user=OTHER))


def _run_doc(run_id="r1", prompt_type="code", model="openai/gpt-4o", created="2025-01-02T00:00:00+00:00"):
    return {
        "id": run_id,
        "prompt": "p",
        "promptType": prompt_type,
        "promptSetId": None,
        "results": [{"model": model, "content": "out", "rating": 4, "costUsd": 0.01, "latencyMs": 500}],
        "models": [model],
        "createdAt": created,
    }


class TestPromptSets:
    def test_returns_builtin_sets(self, client):
        resp = client.get("/benchmarks/prompt-sets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(BUILTIN_PROMPT_SETS)
        ids = {s["id"] for s in data}
        assert {"rag", "code", "summarization", "reasoning"}.issubset(ids)


class TestCreateRun:
    def test_creates_run(self, client, mock_redis):
        mock_redis.hset.return_value = 1
        resp = client.post(
            "/benchmarks/runs",
            json={
                "prompt": "Write a function",
                "promptType": "code",
                "results": [
                    {"model": "openai/gpt-4o", "content": "ok", "rating": 5, "costUsd": 0.02, "latencyMs": 800}
                ],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["prompt"] == "Write a function"
        assert data["promptType"] == "code"
        assert data["models"] == ["openai/gpt-4o"]
        assert data["results"][0]["rating"] == 5
        assert "id" in data and "createdAt" in data
        mock_redis.hset.assert_awaited_once()

    def test_persists_under_user_scoped_key(self, client, mock_redis):
        mock_redis.hset.return_value = 1
        client.post("/benchmarks/runs", json={"prompt": "x", "results": []})
        args = mock_redis.hset.await_args.args
        assert args[0] == USER_HASH_KEY

    def test_rejects_out_of_range_rating(self, client):
        resp = client.post(
            "/benchmarks/runs",
            json={"prompt": "x", "results": [{"model": "a/b", "rating": 9}]},
        )
        assert resp.status_code == 422


class TestListRuns:
    def test_empty(self, client, mock_redis):
        mock_redis.hgetall.return_value = {}
        resp = client.get("/benchmarks/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_newest_first(self, client, mock_redis):
        old = _run_doc("old", created="2025-01-01T00:00:00+00:00")
        new = _run_doc("new", created="2025-02-01T00:00:00+00:00")
        mock_redis.hgetall.return_value = {"old": json.dumps(old), "new": json.dumps(new)}
        resp = client.get("/benchmarks/runs")
        assert [r["id"] for r in resp.json()] == ["new", "old"]

    def test_filter_by_model(self, client, mock_redis):
        a = _run_doc("a", model="openai/gpt-4o")
        b = _run_doc("b", model="anthropic/claude")
        mock_redis.hgetall.return_value = {"a": json.dumps(a), "b": json.dumps(b)}
        resp = client.get("/benchmarks/runs?model=anthropic/claude")
        ids = [r["id"] for r in resp.json()]
        assert ids == ["b"]

    def test_filter_by_prompt_type(self, client, mock_redis):
        a = _run_doc("a", prompt_type="code")
        b = _run_doc("b", prompt_type="reasoning")
        mock_redis.hgetall.return_value = {"a": json.dumps(a), "b": json.dumps(b)}
        resp = client.get("/benchmarks/runs?prompt_type=reasoning")
        assert [r["id"] for r in resp.json()] == ["b"]

    def test_filter_since(self, client, mock_redis):
        old = _run_doc("old", created="2025-01-01T00:00:00+00:00")
        new = _run_doc("new", created="2025-03-01T00:00:00+00:00")
        mock_redis.hgetall.return_value = {"old": json.dumps(old), "new": json.dumps(new)}
        resp = client.get("/benchmarks/runs?since=2025-02-01T00:00:00+00:00")
        assert [r["id"] for r in resp.json()] == ["new"]

    def test_skips_corrupt(self, client, mock_redis):
        good = _run_doc("good")
        mock_redis.hgetall.return_value = {"good": json.dumps(good), "bad": "{not json"}
        resp = client.get("/benchmarks/runs")
        assert [r["id"] for r in resp.json()] == ["good"]


class TestGetRun:
    def test_found(self, client, mock_redis):
        mock_redis.hget.return_value = json.dumps(_run_doc("r1"))
        resp = client.get("/benchmarks/runs/r1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "r1"

    def test_404(self, client, mock_redis):
        mock_redis.hget.return_value = None
        resp = client.get("/benchmarks/runs/missing")
        assert resp.status_code == 404


class TestDeleteRun:
    def test_deletes(self, client, mock_redis):
        mock_redis.hdel.return_value = 1
        resp = client.delete("/benchmarks/runs/r1")
        assert resp.status_code == 204
        mock_redis.hdel.assert_awaited_once_with(USER_HASH_KEY, "r1")

    def test_404(self, client, mock_redis):
        mock_redis.hdel.return_value = 0
        resp = client.delete("/benchmarks/runs/missing")
        assert resp.status_code == 404


class TestPerUserScoping:
    def test_other_user_reads_own_key(self, other_client, mock_redis):
        mock_redis.hgetall.return_value = {}
        other_client.get("/benchmarks/runs")
        mock_redis.hgetall.assert_awaited_with(OTHER_HASH_KEY)

    def test_other_user_deletes_own_key(self, other_client, mock_redis):
        mock_redis.hdel.return_value = 1
        other_client.delete("/benchmarks/runs/r1")
        mock_redis.hdel.assert_awaited_once_with(OTHER_HASH_KEY, "r1")
