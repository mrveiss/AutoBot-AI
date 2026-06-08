# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for GET /api/a2a/tasks/{id}/stream SSE endpoint.
Issue #4627: covers _event_generator critical paths deferred from #4606.

Paths tested:
  1. Unknown task → 404
  2. Redis unavailable → error SSE event
  3. Terminal (completed) task → initial state_change emitted, stream closes
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio  # noqa: F401 — ensures pytest-asyncio plugin loaded
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.a2a import router
from auth_middleware import check_admin_permission

# ---------------------------------------------------------------------------
# App setup — import router first, then override auth dependency
# ---------------------------------------------------------------------------


# Build a minimal FastAPI app to exercise the router in isolation
app = FastAPI()
app.include_router(router, prefix="/api/a2a")
# Override auth so tests never hit Redis/JWT for authentication.
# The Depends(check_admin_permission) on the router references the same
# function object imported here, so the override is picked up correctly.
app.dependency_overrides[check_admin_permission] = lambda: None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task_mock(state_value: str = "submitted") -> MagicMock:
    """Return a minimal Task-like mock with the given state string value."""
    task = MagicMock()
    task.id = "test-task-id"
    task.status.state.value = state_value
    return task


async def _collect_sse(response) -> list:
    """Consume an SSE StreamingResponse and return all non-empty data lines."""
    lines = []
    async for chunk in response.aiter_text():
        for line in chunk.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                lines.append(line[len("data:") :].strip())
    return lines


# ---------------------------------------------------------------------------
# Test 1: unknown task → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_unknown_task_returns_404():
    """GET /stream for a non-existent task_id must return HTTP 404."""
    mock_manager = MagicMock()
    mock_manager.get_task.return_value = None

    with patch("api.a2a.get_task_manager", return_value=mock_manager):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/a2a/tasks/unknown-id/stream")

    assert response.status_code == 404
    assert "unknown-id" in response.text


# ---------------------------------------------------------------------------
# Test 2: Redis unavailable → error SSE event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_redis_unavailable_yields_error_event():
    """When get_async_redis_client returns None, yield error event and close."""
    mock_manager = MagicMock()
    mock_manager.get_task.return_value = _make_task_mock("submitted")

    with (
        patch("api.a2a.get_task_manager", return_value=mock_manager),
        patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with client.stream("GET", "/api/a2a/tasks/test-task-id/stream") as response:
                assert response.status_code == 200
                data_lines = await _collect_sse(response)

    assert len(data_lines) == 1
    payload = json.loads(data_lines[0])
    assert payload["event"] == "error"
    assert "Redis" in payload["message"]


# ---------------------------------------------------------------------------
# Test 3: terminal (completed) task → initial state emitted, stream closes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_terminal_task_closes_after_initial_state():
    """A COMPLETED task must yield one state_change event then close without hanging."""
    mock_manager = MagicMock()
    # Both the pre-check call and the inside-generator call return a completed task
    mock_manager.get_task.return_value = _make_task_mock("completed")

    # pubsub() is called synchronously (redis.pubsub()), so use a plain
    # MagicMock for the client and set pubsub() to return an AsyncMock whose
    # subscribe/unsubscribe/close are all awaitable.  The generator exits before
    # entering the listen() loop because the initial state is already terminal.
    mock_pubsub = AsyncMock()
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub

    with (
        patch("api.a2a.get_task_manager", return_value=mock_manager),
        patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with client.stream("GET", "/api/a2a/tasks/test-task-id/stream") as response:
                assert response.status_code == 200
                data_lines = await _collect_sse(response)

    assert len(data_lines) >= 1
    payload = json.loads(data_lines[0])
    assert payload["event"] == "state_change"
    assert payload["state"] == "completed"
    assert payload["task_id"] == "test-task-id"
    # Stream must have closed without additional events
    assert len(data_lines) == 1


# ---------------------------------------------------------------------------
# Test 4: task expires after pubsub subscribe → error SSE event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_generator_task_expires_after_subscribe():
    """Task exists on 404 guard but expires before snapshot — yields error event."""
    mock_manager = MagicMock()
    # First call (HTTP 404 guard in stream_task_events): task exists
    # Second call (snapshot inside _event_generator): task is gone
    mock_manager.get_task.side_effect = [_make_task_mock("submitted"), None]

    mock_pubsub = AsyncMock()
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub

    with (
        patch("api.a2a.get_task_manager", return_value=mock_manager),
        patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with client.stream("GET", "/api/a2a/tasks/test-task-id/stream") as response:
                assert response.status_code == 200
                data_lines = await _collect_sse(response)

    assert len(data_lines) == 1
    payload = json.loads(data_lines[0])
    assert payload["event"] == "error"
    assert "expired" in payload["message"].lower()


# ---------------------------------------------------------------------------
# Test 5: pubsub listener raises exception → sentinel unblocks stream, closes cleanly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_generator_reader_exception_unblocks_stream():
    """pubsub.listen() raising causes _reader to put None sentinel, stream closes cleanly."""
    mock_manager = MagicMock()
    # Both calls return a non-terminal task so we enter the pub/sub loop
    mock_manager.get_task.return_value = _make_task_mock("working")

    async def _failing_listen():
        raise Exception("Redis connection lost")
        yield  # make it an async generator

    mock_pubsub = AsyncMock()
    mock_pubsub.listen = _failing_listen
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub

    with (
        patch("api.a2a.get_task_manager", return_value=mock_manager),
        patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with client.stream("GET", "/api/a2a/tasks/test-task-id/stream") as response:
                assert response.status_code == 200
                data_lines = await _collect_sse(response)

    # Stream must close without hanging — we get the initial state_change event
    # and then the stream closes after the _reader exception puts the None sentinel.
    assert len(data_lines) >= 1
    payload = json.loads(data_lines[0])
    assert payload["event"] == "state_change"
    assert payload["state"] == "working"
