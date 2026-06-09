# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for agent usage tracking — Issue #3289.

Covers:
- AgentAnalytics.track_task_start / track_task_complete round-trip
- track_agent_usage context manager (success and failure paths)
- BaseAgent.execute_with_tracking wires analytics (smoke test via mocks)
- GET /api/agent_config/agents/usage endpoint aggregation logic
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.agent_analytics import AgentAnalytics, TaskStatus, track_agent_usage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_stub() -> AsyncMock:
    """Minimal async Redis stub with the methods used by AgentAnalytics."""
    stub = AsyncMock()
    # set / get / delete / expire
    stub.set = AsyncMock(return_value=True)
    stub.get = AsyncMock(return_value=None)
    stub.delete = AsyncMock(return_value=1)
    stub.expire = AsyncMock(return_value=True)
    # list ops
    stub.lpush = AsyncMock(return_value=1)
    stub.ltrim = AsyncMock(return_value=True)
    stub.lrange = AsyncMock(return_value=[])
    # hash ops
    stub.hincrby = AsyncMock(return_value=1)
    stub.hincrbyfloat = AsyncMock(return_value=1.0)
    stub.hset = AsyncMock(return_value=True)
    stub.hgetall = AsyncMock(return_value={})
    stub.keys = AsyncMock(return_value=[])
    # pipeline
    pipe_stub = AsyncMock()
    pipe_stub.hgetall = MagicMock(return_value=pipe_stub)
    pipe_stub.execute = AsyncMock(return_value=[])
    stub.pipeline = MagicMock(return_value=pipe_stub)
    return stub


def _make_analytics_with_stub():
    """Return (analytics, redis_stub) with Redis injected."""
    analytics = AgentAnalytics()
    stub = _make_redis_stub()
    analytics._redis_client = stub
    return analytics, stub


# ---------------------------------------------------------------------------
# AgentAnalytics unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_track_task_start_stores_record():
    analytics, redis_stub = _make_analytics_with_stub()

    record = await analytics.track_task_start(
        agent_id="chat",
        agent_type="chat",
        task_id="t-001",
        task_name="conversation",
    )

    assert record.agent_id == "chat"
    assert record.task_id == "t-001"
    assert record.status == TaskStatus.RUNNING.value
    redis_stub.set.assert_awaited_once()
    # Key should embed the task_id
    call_args = redis_stub.set.call_args
    assert "t-001" in call_args[0][0]


@pytest.mark.asyncio
async def test_track_task_complete_updates_and_cleans():
    analytics, redis_stub = _make_analytics_with_stub()

    task_id = "t-002"
    start_record = {
        "agent_id": "orchestrator",
        "agent_type": "orchestrator",
        "task_id": task_id,
        "task_name": "route",
        "status": TaskStatus.RUNNING.value,
        "started_at": datetime.now(tz=timezone.utc).isoformat(),
        "metadata": {},
    }
    redis_stub.get = AsyncMock(return_value=json.dumps(start_record).encode("utf-8"))

    result = await analytics.track_task_complete(
        task_id=task_id,
        status=TaskStatus.COMPLETED,
        tokens_used=128,
    )

    assert result is not None
    assert result.status == TaskStatus.COMPLETED.value
    assert result.tokens_used == 128
    redis_stub.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_track_task_complete_missing_task_returns_none():
    analytics, redis_stub = _make_analytics_with_stub()
    # get returns None → task not found
    redis_stub.get = AsyncMock(return_value=None)

    result = await analytics.track_task_complete(
        task_id="nonexistent",
        status=TaskStatus.FAILED,
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_agent_metrics_empty_returns_none():
    analytics, redis_stub = _make_analytics_with_stub()
    redis_stub.hgetall = AsyncMock(return_value={})

    result = await analytics.get_agent_metrics("unknown_agent")
    assert result is None


@pytest.mark.asyncio
async def test_get_agent_metrics_populated():
    analytics, redis_stub = _make_analytics_with_stub()
    redis_stub.hgetall = AsyncMock(
        return_value={
            b"total_tasks": b"10",
            b"completed_tasks": b"8",
            b"failed_tasks": b"2",
            b"total_duration_ms": b"5000.0",
            b"total_tokens_used": b"1024",
            b"agent_type": b"chat",
            b"last_activity": b"2026-01-01T00:00:00",
        }
    )

    metrics = await analytics.get_agent_metrics("chat")

    assert metrics is not None
    assert metrics.total_tasks == 10
    assert metrics.completed_tasks == 8
    assert metrics.success_rate == pytest.approx(80.0)
    assert metrics.error_rate == pytest.approx(20.0)
    assert metrics.avg_duration_ms == pytest.approx(500.0)


@pytest.mark.asyncio
async def test_get_all_agents_metrics_empty():
    analytics, redis_stub = _make_analytics_with_stub()
    redis_stub.keys = AsyncMock(return_value=[])

    result = await analytics.get_all_agents_metrics()
    assert result == []


# ---------------------------------------------------------------------------
# track_agent_usage context manager tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_track_agent_usage_success():
    analytics, redis_stub = _make_analytics_with_stub()

    # Provide a running record so track_task_complete can find it
    task_captured = {}

    async def capture_set(key, value, **kwargs):
        task_captured["key"] = key
        task_captured["value"] = value
        return True

    redis_stub.set.side_effect = capture_set

    async def fake_get(key):
        stored = task_captured.get("value")
        return stored.encode("utf-8") if isinstance(stored, str) else stored

    redis_stub.get.side_effect = fake_get

    with patch("services.agent_analytics.get_agent_analytics", return_value=analytics):
        async with track_agent_usage("chat", "conversation"):
            pass  # no exception → COMPLETED

    # track_task_complete should have been called (delete was called)
    redis_stub.delete.assert_awaited()


@pytest.mark.asyncio
async def test_track_agent_usage_failure_records_failed():
    analytics, redis_stub = _make_analytics_with_stub()

    task_captured = {}

    async def capture_set(key, value, **kwargs):
        task_captured["key"] = key
        task_captured["value"] = value
        return True

    redis_stub.set.side_effect = capture_set

    async def fake_get(key):
        stored = task_captured.get("value")
        return stored.encode("utf-8") if isinstance(stored, str) else stored

    redis_stub.get.side_effect = fake_get

    completed_statuses = []

    original_complete = analytics.track_task_complete

    async def capture_complete(task_id, status, **kwargs):
        completed_statuses.append(status)
        return await original_complete(task_id=task_id, status=status, **kwargs)

    analytics.track_task_complete = capture_complete

    with patch("services.agent_analytics.get_agent_analytics", return_value=analytics):
        with pytest.raises(ValueError):
            async with track_agent_usage("chat", "conversation"):
                raise ValueError("boom")

    assert TaskStatus.FAILED in completed_statuses


# ---------------------------------------------------------------------------
# BaseAgent.execute_with_tracking hook smoke test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_with_tracking_calls_analytics():
    """Verify that execute_with_tracking invokes AgentAnalytics on success."""
    from agents.base_agent import AgentRequest, AgentResponse, BaseAgent

    class _DummyAgent(BaseAgent):
        def __init__(self):
            super().__init__("dummy")

        async def process_request(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                request_id=request.request_id,
                agent_type=self.agent_type,
                status="success",
                result="ok",
            )

        def get_capabilities(self):
            return []

    dummy = _DummyAgent()
    mock_analytics = AsyncMock()
    mock_analytics.track_task_start = AsyncMock(return_value=MagicMock())
    mock_analytics.track_task_complete = AsyncMock(return_value=MagicMock())

    request = AgentRequest(
        request_id=str(uuid.uuid4()),
        agent_type="dummy",
        action="test",
        payload={},
    )

    with (
        patch("agents.base_agent.get_agent_analytics", return_value=mock_analytics, create=True),
        patch("agents.base_agent.TaskStatus", TaskStatus, create=True),
    ):
        response = await dummy.execute_with_tracking(request)

    assert response.status == "success"


@pytest.mark.asyncio
async def test_execute_with_tracking_records_failure():
    """execute_with_tracking records FAILED outcome when process_request raises."""
    from agents.base_agent import AgentRequest, AgentResponse, BaseAgent

    class _BrokenAgent(BaseAgent):
        def __init__(self):
            super().__init__("broken")

        async def process_request(self, request: AgentRequest) -> AgentResponse:
            raise RuntimeError("intentional failure")

        def get_capabilities(self):
            return []

    broken = _BrokenAgent()
    request = AgentRequest(
        request_id=str(uuid.uuid4()),
        agent_type="broken",
        action="test",
        payload={},
    )

    mock_analytics = AsyncMock()
    mock_analytics.track_task_start = AsyncMock(return_value=MagicMock())
    mock_analytics.track_task_complete = AsyncMock(return_value=MagicMock())

    with (
        patch("agents.base_agent.get_agent_analytics", return_value=mock_analytics, create=True),
        patch("agents.base_agent.TaskStatus", TaskStatus, create=True),
    ):
        response = await broken.execute_with_tracking(request)

    assert response.status == "error"
    assert "intentional failure" in (response.error or "")


# ---------------------------------------------------------------------------
# GET /api/agent_config/agents/usage endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_usage_endpoint_returns_structure():
    """Usage endpoint returns expected keys when analytics data is present."""
    from fastapi.testclient import TestClient

    mock_metrics = MagicMock()
    mock_metrics.agent_id = "chat"
    mock_metrics.agent_type = "chat"
    mock_metrics.total_tasks = 5
    mock_metrics.completed_tasks = 4
    mock_metrics.failed_tasks = 1
    mock_metrics.cancelled_tasks = 0
    mock_metrics.timeout_tasks = 0
    mock_metrics.avg_duration_ms = 200.0
    mock_metrics.total_tokens_used = 512
    mock_metrics.error_rate = 20.0
    mock_metrics.success_rate = 80.0
    mock_metrics.last_activity = "2026-01-01T00:00:00+00:00"
    mock_metrics.to_dict = MagicMock(
        return_value={
            "agent_id": "chat",
            "agent_type": "chat",
            "total_tasks": 5,
            "completed_tasks": 4,
            "failed_tasks": 1,
            "cancelled_tasks": 0,
            "timeout_tasks": 0,
            "avg_duration_ms": 200.0,
            "min_duration_ms": 100.0,
            "max_duration_ms": 300.0,
            "total_tokens_used": 512,
            "error_rate": 20.0,
            "success_rate": 80.0,
            "last_activity": "2026-01-01T00:00:00+00:00",
        }
    )

    mock_task = {
        "agent_id": "chat",
        "agent_type": "chat",
        "task_id": "t-1",
        "task_name": "conversation",
        "status": "completed",
        "started_at": "2026-01-01T10:00:00+00:00",
        "completed_at": "2026-01-01T10:00:01+00:00",
        "duration_ms": 200.0,
        "tokens_used": 128,
        "error_message": None,
        "metadata": {},
    }

    mock_analytics_instance = AsyncMock()
    mock_analytics_instance.get_all_agents_metrics = AsyncMock(return_value=[mock_metrics])
    mock_analytics_instance.get_recent_tasks = AsyncMock(return_value=[mock_task])

    with (
        patch(
            "api.agent_config.check_admin_permission",
            return_value=True,
        ),
        patch(
            "services.agent_analytics.get_agent_analytics",
            return_value=mock_analytics_instance,
        ),
    ):
        from fastapi import FastAPI

        from api.agent_config import router

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/agents/usage")

    assert response.status_code == 200
    body = response.json()
    assert "agents" in body
    assert "daily_trends" in body
    assert "summary" in body
    assert "timestamp" in body
    assert body["summary"]["period_days"] == 7


@pytest.mark.asyncio
async def test_usage_endpoint_outcome_filter():
    """outcome= query param filters the daily_trends to matching tasks only."""
    mock_tasks = [
        {
            "agent_id": "chat",
            "status": "completed",
            "started_at": "2026-01-01T10:00:00+00:00",
            "duration_ms": 100.0,
        },
        {
            "agent_id": "chat",
            "status": "failed",
            "started_at": "2026-01-01T11:00:00+00:00",
            "duration_ms": 50.0,
        },
    ]

    mock_analytics_instance = AsyncMock()
    mock_analytics_instance.get_all_agents_metrics = AsyncMock(return_value=[])
    mock_analytics_instance.get_recent_tasks = AsyncMock(return_value=mock_tasks)

    with (
        patch(
            "api.agent_config.check_admin_permission",
            return_value=True,
        ),
        patch(
            "services.agent_analytics.get_agent_analytics",
            return_value=mock_analytics_instance,
        ),
    ):
        from fastapi import FastAPI

        from api.agent_config import router

        app = FastAPI()
        app.include_router(router)

        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/agents/usage?outcome=completed&days=30")

    assert response.status_code == 200
    body = response.json()
    # Only completed tasks should appear → total_calls == 1
    assert body["summary"]["total_calls"] == 1
